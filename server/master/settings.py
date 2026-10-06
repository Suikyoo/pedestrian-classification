from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration, read from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    model_path: str = "yolo11n.pt"
    device: str = "cpu"
    pedestrian_conf_threshold: float = 0.6
    alert_dwell_seconds: float = 5.0
    max_gap_seconds: float = 3.0
    alert_cooldown_seconds: float = 30.0
    events_dir: Path = Path("./events")
    inference_history: int = 200
    web_host: str = "0.0.0.0"
    web_port: int = 8000
