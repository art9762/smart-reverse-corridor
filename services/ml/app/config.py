"""Centralized config loaded from environment.

All ML_* variables are documented in repo-root `.env.example`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Environment variables override defaults. Names match `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- MQTT ----
    mqtt_host: str = Field(default="mosquitto", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    mqtt_user: Optional[str] = Field(default=None, alias="MQTT_USER")
    mqtt_pass: Optional[str] = Field(default=None, alias="MQTT_PASS")
    mqtt_client_id: str = Field(default="ml-cv", alias="MQTT_CLIENT_ID")

    # ---- ML / Model ----
    ml_model: str = Field(default="yolov8n.pt", alias="ML_MODEL")
    ml_conf: float = Field(default=0.35, alias="ML_CONF")
    ml_iou: float = Field(default=0.5, alias="ML_IOU")
    ml_device: str = Field(default="cpu", alias="ML_DEVICE")
    ml_imgsz: int = Field(default=640, alias="ML_IMGSZ")

    # ---- Video sources ----
    ml_video_a_in: str = Field(default="/data/cam_A_in.mp4", alias="ML_VIDEO_A_IN")
    ml_video_a_out: str = Field(default="/data/cam_A_out.mp4", alias="ML_VIDEO_A_OUT")
    ml_video_b_in: str = Field(default="/data/cam_B_in.mp4", alias="ML_VIDEO_B_IN")
    ml_video_b_out: str = Field(default="/data/cam_B_out.mp4", alias="ML_VIDEO_B_OUT")

    # ---- Calibration ----
    ml_calibration_path: str = Field(
        default="/app/app/calibration.json",
        alias="ML_CALIBRATION_PATH",
    )

    # ---- Loop & heartbeat ----
    ml_loop_video: bool = Field(default=True, alias="ML_LOOP_VIDEO")
    ml_heartbeat_interval_s: float = Field(
        default=1.0, alias="ML_HEARTBEAT_INTERVAL_S"
    )

    # ---- Emergency vehicle heuristic ----
    ml_emergency_hsv: bool = Field(default=False, alias="ML_EMERGENCY_HSV")

    @property
    def cameras(self) -> dict[str, str]:
        """Map camera_id -> video source path/URL."""
        return {
            "A_in": self.ml_video_a_in,
            "A_out": self.ml_video_a_out,
            "B_in": self.ml_video_b_in,
            "B_out": self.ml_video_b_out,
        }


def get_settings() -> Settings:
    """Return a fresh Settings instance (kept simple for tests)."""
    return Settings()
