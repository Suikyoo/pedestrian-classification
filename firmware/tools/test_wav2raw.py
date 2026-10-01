import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import wav2raw  # noqa: E402


def test_to_u8_maps_range():
    assert wav2raw.to_u8([0.0, 1.0, -1.0, 2.0, -2.0]) == bytes([128, 255, 1, 255, 1])


def _write_wav(path, rate, channels, frames):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<" + "h" * channels, *f) for f in frames))


def test_read_wav_mixes_to_mono_and_resamples(tmp_path):
    path = tmp_path / "in.wav"
    # 8 kHz stereo, 100 frames: left full positive, right silent -> mono 0.5
    _write_wav(path, 8000, 2, [(32767, 0)] * 100)
    samples = wav2raw.read_wav(path)
    assert len(samples) == 200
    assert all(abs(s - 0.5) < 0.01 for s in samples)


def test_demo_length_and_range():
    samples = wav2raw.demo(1.2)
    assert len(samples) == int(1.2 * wav2raw.RATE)
    assert max(samples) <= 1.0 and min(samples) >= -1.0
    assert max(samples) > 0.5


def test_cli_demo_writes_raw(tmp_path):
    out = tmp_path / "alert.raw"
    wav2raw.main(["--demo", str(out)])
    assert out.stat().st_size == int(1.2 * wav2raw.RATE)
