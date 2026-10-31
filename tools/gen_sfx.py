"""用纯 Python 合成游戏音效（不需要任何素材，可随项目开源）。

用法：python tools/gen_sfx.py
输出：web/audio/sfx_*.wav（22.05kHz 单声道）
"""

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "web" / "audio"


def tone(freq, dur, vol=0.5, wave_type="sine", attack=0.005, decay=None, slide=0.0, vibrato=0.0):
    """单个音：可选波形、起音、指数衰减、滑音、颤音。"""
    n = int(RATE * dur)
    decay = dur if decay is None else decay
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = freq * (1 + slide * t / dur) * (1 + vibrato * math.sin(2 * math.pi * 6 * t))
        phase += 2 * math.pi * f / RATE
        if wave_type == "sine":
            s = math.sin(phase)
        elif wave_type == "square":
            s = 1.0 if math.sin(phase) >= 0 else -1.0
            s *= 0.5
        elif wave_type == "tri":
            s = 2 / math.pi * math.asin(math.sin(phase))
        elif wave_type == "noise":
            s = random.uniform(-1, 1)
        else:
            s = math.sin(phase) + 0.3 * math.sin(2 * phase) + 0.15 * math.sin(3 * phase)
            s /= 1.45
        env = min(1.0, t / attack) * math.exp(-4.0 * t / decay)
        out.append(s * env * vol)
    return out


def mix(*tracks, offsets=None):
    offsets = offsets or [0.0] * len(tracks)
    length = max(int(o * RATE) + len(t) for t, o in zip(tracks, offsets))
    buf = [0.0] * length
    for t, o in zip(tracks, offsets):
        start = int(o * RATE)
        for i, s in enumerate(t):
            buf[start + i] += s
    return buf


def seq(notes, gap, **kw):
    """依次播放的一串音：notes 是频率列表。"""
    return mix(*[tone(f, kw.pop("dur", 0.18) if False else kw.get("dur", 0.18), **{k: v for k, v in kw.items() if k != "dur"})
                 for f in notes], offsets=[i * gap for i in range(len(notes))])


def save(name, samples):
    peak = max(1e-6, max(abs(s) for s in samples))
    scale = 0.9 / peak if peak > 0.9 else 1.0
    with wave.open(str(OUT / f"sfx_{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s * scale)) * 32767)) for s in samples))


def main() -> None:
    random.seed(7)
    OUT.mkdir(parents=True, exist_ok=True)
    N = {"C5": 523.3, "D5": 587.3, "E5": 659.3, "G5": 784.0, "A5": 880.0, "C6": 1046.5, "E6": 1318.5,
         "G4": 392.0, "C4": 261.6, "E4": 329.6, "A3": 220.0, "F4": 349.2}
    save("tap", tone(900, 0.05, 0.35, "tri", decay=0.03))
    save("door", mix(tone(N["E6"], 0.6, 0.35, "rich", decay=0.5), tone(N["C6"], 0.7, 0.3, "rich", decay=0.6), offsets=[0, 0.12]))
    save("clue", mix(tone(0, 0.12, 0.25, "noise", decay=0.06), tone(N["A5"], 0.25, 0.3, "sine", decay=0.2), offsets=[0, 0.05]))
    save("coin", mix(tone(0, 0.08, 0.3, "noise", decay=0.04), tone(N["E6"], 0.35, 0.35, "rich", decay=0.3),
                     tone(N["G5"] * 2, 0.45, 0.3, "rich", decay=0.4), offsets=[0, 0.04, 0.1]))
    save("stamp", mix(tone(90, 0.18, 0.7, "sine", slide=-0.5, decay=0.12), tone(0, 0.08, 0.4, "noise", decay=0.04)))
    save("counter", seq([N["G4"], N["E4"]], 0.1, dur=0.15, vol=0.3, wave_type="tri", decay=0.12))
    save("angry", tone(160, 0.35, 0.45, "square", vibrato=0.08, slide=-0.3, decay=0.3))
    save("leave", seq([N["E4"], N["C4"], N["A3"]], 0.13, dur=0.2, vol=0.3, wave_type="tri", decay=0.18))
    save("caught", seq([N["C5"], N["E5"], N["G5"], N["C6"]], 0.07, dur=0.25, vol=0.3, wave_type="square", decay=0.2))
    save("notify", seq([N["G5"], N["C6"], N["G5"], N["C6"]], 0.11, dur=0.22, vol=0.32, wave_type="rich", decay=0.2))
    save("gift", mix(*[tone(f, 0.3, 0.22, "sine", decay=0.25) for f in (N["C6"], N["E6"], N["G5"] * 2, 2093)],
                     tone(0, 0.3, 0.15, "noise", decay=0.15), offsets=[0, 0.06, 0.12, 0.18, 0]))
    save("bad_gift", seq([N["G4"], 370.0, 349.2, 311.1], 0.28, dur=0.35, vol=0.35, wave_type="square", vibrato=0.03, decay=0.32))
    save("day_end", seq([N["C5"], N["E5"], N["G5"], N["C6"], N["G5"], N["C6"]], 0.1, dur=0.3, vol=0.3, wave_type="rich", decay=0.25))
    save("lose", seq([N["G4"], N["F4"], N["E4"], N["C4"]], 0.3, dur=0.45, vol=0.35, wave_type="tri", decay=0.4))
    save("win", seq([N["C5"], N["E5"], N["G5"], N["C6"], N["E6"]], 0.12, dur=0.45, vol=0.3, wave_type="rich", decay=0.4))
    for f in sorted(OUT.glob("sfx_*.wav")):
        print(f.name, f.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
