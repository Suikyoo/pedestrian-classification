from pathlib import Path

from master.settings import Settings


def test_defaults_without_env_file(monkeypatch):
    for key in ("MQTT_USER", "MQTT_PASS", "PEDESTRIAN_CONF_THRESHOLD"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.mqtt_host == "127.0.0.1"
    assert s.mqtt_port == 1883
    assert s.mqtt_user == ""
    assert s.mqtt_pass == ""
    assert s.model_path == "yolo11n.pt"
    assert s.device == "cpu"
    assert s.pedestrian_conf_threshold == 0.6
    assert not hasattr(s, "alert_dwell_seconds")
    assert s.events_dir == Path("./events")


def test_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PEDESTRIAN_CONF_THRESHOLD=0.5\nALERT_DWELL_SECONDS=8\nMQTT_USER=server\nMQTT_PASS=\n",
                   encoding="utf-8")
    s = Settings(_env_file=env)  # an old .env with dwell settings still loads
    assert s.pedestrian_conf_threshold == 0.5
    assert s.mqtt_user == "server"
    assert s.mqtt_pass == ""


def test_dashboard_defaults():
    s = Settings(_env_file=None)
    assert s.inference_history == 200
    assert s.web_host == "0.0.0.0"
    assert s.web_port == 8000


def test_verify_defaults_without_env_file(monkeypatch):
    for key in ("PEDESTRIAN_VERIFY_THRESHOLD", "PEDESTRIAN_VERIFY_DWELL_S",
                "PEDESTRIAN_VERIFY_MAX_GAP_S", "PEDESTRIAN_VERIFY_ALERT_COOLDOWN_S"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.pedestrian_verify_threshold == 0.8
    assert s.pedestrian_verify_dwell_s == 5.0
    assert s.pedestrian_verify_max_gap_s == 3.0
    assert s.pedestrian_verify_alert_cooldown_s == 5.0


def test_verify_reads_env(monkeypatch):
    monkeypatch.setenv("PEDESTRIAN_VERIFY_THRESHOLD", "0.9")
    monkeypatch.setenv("PEDESTRIAN_VERIFY_DWELL_S", "6.0")
    monkeypatch.setenv("PEDESTRIAN_VERIFY_MAX_GAP_S", "2.0")
    monkeypatch.setenv("PEDESTRIAN_VERIFY_ALERT_COOLDOWN_S", "7.0")
    s = Settings(_env_file=None)
    assert s.pedestrian_verify_threshold == 0.9
    assert s.pedestrian_verify_dwell_s == 6.0
    assert s.pedestrian_verify_max_gap_s == 2.0
    assert s.pedestrian_verify_alert_cooldown_s == 7.0
