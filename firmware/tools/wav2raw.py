"""Convert a WAV file to the firmware's alert clip: 8-bit unsigned mono PCM at 16 kHz.

    python tools/wav2raw.py input.wav main/assets/alert.raw
    python tools/wav2raw.py --demo main/assets/alert.raw     # synthesize a two-tone chime

Keep clips short: 16 KB per second of audio, embedded in the firmware image.
"""

import argparse
import math
import struct
import wave
from pathlib import Path

RATE = 16000


def to_u8(samples: list[float]) -> bytes:
    """Map floats in [-1, 1] to unsigned bytes with silence at 128 (clipped)."""
    out = bytearray()
    for s in samples:
        s = max(-1.0, min(1.0, s))
        out.append(128 + round(s * 127))
    return bytes(out)


def read_wav(path) -> list[float]:
    with wave.open(str(path), "rb") as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width == 1:
        values = [(b - 128) / 128 for b in raw]
    elif width == 2:
        values = [v / 32768 for v in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
    else:
        raise SystemExit(f"unsupported sample width {width * 8} bits; use 8 or 16-bit WAV")
    mono = [sum(values[i:i + channels]) / channels for i in range(0, len(values), channels)]
    if rate == RATE or not mono:
        return mono
    n_out = int(len(mono) * RATE / rate)
    out = []
    for i in range(n_out):
        t = i * rate / RATE
        j = int(t)
        frac = t - j
        a = mono[j]
        b = mono[j + 1] if j + 1 < len(mono) else a
        out.append(a + (b - a) * frac)
    return out


def demo(seconds: float = 1.2) -> list[float]:
    """Alternating 880/660 Hz tones, 150 ms each, with 5 ms fades to avoid clicks."""
    n = int(seconds * RATE)
    seg = int(0.15 * RATE)
    fade = int(0.005 * RATE)
    out = []
    for i in range(n):
        freq = 880 if (i // seg) % 2 == 0 else 660
        k = i % seg
        env = min(1.0, k / fade, (seg - k) / fade)
        out.append(0.9 * env * math.sin(2 * math.pi * freq * i / RATE))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="synthesize a chime instead of reading a WAV")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="[input.wav] output.raw")
    args = ap.parse_args(argv)
    if args.demo:
        if len(args.paths) != 1:
            ap.error("--demo takes only the output path")
        samples, out = demo(), Path(args.paths[0])
    else:
        if len(args.paths) != 2:
            ap.error("expected input.wav output.raw")
        samples, out = read_wav(args.paths[0]), Path(args.paths[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(to_u8(samples))
    print(f"wrote {out} ({len(samples)} samples, {len(samples) / RATE:.2f} s)")


if __name__ == "__main__":
    main()
