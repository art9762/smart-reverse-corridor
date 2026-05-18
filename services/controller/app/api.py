"""FastAPI HTTP + WebSocket API."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HealthResp(BaseModel):
    status: str
    fsm_phase: str
    mode: str


class OverrideReq(BaseModel):
    action: Literal["force_phase", "emergency", "resume", "mode_switch"]
    phase: Optional[str] = None
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
    prio_w_wait: Optional[float] = None
    prio_w_other_empty: Optional[float] = None
    prio_w_truck: Optional[float] = None
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


@router.post("/override")
async def override(req: OverrideReq, request: Request) -> Dict[str, Any]:
    eng = _engine(request)
    return eng.apply_override(req.model_dump())


@router.post("/config")
async def config(req: ConfigReq, request: Request) -> Dict[str, Any]:
    eng = _engine(request)
    payload = req.model_dump(exclude_none=True)
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
