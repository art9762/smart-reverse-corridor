"""Core engine binding FSM, counters, scheduler, MQTT and storage.

The engine runs three asyncio tasks:
  * `_consume_inbox` — pulls MQTT messages from the inbox queue
  * `_tick_loop` — once per second: publishes state, runs watchdogs
  * `_phase_loop` — runs the phase machine

It also owns broadcast to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import structlog

from .config import Settings
from .counters import Counters
from .fsm import (
    ALL_RED_AFTER_A,
    ALL_RED_AFTER_B,
    EMERGENCY_STOP,
    GREEN_A,
    GREEN_B,
    INIT,
    RED_BOTH,
    YELLOW_A,
    YELLOW_B,
    CorridorFSM,
    FSMTimings,
    PhaseTimer,
)
from .mqtt_client import (
    IncomingMessage,
    MQTTClient,
    parse_cam_topic,
    parse_cmd_topic,
)
from .scheduler import Scheduler, SchedulerInputs
from .storage import InfluxWriter, SQLiteStore

log = structlog.get_logger("engine")


@dataclass
class Alert:
    ts: float
    level: str
    code: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts, "level": self.level, "code": self.code,
                "detail": self.detail}


@dataclass
class EngineState:
    mode: str = "adaptive"  # adaptive | baseline
    queue_a: int = 0
    queue_b: int = 0
    last_wait_started_a: float = field(default_factory=time.monotonic)
    last_wait_started_b: float = field(default_factory=time.monotonic)
    throughput_5min: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
    avg_delay_5min: Dict[str, float] = field(default_factory=lambda: {"A": 0.0, "B": 0.0})
    max_queue_today: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
    alerts: Deque[Alert] = field(default_factory=lambda: deque(maxlen=200))


class Engine:
    """High-level controller engine."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.counters = Counters(stuck_threshold_s=settings.stuck_threshold_s)
        self.scheduler = Scheduler(settings)
        self.fsm = CorridorFSM(
            timings=FSMTimings(
                yellow_s=settings.yellow_s,
                all_red_guard_s=settings.all_red_guard_s,
                clear_timeout_s=settings.clear_timeout_s,
            ),
            zone_empty_fn=self.counters.is_zone_empty,
        )
        self.phase_timer = PhaseTimer()
        self.state = EngineState(mode=settings.default_mode)
        self.storage = SQLiteStore(settings.sqlite_path)
        self.influx = InfluxWriter(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
            bucket=settings.influx_bucket,
        )

        self.inbox: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self.mqtt: Optional[MQTTClient] = None
        self._tasks: List[asyncio.Task] = []
        self._ws_clients: Set[Any] = set()
        self._ws_lock = asyncio.Lock()

        # Phase scheduling — when this monotonic deadline elapses, advance.
        self._phase_deadline: float = time.monotonic()
        self._stuck_alerted: Dict[str, float] = {}
        self._cameras_lost_alerted: Dict[str, float] = {}
        self._zone_clear_started: Optional[float] = None

        # Fallback fixed-timer mode: activated when both cameras on a side are lost
        # for longer than fallback_camera_loss_timeout_s.
        # _fallback_mode: None = normal, "A" or "B" = side whose cameras are lost
        self._fallback_mode: Optional[str] = None
        self._fallback_side_lost_at: Dict[str, float] = {}  # side -> monotonic when both cams lost

        # Rolling-window metrics
        self._throughput_events: Dict[str, Deque[float]] = {"A": deque(), "B": deque()}
        self._vehicle_entries: Dict[int, Tuple[str, float]] = {}  # track_id -> (side, entry_time)
        self._recent_delays: Dict[str, Deque[float]] = {"A": deque(maxlen=500), "B": deque(maxlen=500)}
        self._metrics_window_s: float = 300.0  # 5 minutes

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.mqtt = MQTTClient(self.settings, loop, self.inbox)
        self.mqtt.start()

        # Boot FSM into RED_BOTH and prime first phase.
        self.fsm.try_trigger("boot")
        self._begin_red_both(initial=True)

        self._tasks = [
            asyncio.create_task(self._consume_inbox(), name="consume_inbox"),
            asyncio.create_task(self._tick_loop(), name="tick_loop"),
            asyncio.create_task(self._phase_loop(), name="phase_loop"),
        ]
        log.info("engine.started", mode=self.state.mode)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        if self.mqtt is not None:
            self.mqtt.stop()
        self.influx.close()
        log.info("engine.stopped")

    # ------------------------------------------------------------------
    # Public API surface (used by FastAPI handlers)
    # ------------------------------------------------------------------

    def state_payload(self) -> Dict[str, Any]:
        cam_health = (
            self.mqtt.camera_health(self.settings.heartbeat_timeout_s)
            if self.mqtt
            else {"A_in": False, "A_out": False, "B_in": False, "B_out": False}
        )
        return {
            "phase": self.fsm.phase,
            "phase_started_at": self.phase_timer.started_at,
            "phase_planned_end_at": self.phase_timer.planned_end_at,
            "inside_A": self.counters.inside("A"),
            "inside_B": self.counters.inside("B"),
            "queue_A": self.state.queue_a,
            "queue_B": self.state.queue_b,
            "mode": self.state.mode,
            "camera_health": cam_health,
        }

    def metrics_payload(self) -> Dict[str, Any]:
        return {
            "ts": time.time(),
            "throughput_5min": dict(self.state.throughput_5min),
            "avg_delay_5min": dict(self.state.avg_delay_5min),
            "queue": {"A": self.state.queue_a, "B": self.state.queue_b},
            "max_queue_today": dict(self.state.max_queue_today),
        }

    def recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in list(self.state.alerts)[-limit:]]

    # ------------------------------------------------------------------
    # MQTT inbox consumer
    # ------------------------------------------------------------------

    async def _consume_inbox(self) -> None:
        while True:
            try:
                msg = await self.inbox.get()
            except asyncio.CancelledError:
                raise
            try:
                await self._handle_message(msg)
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("inbox.handle_failed", error=str(exc), topic=msg.topic)

    async def _handle_message(self, msg: IncomingMessage) -> None:
        cam = parse_cam_topic(msg.topic)
        if cam is not None:
            if cam["kind"] == "event":
                self._handle_cam_event(cam["side"], cam["dir"], msg.payload)
            elif cam["kind"] == "heartbeat":
                # Tracked in MQTTClient already.
                return
            return

        cmd = parse_cmd_topic(msg.topic)
        if cmd == "override":
            self._apply_override(msg.payload)
        elif cmd == "config":
            self._apply_config(msg.payload)

    def _handle_cam_event(self, side: str, direction: str, payload: Dict[str, Any]) -> None:
        # `side` here is the CAMERA side (from MQTT topic), not the vehicle's
        # travel direction. For zone occupancy we need to track by vehicle
        # origin side:
        #   - cam A/in  = vehicle from side A entering zone  → inside_A++
        #   - cam B/out = vehicle from side A exiting zone   → inside_A--
        #   - cam B/in  = vehicle from side B entering zone  → inside_B++
        #   - cam A/out = vehicle from side B exiting zone   → inside_B--
        #
        # Rule: "in" events increment the CAMERA side's inside counter.
        #       "out" events decrement the OPPOSITE side's inside counter
        #       (because exit camera is on the opposite end from entry).
        if direction == "in":
            self.counters.on_event(side, "in")
        elif direction == "out":
            # Vehicle exits on camera side X → it entered from the opposite side
            opposite = "B" if side.upper() == "A" else "A"
            self.counters.on_event(opposite, "out")

        side_u = side.upper()
        now = time.time()

        if direction == "in":
            # Record entry timestamp for rolling throughput
            self._throughput_events[side_u].append(now)
            # Track vehicle for delay calculation
            track_id = payload.get("track_id")
            if track_id is not None:
                self._vehicle_entries[int(track_id)] = (side_u, now)
        elif direction == "out":
            # Calculate delay for this vehicle
            track_id = payload.get("track_id")
            if track_id is not None:
                key = int(track_id)
                entry = self._vehicle_entries.pop(key, None)
                if entry is not None:
                    entry_side, entry_time = entry
                    delay = now - entry_time
                    if delay > 0:
                        self._recent_delays[entry_side].append(delay)

        self.storage.log_event("cam_event", {"side": side, "dir": direction, **payload})

    # ------------------------------------------------------------------
    # Phase loop
    # ------------------------------------------------------------------

    async def _phase_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(0.1)
                now = time.monotonic()
                if now < self._phase_deadline:
                    continue
                # Deadline reached — advance.
                await self._advance_phase()
        except asyncio.CancelledError:
            raise

    async def _advance_phase(self) -> None:
        phase = self.fsm.phase
        if phase == EMERGENCY_STOP:
            # Stay until operator resumes
            self._phase_deadline = time.monotonic() + 1.0
            return

        # Fallback fixed-timer mode: when both cameras on a side are lost,
        # alternate GREEN_A / GREEN_B on a fixed timer, ignoring zone-empty guards.
        if self._fallback_mode is not None and not self.fsm.is_emergency():
            await self._advance_phase_fallback(phase)
            return

        if phase == RED_BOTH:
            # Pick a side and try to go green
            next_side = Scheduler.pick_next_side(
                self.state.queue_a, self.state.queue_b, self.fsm.last_green_side
            )
            if self._try_go_green(next_side):
                return
            # Couldn't go green (zone not empty / guard) — wait a beat
            self._phase_deadline = time.monotonic() + 0.5
            self._maybe_clear_timeout()
            return

        if phase in (GREEN_A, GREEN_B):
            self.fsm.try_trigger("go_yellow")
            self.phase_timer.restart(self.settings.yellow_s)
            self._phase_deadline = time.monotonic() + self.settings.yellow_s
            self._publish_state()
            return

        if phase in (YELLOW_A, YELLOW_B):
            self.fsm.try_trigger("go_all_red")
            self.phase_timer.restart(self.settings.all_red_guard_s)
            self._phase_deadline = time.monotonic() + self.settings.all_red_guard_s
            self._zone_clear_started = time.monotonic()
            self._publish_state()
            return

        if phase in (ALL_RED_AFTER_A, ALL_RED_AFTER_B):
            target = "B" if phase == ALL_RED_AFTER_A else "A"
            if self._try_go_green(target):
                self._zone_clear_started = None
                return
            # Guard not met — keep waiting; check clear timeout
            self._phase_deadline = time.monotonic() + 0.5
            self._maybe_clear_timeout()
            return

    async def _advance_phase_fallback(self, phase: str) -> None:
        """Fixed-timer phase advance used when cameras are lost on one side.

        Alternates GREEN_A / GREEN_B on a fixed timer (fallback_green_s),
        bypassing zone-empty guards since we can't trust the counters.
        """
        fallback_green = self.settings.fallback_green_s

        if phase == RED_BOTH:
            # Pick the side opposite to the lost-camera side first (safer),
            # or just alternate from last green.
            lost_side = self._fallback_mode  # "A" or "B"
            # Prefer the side whose cameras are working
            next_side = "B" if lost_side == "A" else "A"
            if self.fsm.last_green_side == next_side:
                # Already gave green to the healthy side; now give to lost side
                next_side = lost_side

            # Force green without zone-empty guard by temporarily patching
            # the FSM's zone_empty_fn
            orig_fn = self.fsm._zone_empty_fn
            self.fsm._zone_empty_fn = lambda: True
            try:
                ok = self._try_go_green(next_side)
            finally:
                self.fsm._zone_empty_fn = orig_fn

            if not ok:
                self._phase_deadline = time.monotonic() + 0.5
            else:
                # Override the phase timer with fallback duration
                self.phase_timer.restart(fallback_green)
                self._phase_deadline = time.monotonic() + fallback_green
            return

        if phase in (GREEN_A, GREEN_B):
            self.fsm.try_trigger("go_yellow")
            self.phase_timer.restart(self.settings.yellow_s)
            self._phase_deadline = time.monotonic() + self.settings.yellow_s
            self._publish_state()
            return

        if phase in (YELLOW_A, YELLOW_B):
            self.fsm.try_trigger("go_all_red")
            self.phase_timer.restart(self.settings.all_red_guard_s)
            self._phase_deadline = time.monotonic() + self.settings.all_red_guard_s
            self._publish_state()
            return

        if phase in (ALL_RED_AFTER_A, ALL_RED_AFTER_B):
            # In fallback mode, skip zone-empty check and go straight to RED_BOTH
            self.fsm.try_trigger("halt_to_red")
            self._begin_red_both(initial=False)
            self._publish_state()
            return

    def _try_go_green(self, side: str) -> bool:
        trig = "go_green_a" if side.upper() == "A" else "go_green_b"
        if not self.fsm.try_trigger(trig):
            return False
        # Compute green duration
        if side.upper() == "A":
            inp = SchedulerInputs(
                queue_side=self.state.queue_a,
                wait_other=time.monotonic() - self.state.last_wait_started_b,
                other_empty=self.counters.inside("B") == 0
                and self.state.queue_b == 0,
            )
            self.state.last_wait_started_a = time.monotonic()
        else:
            inp = SchedulerInputs(
                queue_side=self.state.queue_b,
                wait_other=time.monotonic() - self.state.last_wait_started_a,
                other_empty=self.counters.inside("A") == 0
                and self.state.queue_a == 0,
            )
            self.state.last_wait_started_b = time.monotonic()
        duration = self.scheduler.compute(self.state.mode, inp)
        self.phase_timer.restart(duration)
        self._phase_deadline = time.monotonic() + duration
        self._publish_state()
        self.storage.log_event(
            "phase_change",
            {"phase": self.fsm.phase, "duration_s": duration, "mode": self.state.mode},
        )
        return True

    def _begin_red_both(self, *, initial: bool) -> None:
        self.phase_timer.restart(self.settings.all_red_guard_s if initial else 1.0)
        self._phase_deadline = time.monotonic() + (
            self.settings.all_red_guard_s if initial else 1.0
        )

    def _maybe_clear_timeout(self) -> None:
        if (
            self._zone_clear_started is not None
            and not self.counters.is_zone_empty()
            and (time.monotonic() - self._zone_clear_started)
            >= self.settings.clear_timeout_s
        ):
            self._raise_emergency("STUCK_VEHICLE", "zone did not clear in time")

    # ------------------------------------------------------------------
    # Tick loop / watchdogs / metrics publish
    # ------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                self._refresh_queues()
                self._compute_rolling_metrics()
                self._run_watchdogs()
                self._publish_state()
                self._publish_metrics()
        except asyncio.CancelledError:
            raise

    def _refresh_queues(self) -> None:
        # Queue = vehicles currently inside the zone from that side
        self.state.queue_a = self.counters.inside("A")
        self.state.queue_b = self.counters.inside("B")
        self.state.max_queue_today["A"] = max(
            self.state.max_queue_today["A"], self.state.queue_a
        )
        self.state.max_queue_today["B"] = max(
            self.state.max_queue_today["B"], self.state.queue_b
        )

    def _compute_rolling_metrics(self) -> None:
        now = time.time()
        cutoff = now - self._metrics_window_s

        for side in ("A", "B"):
            # Prune old throughput events and count remaining
            events = self._throughput_events[side]
            while events and events[0] < cutoff:
                events.popleft()
            self.state.throughput_5min[side] = len(events)

            # Compute average delay from recent completions
            delays = self._recent_delays[side]
            if delays:
                self.state.avg_delay_5min[side] = round(sum(delays) / len(delays), 2)
            else:
                self.state.avg_delay_5min[side] = 0.0

        # Prune stale vehicle entries (no matching "out" after 10 min)
        stale_cutoff = now - 600.0
        stale_keys = [k for k, (_, t) in self._vehicle_entries.items() if t < stale_cutoff]
        for k in stale_keys:
            del self._vehicle_entries[k]

    def _run_watchdogs(self) -> None:
        # Stuck vehicles per side
        for side, duration in self.counters.stuck_sides().items():
            last = self._stuck_alerted.get(side, 0.0)
            if time.monotonic() - last >= 30.0:
                self._stuck_alerted[side] = time.monotonic()
                self._raise_alert(
                    "warning",
                    "STUCK_VEHICLE",
                    f"side={side} duration_s={duration:.0f}",
                )
        # Camera heartbeats
        if self.mqtt is not None:
            lost = self.mqtt.lost_cameras(self.settings.heartbeat_timeout_s)
            if lost:
                # If both cameras on a single side are lost — RED_BOTH safe state
                for side in ("A", "B"):
                    if {f"{side}_in", f"{side}_out"}.issubset(lost.keys()):
                        # Track when both cameras on this side were first lost
                        if side not in self._fallback_side_lost_at:
                            self._fallback_side_lost_at[side] = time.monotonic()
                            self._raise_alert(
                                "warning",
                                "CAMERA_LOST",
                                f"both cameras on side {side} lost",
                            )
                            if not self.fsm.is_emergency() and self.fsm.phase != RED_BOTH:
                                self.fsm.try_trigger("halt_to_red")
                                self._begin_red_both(initial=False)
                                self._publish_state()

                        # Check if we've been stuck in RED_BOTH long enough to activate fallback
                        lost_duration = time.monotonic() - self._fallback_side_lost_at[side]
                        if (
                            lost_duration >= self.settings.fallback_camera_loss_timeout_s
                            and self._fallback_mode is None
                            and not self.fsm.is_emergency()
                        ):
                            self._fallback_mode = side
                            self._raise_alert(
                                "warning",
                                "FALLBACK_TIMER_MODE",
                                f"side {side} cameras lost for {lost_duration:.0f}s — switching to fixed-timer fallback",
                            )
                            log.warning(
                                "engine.fallback_activated",
                                side=side,
                                lost_duration_s=lost_duration,
                            )
                    else:
                        # Cameras recovered on this side
                        if side in self._fallback_side_lost_at:
                            del self._fallback_side_lost_at[side]
                            if self._fallback_mode == side:
                                self._fallback_mode = None
                                self._raise_alert(
                                    "info",
                                    "FALLBACK_TIMER_CLEARED",
                                    f"side {side} cameras recovered — resuming normal operation",
                                )
                                log.info("engine.fallback_deactivated", side=side)

                for cid in lost:
                    last = self._cameras_lost_alerted.get(cid, 0.0)
                    if time.monotonic() - last >= 10.0:
                        self._cameras_lost_alerted[cid] = time.monotonic()
                        self._raise_alert("warning", "CAMERA_LOST", f"camera={cid}")
            else:
                # All cameras healthy — clear any fallback state
                if self._fallback_side_lost_at:
                    self._fallback_side_lost_at.clear()
                if self._fallback_mode is not None:
                    self._fallback_mode = None
                    self._raise_alert(
                        "info",
                        "FALLBACK_TIMER_CLEARED",
                        "all cameras recovered — resuming normal operation",
                    )
                    log.info("engine.fallback_deactivated", side="all")

    # ------------------------------------------------------------------
    # Overrides / config
    # ------------------------------------------------------------------

    def apply_override(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Public entry called by REST handlers."""
        return self._apply_override(payload)

    def apply_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._apply_config(payload)

    def reset_for_test(self) -> Dict[str, Any]:
        """Reset engine state for integration tests.

        Resets counters, returns FSM to RED_BOTH, clears metrics/alerts.
        Does NOT restart MQTT or storage.
        """
        # Reset counters
        self.counters.reset()

        # Clear rolling metrics
        for side in ("A", "B"):
            self._throughput_events[side].clear()
            self._recent_delays[side].clear()
        self._vehicle_entries.clear()

        # Clear alerts
        self.state.alerts.clear()

        # Reset queue state
        self.state.queue_a = 0
        self.state.queue_b = 0
        self.state.throughput_5min = {"A": 0, "B": 0}
        self.state.avg_delay_5min = {"A": 0.0, "B": 0.0}
        self.state.max_queue_today = {"A": 0, "B": 0}
        self.state.last_wait_started_a = time.monotonic()
        self.state.last_wait_started_b = time.monotonic()

        # Reset watchdog state
        self._stuck_alerted.clear()
        self._cameras_lost_alerted.clear()
        self._zone_clear_started = None
        self._fallback_mode = None
        self._fallback_side_lost_at.clear()

        # Force FSM back to RED_BOTH (go through emergency if needed)
        if self.fsm.is_emergency():
            self.fsm.try_trigger("resume")
        elif self.fsm.phase not in (RED_BOTH,):
            self.fsm.try_trigger("halt_to_red")
            if self.fsm.phase not in (RED_BOTH,):
                # In a YELLOW state — force via emergency + resume
                self.fsm.try_trigger("emergency")
                self.fsm.try_trigger("resume")

        self._begin_red_both(initial=True)
        self._publish_state()
        log.info("engine.reset_for_test")
        return {"ok": True, "phase": self.fsm.phase}

    def _apply_override(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = (payload or {}).get("action")
        result: Dict[str, Any] = {"ok": True, "action": action}
        if action == "force_phase":
            phase = payload.get("phase")
            ok = self._force_phase(phase)
            result["ok"] = ok
        elif action == "emergency":
            self._raise_emergency(
                "EMERGENCY_OVERRIDE",
                payload.get("reason", "operator emergency"),
            )
        elif action == "resume":
            if self.fsm.is_emergency():
                self.fsm.try_trigger("resume")
                self._begin_red_both(initial=False)
                self._publish_state()
            result["ok"] = True
        elif action == "mode_switch":
            mode = payload.get("mode")
            if mode in ("baseline", "adaptive"):
                self.state.mode = mode
                result["mode"] = mode
            else:
                result["ok"] = False
                result["error"] = "mode must be baseline|adaptive"
        else:
            result["ok"] = False
            result["error"] = f"unknown action: {action}"
        self.storage.log_event("override", payload or {})
        return result

    def _force_phase(self, phase: Optional[str]) -> bool:
        if phase not in (GREEN_A, GREEN_B, RED_BOTH, EMERGENCY_STOP):
            return False
        if phase == EMERGENCY_STOP:
            self._raise_emergency("EMERGENCY_OVERRIDE", "force_phase")
            return True
        if phase == RED_BOTH:
            self.fsm.try_trigger("halt_to_red")
            self._begin_red_both(initial=False)
            self._publish_state()
            return True
        # Force GREEN_X — only if guards are met (safety!)
        side = "A" if phase == GREEN_A else "B"
        # If currently in GREEN, drive through YELLOW/ALL_RED before re-greening.
        if self.fsm.phase in (GREEN_A, GREEN_B):
            self.fsm.try_trigger("go_yellow")
            self.fsm.try_trigger("go_all_red")
        ok = self._try_go_green(side)
        return ok

    def _apply_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        updated: Dict[str, Any] = {}
        # Allow updating timing and weights at runtime
        keys = (
            "green_min_s",
            "green_max_s",
            "yellow_s",
            "all_red_guard_s",
            "clear_timeout_s",
            "prio_w_queue",
            "prio_w_wait",
            "prio_w_other_empty",
            "prio_w_truck",
            "base_green_s",
            "stuck_threshold_s",
        )
        for k in keys:
            if k in (payload or {}):
                v = payload[k]
                cur = getattr(self.settings, k)
                try:
                    setattr(self.settings, k, type(cur)(v))
                    updated[k] = getattr(self.settings, k)
                except (ValueError, TypeError):
                    pass
        # Keep counters watchdog in sync
        if "stuck_threshold_s" in updated:
            self.counters.stuck_threshold_s = self.settings.stuck_threshold_s
        # Persist
        for k, v in updated.items():
            self.storage.set_config(k, str(v))
        return {"ok": True, "updated": updated}

    # ------------------------------------------------------------------
    # Emergency / alerts
    # ------------------------------------------------------------------

    def _raise_emergency(self, code: str, detail: str) -> None:
        if not self.fsm.is_emergency():
            self.fsm.try_trigger("emergency")
        self.phase_timer.restart(0)
        self._phase_deadline = time.monotonic() + 1.0
        self._raise_alert("emergency", code, detail)
        self._publish_state()

    def _raise_alert(self, level: str, code: str, detail: str = "") -> None:
        alert = Alert(ts=time.time(), level=level, code=code, detail=detail)
        self.state.alerts.append(alert)
        self.storage.log_event("alert", alert.to_dict())
        if self.mqtt is not None:
            self.mqtt.publish_alert(alert.to_dict())
        log.info("alert", level=level, code=code, detail=detail)
        # Broadcast to WS — schedule on the loop
        asyncio.create_task(self._broadcast_ws({"type": "alert", "alert": alert.to_dict()}))

    # ------------------------------------------------------------------
    # Publish helpers
    # ------------------------------------------------------------------

    def _publish_state(self) -> None:
        payload = self.state_payload()
        if self.mqtt is not None:
            self.mqtt.publish_state(payload)
        asyncio.create_task(self._broadcast_ws({"type": "state", "state": payload}))

    def _publish_metrics(self) -> None:
        payload = self.metrics_payload()
        if self.mqtt is not None:
            self.mqtt.publish_metrics(payload)
        # Influx best-effort
        self.influx.write_metrics(
            measurement="corridor_tick",
            fields={
                "queue_A": payload["queue"]["A"],
                "queue_B": payload["queue"]["B"],
                "throughput_A": payload["throughput_5min"]["A"],
                "throughput_B": payload["throughput_5min"]["B"],
                "delay_A": payload["avg_delay_5min"]["A"],
                "delay_B": payload["avg_delay_5min"]["B"],
                "inside_A": self.counters.inside("A"),
                "inside_B": self.counters.inside("B"),
            },
            tags={"phase": self.fsm.phase, "mode": self.state.mode},
        )

    # ------------------------------------------------------------------
    # WebSocket fan-out
    # ------------------------------------------------------------------

    def register_ws(self, ws: Any) -> None:
        self._ws_clients.add(ws)

    def unregister_ws(self, ws: Any) -> None:
        self._ws_clients.discard(ws)

    async def _broadcast_ws(self, payload: Dict[str, Any]) -> None:
        if not self._ws_clients:
            return
        dead: List[Any] = []
        async with self._ws_lock:
            for ws in list(self._ws_clients):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_clients.discard(ws)
