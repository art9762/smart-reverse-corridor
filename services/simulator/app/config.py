"""Configuration for the reverse-corridor simulator.

Reads MQTT/world parameters from environment (with sensible defaults) so the
process is interchangeable with the real ML/CV service from the controller's
point of view: same MQTT broker, same topics, same payloads.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    """Runtime knobs for the simulator."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MQTT broker — matches .env.example contract.
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    mqtt_client_id: str = "simulator"

    # World geometry (metres).
    zone_length_m: float = 800.0
    approach_length_m: float = 200.0  # space for queue/approach on each side.
    lane_width_m: float = 3.5

    # Display (pixels). Independent of physical lengths — render scales.
    window_width: int = 1280
    window_height: int = 360

    # Simulation tick.
    fps: int = 30

    # Default speeds (km/h) — converted to m/s in code.
    car_speed_kmh: float = 60.0
    truck_speed_kmh: float = 40.0
    bus_speed_kmh: float = 50.0
    moto_speed_kmh: float = 70.0
    emergency_speed_kmh: float = 80.0

    # Vehicle lengths (m).
    car_length_m: float = 4.5
    truck_length_m: float = 12.0
    bus_length_m: float = 11.0
    moto_length_m: float = 2.0
    emergency_length_m: float = 5.5

    # Baseline phase timings (seconds).
    baseline_green_s: float = 180.0
    baseline_yellow_s: float = 3.0
    baseline_all_red_s: float = 5.0


def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
