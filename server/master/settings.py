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
    # YOLO cutoff for stream-mode frames. Alerts are decided on each device.
    pedestrian_conf_threshold: float = 0.6
    # Host verification of device alert candidates (see the host-verified
    # alerts design): confirm cutoff, dwell window, gap that restarts the
    # window, and minimum time between host alert commands.
    pedestrian_verify_threshold: float = 0.8
    pedestrian_verify_dwell_s: float = 5.0
    pedestrian_verify_max_gap_s: float = 3.0
    pedestrian_verify_alert_cooldown_s: float = 5.0
    events_dir: Path = Path("./events")
    # When set, every received frame and event snapshot is also saved here, unmodified.
    dataset_dir: Path | None = None
    inference_history: int = 200
    # Admin page (/admin) sends commands and config to devices. Off while the password is empty.
    admin_user: str = "admin"
    admin_password: str = ""
    web_host: str = "0.0.0.0"
    web_port: int = 8000
