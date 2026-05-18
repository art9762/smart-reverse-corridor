"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Variable names match `.env.example` at the repo root. Unknown env vars
    are ignored to keep the controller forward-compatible.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # MQTT
    mqtt_host: str = Field(default="mosquitto", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    mqtt_ws_port: int = Field(default=9001, alias="MQTT_WS_PORT")
    mqtt_user: Optional[str] = Field(default=None, alias="MQTT_USER")
    mqtt_pass: Optional[str] = Field(default=None, alias="MQTT_PASS")
    mqtt_client_id: str = Field(default="controller", alias="MQTT_CLIENT_ID")

    # Controller
    controller_host: str = Field(default="0.0.0.0", alias="CONTROLLER_HOST")
    controller_port: int = Field(default=8000, alias="CONTROLLER_PORT")
    controller_log_level: str = Field(default="INFO", alias="CONTROLLER_LOG_LEVEL")

    zone_length_m: int = Field(default=800, alias="ZONE_LENGTH_M")
    green_min_s: int = Field(default=15, alias="GREEN_MIN_S")
    green_max_s: int = Field(default=240, alias="GREEN_MAX_S")
    yellow_s: int = Field(default=3, alias="YELLOW_S")
    all_red_guard_s: int = Field(default=5, alias="ALL_RED_GUARD_S")
    clear_timeout_s: int = Field(default=60, alias="CLEAR_TIMEOUT_S")

    # Adaptive scheduler weights
    prio_w_queue: float = Field(default=1.0, alias="PRIO_W_QUEUE")
    prio_w_wait: float = Field(default=0.05, alias="PRIO_W_WAIT")
    prio_w_truck: float = Field(default=0.5, alias="PRIO_W_TRUCK")
    prio_w_other_empty: float = Field(default=2.0, alias="PRIO_W_OTHER_EMPTY")
    base_green_s: int = Field(default=20, alias="BASE_GREEN_S")

    # Watchdogs
    stuck_threshold_s: int = Field(default=30, alias="STUCK_THRESHOLD_S")
    heartbeat_timeout_s: int = Field(default=5, alias="HEARTBEAT_TIMEOUT_S")

    # InfluxDB (optional)
    influx_url: Optional[str] = Field(default=None, alias="INFLUX_URL")
    influx_token: Optional[str] = Field(default=None, alias="INFLUX_TOKEN")
    influx_org: Optional[str] = Field(default=None, alias="INFLUX_ORG")
    influx_bucket: Optional[str] = Field(default=None, alias="INFLUX_BUCKET")

    # SQLite
    sqlite_path: str = Field(default="/app/data/controller.db", alias="SQLITE_PATH")

    # Mode
    default_mode: str = Field(default="adaptive", alias="DEFAULT_MODE")  # adaptive|baseline


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
