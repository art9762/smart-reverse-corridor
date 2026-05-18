"""FastAPI HTTP + WebSocket API."""

from __future__ import annotations

import os
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

router = APIRouter()


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
#
# The dashboard (web/) lives on a different origin than the controller in every
# real deployment (different host port at minimum, different DNS in production).
# Without CORS, every POST from the Operator Panel is rejected by the browser
# *before* it ever hits FastAPI, which looks like "buttons do nothing".
#
# DEV default: allow everything. For prod, set CONTROLLER_CORS_ORIGINS to a
# comma-separated allow-list, e.g. "https://ops.example.com,https://admin.example.com".


def _parse_origins(env: str | None) -> list[str]:
    if not env:
        return ["*"]
    items = [o.strip() for o in env.split(",") if o.strip()]
    return items or ["*"]


def install_cors(app: FastAPI) -> None:
    """Attach permissive CORS for DEV; tighten via env in prod."""
    origins = _parse_origins(os.getenv("CONTROLLER_CORS_ORIGINS"))
    # When using "*", credentials must be False per the CORS spec.
    allow_credentials = origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HealthResp(BaseModel):
    status: str
    fsm_phase: str
    mode: str


class OverrideReq(BaseModel):
    """Operator command. Accepts both `force_phase` and the legacy aliases
    used by the dashboard (`emergency_stop`, `priority`) so the buttons work
    without a separate adapter layer.
    """

    action: Literal[
        "force_phase",
        "emergency",
        "emergency_stop",
        "resume",
        "mode_switch",
        "priority",
    ]
    phase: Optional[str] = None
    side: Optional[Literal["A", "B"]] = None
    mode: Optional[Literal["baseline", "adaptive"]] = None
    reason: Optional[str] = None
    by: Optional[str] = None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v):  # noqa: D401
        if v is None:
            return v
        allowed = {"GREEN_A", "GREEN_B", "RED_BOTH", "EMERGENCY_STOP"}
        if v not in allowed:
            raise ValueError(f"phase must be one of {sorted(allowed)}")
        return v


class ConfigReq(BaseModel):
    """Hot-reloadable timings and weights."""

    green_min_s: Optional[float] = Field(default=None, ge=1, le=600)
    green_max_s: Optional[float] = Field(default=None, ge=1, le=600)
    yellow_s: Optional[float] = Field(default=None, ge=1, le=30)
    all_red_guard_s: Optional[float] = Field(default=None, ge=0, le=60)
    clear_timeout_s: Optional[float] = Field(default=None, ge=1, le=600)
    prio_w_queue: Optional[float] = None
    PRIO_W_QUEUE: Optional[float] = None
    prio_w_wait: Optional[float] = None
    PRIO_W_WAIT: Optional[float] = None
    prio_w_other_empty: Optional[float] = None
    prio_w_truck: Optional[float] = None
    PRIO_W_TRUCK: Optional[float] = None
    base_green_s: Optional[float] = Field(default=None, ge=1, le=600)
    stuck_threshold_s: Optional[float] = Field(default=None, ge=1, le=3600)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _engine(request: Request):
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        raise HTTPException(status_code=503, detail="engine not ready")
    return eng


@router.get("/health", response_model=HealthResp)
async def health(request: Request) -> HealthResp:
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        return HealthResp(status="starting", fsm_phase="INIT", mode="adaptive")
    return HealthResp(
        status="ok",
        fsm_phase=eng.fsm.phase,
        mode=eng.state.mode,
    )


@router.get("/state")
async def state(request: Request) -> Dict[str, Any]:
    return _engine(request).state_payload()


@router.get("/metrics")
async def metrics(request: Request) -> Dict[str, Any]:
    eng = _engine(request)
    return {
        "current": eng.metrics_payload(),
        "alerts": eng.recent_alerts(limit=20),
    }


def _normalize_override(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map dashboard-facing aliases onto the engine's internal action names.

    The web UI uses `emergency_stop` and `priority`; the engine speaks
    `emergency` and `force_phase`. Keep the public API forgiving so the
    Operator Panel keeps working without contract churn.
    """
    out = dict(payload)
    action = out.get("action")
    if action == "emergency_stop":
        out["action"] = "emergency"
    elif action == "priority":
        # Treat "priority for side X" as a force-phase to that side's green.
        side = out.get("side")
        if side in ("A", "B"):
            out["action"] = "force_phase"
            out["phase"] = f"GREEN_{side}"
    return out


@router.post("/override")
async def override(req: OverrideReq, request: Request) -> Dict[str, Any]:
    eng = _engine(request)
    return eng.apply_override(_normalize_override(req.model_dump()))


def _normalize_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both upper- and snake_case keys so /config doesn't 422 on the UI.

    The dashboard sends `PRIO_W_QUEUE` etc., the engine reads `prio_w_queue`.
    """
    aliases = {
        "PRIO_W_QUEUE": "prio_w_queue",
        "PRIO_W_WAIT": "prio_w_wait",
        "PRIO_W_TRUCK": "prio_w_truck",
    }
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if v is None:
            continue
        out[aliases.get(k, k)] = v
    return out


@router.post("/config")
async def config(req: ConfigReq, request: Request) -> Dict[str, Any]:
    eng = _engine(request)
    payload = _normalize_config(req.model_dump(exclude_none=True))
    return eng.apply_config(payload)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    eng = getattr(ws.app.state, "engine", None)
    if eng is None:
        await ws.send_json({"type": "error", "error": "engine not ready"})
        await ws.close()
        return
    eng.register_ws(ws)
    # send initial snapshot
    try:
        await ws.send_json({"type": "state", "state": eng.state_payload()})
        while True:
            # We don't expect inbound messages, but keep the socket alive.
            try:
                _ = await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        eng.unregister_ws(ws)
