"""Pygame visualisation. Pure rendering — no domain logic lives here.

The render module is import-safe even with `SDL_VIDEODRIVER=dummy`, which is
how CI and the Docker image run it.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable

from .config import SimulatorSettings
from .world import Phase, Side, Vehicle, World

log = logging.getLogger(__name__)


_COLOR_BG = (28, 30, 38)
_COLOR_ROAD = (60, 64, 76)
_COLOR_LANE = (200, 200, 200)
_COLOR_ZONE = (90, 60, 60)
_COLOR_ZONE_HATCH = (180, 130, 60)
_COLOR_TEXT = (240, 240, 240)
_COLOR_LIGHT_RED = (220, 60, 60)
_COLOR_LIGHT_YELLOW = (235, 200, 60)
_COLOR_LIGHT_GREEN = (90, 200, 90)
_COLOR_LIGHT_OFF = (70, 70, 70)
_COLOR_CAMERA_LINE = (140, 200, 240)

_VEHICLE_COLORS = {
    "car": (90, 160, 230),
    "truck": (235, 150, 60),
    "bus": (240, 200, 90),
    "motorcycle": (200, 200, 200),
    "emergency": (235, 80, 80),
}


@dataclass
class Renderer:
    """Encapsulates the pygame surface + drawing helpers."""

    settings: SimulatorSettings
    headless: bool = False

    def __post_init__(self) -> None:
        if self.headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        # Import lazily so that purely headless callers (e.g. tests) don't
        # require pygame on the import path of unrelated modules.
        import pygame

        self._pygame = pygame
        pygame.init()
        flags = 0
        if self.headless:
            self._screen = pygame.Surface(
                (self.settings.window_width, self.settings.window_height)
            )
        else:
            self._screen = pygame.display.set_mode(
                (self.settings.window_width, self.settings.window_height), flags
            )
            pygame.display.set_caption("Reverse Corridor Simulator")
        self._font = pygame.font.SysFont("dejavusansmono", 14)
        self._big_font = pygame.font.SysFont("dejavusansmono", 18)
        self._clock = pygame.time.Clock()

    # ---------------------------------------------------------------- render
    def draw(
        self,
        world: World,
        phase: Phase,
        mode: str,
        scenario: str,
        metrics: dict,
        events_published: int,
    ) -> None:
        pg = self._pygame
        s = self._screen
        s.fill(_COLOR_BG)
        self._draw_road(world)
        for v in world.all_active():
            self._draw_vehicle(v, world)
        self._draw_lights(world, phase)
        self._draw_hud(world, phase, mode, scenario, metrics, events_published)
        if not self.headless:
            pg.display.flip()
        self._clock.tick(self.settings.fps)

    def _x_to_px(self, x_m: float, world: World) -> int:
        return int((x_m / world.total_m) * self.settings.window_width)

    def _draw_road(self, world: World) -> None:
        pg = self._pygame
        s = self._screen
        h = self.settings.window_height
        road_top = h // 2 - 70
        road_bottom = h // 2 + 70
        pg.draw.rect(
            s, _COLOR_ROAD, (0, road_top, self.settings.window_width, road_bottom - road_top)
        )
        # Lane divider (dashed).
        for x in range(0, self.settings.window_width, 30):
            pg.draw.rect(s, _COLOR_LANE, (x, h // 2 - 1, 18, 2))
        # Work zone (one lane closed in the middle).
        zx0 = self._x_to_px(world.camera_x_a, world)
        zx1 = self._x_to_px(world.camera_x_b, world)
        pg.draw.rect(s, _COLOR_ZONE, (zx0, road_top, zx1 - zx0, 40))
        # Hatch pattern over closed lane.
        for x in range(zx0, zx1, 10):
            pg.draw.line(
                s, _COLOR_ZONE_HATCH, (x, road_top), (x + 10, road_top + 40), 1
            )
        # Camera lines.
        pg.draw.line(s, _COLOR_CAMERA_LINE, (zx0, road_top - 10), (zx0, road_bottom + 10), 2)
        pg.draw.line(s, _COLOR_CAMERA_LINE, (zx1, road_top - 10), (zx1, road_bottom + 10), 2)

    def _draw_vehicle(self, v: Vehicle, world: World) -> None:
        pg = self._pygame
        s = self._screen
        h = self.settings.window_height
        # Y depends on direction of travel.
        y = h // 2 + 20 if v.side is Side.A else h // 2 - 50
        x = self._x_to_px(v.position_m, world)
        # Width scaled by length, but clipped to keep things visible.
        scale = self.settings.window_width / world.total_m
        w_px = max(6, int(v.length_m * scale))
        rect = pg.Rect(x - w_px // 2, y, w_px, 22)
        color = _VEHICLE_COLORS.get(v.type.value, _VEHICLE_COLORS["car"])
        pg.draw.rect(s, color, rect)
        # Emergency vehicles get a flashy outline.
        if v.is_emergency:
            pg.draw.rect(s, (255, 255, 255), rect, 2)

    def _draw_lights(self, world: World, phase: Phase) -> None:
        pg = self._pygame
        s = self._screen
        h = self.settings.window_height
        # Light A is on the left edge of the work zone, light B on the right.
        cx_a = self._x_to_px(world.camera_x_a, world)
        cx_b = self._x_to_px(world.camera_x_b, world)
        for cx, side in ((cx_a, Side.A), (cx_b, Side.B)):
            color = self._light_color(side, phase)
            pg.draw.rect(s, (40, 40, 40), (cx - 8, h // 2 - 110, 16, 30))
            pg.draw.circle(s, color, (cx, h // 2 - 95), 8)

    def _light_color(self, side: Side, phase: Phase) -> tuple[int, int, int]:
        if phase in (Phase.YELLOW, Phase.YELLOW_A, Phase.YELLOW_B):
            return _COLOR_LIGHT_YELLOW
        if phase in (Phase.ALL_RED, Phase.ALL_RED_AFTER_A, Phase.ALL_RED_AFTER_B, Phase.RED_BOTH, Phase.EMERGENCY_STOP, Phase.INIT):
            return _COLOR_LIGHT_RED
        if phase is Phase.GREEN_A and side is Side.A:
            return _COLOR_LIGHT_GREEN
        if phase is Phase.GREEN_B and side is Side.B:
            return _COLOR_LIGHT_GREEN
        return _COLOR_LIGHT_RED

    def _draw_hud(
        self,
        world: World,
        phase: Phase,
        mode: str,
        scenario: str,
        metrics: dict,
        events_published: int,
    ) -> None:
        s = self._screen
        lines = [
            f"scenario={scenario}  mode={mode}  phase={phase.value}",
            f"queue A={metrics['queue']['A']:>3}  B={metrics['queue']['B']:>3}    "
            f"inside A={world.inside_counts()[0]}  B={world.inside_counts()[1]}",
            f"throughput 5min A={metrics['throughput_5min']['A']:>3}  "
            f"B={metrics['throughput_5min']['B']:>3}    "
            f"avg_delay A={metrics['avg_delay_5min']['A']:.1f}s  "
            f"B={metrics['avg_delay_5min']['B']:.1f}s",
            f"published events={events_published}",
        ]
        y = 8
        for line in lines:
            surf = self._font.render(line, True, _COLOR_TEXT)
            s.blit(surf, (12, y))
            y += 18

    # ------------------------------------------------------------ teardown
    def quit(self) -> None:
        try:
            self._pygame.quit()
        except Exception:  # noqa: BLE001
            log.exception("pygame teardown failed")

    def pump(self) -> bool:
        """Pump events. Returns False if the user closed the window."""
        if self.headless:
            return True
        for evt in self._pygame.event.get():
            if evt.type == self._pygame.QUIT:
                return False
        return True
