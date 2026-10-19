"""生成开场片原创电子配乐；只有显式调用时才计算、写文件。"""

from __future__ import annotations

import wave
from pathlib import Path


def synthesize(path: Path, duration: float = 40, sample_rate: int = 48000) -> None:
    """原创音符合成、节拍与转场音效，无采样素材或人声。"""
    import numpy as np

    rng = np.random.default_rng(20261019)
    sound = np.zeros((round(duration * sample_rate), 2), dtype=np.float32)

    def add(start, samples, gain=1, pan=0):
        offset = round(start * sample_rate)
        count = min(len(samples), len(sound) - offset)
        if count > 0:
            sound[offset : offset + count, 0] += samples[:count] * gain * (1 - pan) ** 0.5
            sound[offset : offset + count, 1] += samples[:count] * gain * (1 + pan) ** 0.5

    def time(seconds):
        return np.arange(round(seconds * sample_rate), dtype=np.float32) / sample_rate

    def frequency(note):
        return 440 * 2 ** ((note - 69) / 12)

    chords = [
        (50, 57, 62, 65, 69),
        (46, 53, 58, 62, 65),
        (53, 60, 65, 69, 72),
        (48, 55, 60, 64, 67),
    ]
    for section in range(10):
        t = time(5.5)
        envelope = np.minimum(t / 1.2, 1) * np.exp(-t / 4) * np.minimum((5.5 - t) / 1.6, 1)
        for voice, note in enumerate(chords[section % 4]):
            f = frequency(note)
            pad = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 1.003 * t)
            add(section * 4, pad * envelope, 0.023, (voice - 2) / 4)
    for step in range(round(duration * 4)):
        start = step / 4
        chord = chords[int(start // 4) % 4]
        note = chord[[2, 3, 4, 3, 2, 4, 3, 4][step % 8]] + 12
        t = time(0.9)
        f = frequency(note)
        pluck = np.sin(2 * np.pi * f * t) + 0.24 * np.sin(4 * np.pi * f * t)
        pluck *= (1 - np.exp(-t * 170)) * np.exp(-t * 9)
        level = 0.025 if start < 4 else 0.049
        pan = 0.45 * np.sin(step * 1.8)
        add(start, pluck, level, pan)
        add(start + 0.375, pluck, level * 0.27, -pan)
        if 4 <= start < 35 and step % 2 == 0:
            t = time(0.42)
            phase = 2 * np.pi * (43 * t + 75 * (1 - np.exp(-t * 26)) / 26)
            kick = np.sin(phase) * np.exp(-t * 12) * np.minimum(t * 300, 1)
            add(start, kick, 0.13)
        if 10 <= start < 35:
            t = time(0.075)
            noise = rng.normal(size=len(t)).astype(np.float32)
            hat = np.r_[0, np.diff(noise)] * np.exp(-t * 75) * np.minimum(t * 800, 1)
            add(start, hat, 0.007 if step % 2 else 0.012, (-1) ** step * 0.4)
    for transition in (0, 4, 10, 16, 23, 29, 35):
        t = time(1.4)
        noise = rng.normal(size=len(t)).astype(np.float32)
        spectrum = np.fft.rfft(noise)
        frequencies = np.fft.rfftfreq(len(t), 1 / sample_rate)
        spectrum *= np.exp(-(((frequencies - 1600) / 1800) ** 2)) * (frequencies > 200)
        air = np.fft.irfft(spectrum, n=len(t)).astype(np.float32)
        envelope = np.sin(np.pi * t / 1.4) ** 2
        add(max(0, transition - 0.65), air * envelope, 0.045, -0.2)
        t = time(1.8)
        impact = np.sin(2 * np.pi * (35 * t + 24 * (1 - np.exp(-t * 7)) / 7))
        add(transition, impact * np.exp(-t * 3) * np.minimum(t * 150, 1), 0.11)
    t = np.arange(len(sound), dtype=np.float32) / sample_rate
    sound *= (np.minimum(t / 0.8, 1) * np.clip((duration - t - 0.15) / 2.6, 0, 1))[:, None]
    sound *= 0.76 / max(float(np.max(np.abs(sound))), 1e-6)
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, sample_rate, 0, "NONE", "not compressed"))
        output.writeframes((sound * 32767).astype("<i2").tobytes())
