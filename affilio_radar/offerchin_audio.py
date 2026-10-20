"""Generate an original, dependency-free upbeat instrumental bed for OfferChin shorts."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def write_original_soundtrack(
    output_path: str | Path,
    duration_seconds: float,
    *,
    sample_rate: int = 22050,
) -> Path:
    """Write a short original electronic jingle as stereo PCM WAV.

    The tune and rhythm are procedurally synthesized from oscillators; no sampled
    commercial recording, recognizable song, or third-party music asset is used.
    """
    target = Path(output_path)
    duration = max(5.0, min(12.0, float(duration_seconds)))
    rate = max(16000, min(44100, int(sample_rate)))
    frames = int(round(duration * rate))
    # Faster, bright pop/electronic tempo for a punchier shopping-short feel.
    bpm = 142.0
    beat_seconds = 60.0 / bpm
    eighth_seconds = beat_seconds / 2.0

    # A brighter major-key hook with a quick, memorable rise-and-fall contour.
    lead_notes = (
        659.25, 739.99, 880.00, 987.77,
        880.00, 739.99, 659.25, 554.37,
        659.25, 739.99, 880.00, 987.77,
        1108.73, 987.77, 880.00, 659.25,
    )
    chord_notes = (
        (220.00, 277.18, 329.63),  # A major
        (164.81, 207.65, 246.94),  # E major
        (185.00, 220.00, 277.18),  # F-sharp minor
        (146.83, 185.00, 220.00),  # D major
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        block = bytearray()

        for index in range(frames):
            t = index / rate
            beat_index = int(t / beat_seconds)
            beat_phase = t - beat_index * beat_seconds
            half_index = int(t / eighth_seconds)
            half_phase = t - half_index * eighth_seconds

            kick = 0.0
            if beat_phase < 0.18:
                kick_phase = beat_phase
                swept_cycles = 47.0 * kick_phase + 9.0 * (1.0 - math.exp(-25.0 * kick_phase)) / 25.0
                kick = 0.46 * math.exp(-29.0 * kick_phase) * math.sin(2.0 * math.pi * swept_cycles)

            bass_root = (55.00, 82.41, 46.25, 73.42)[(beat_index // 4) % 4]
            bass = 0.125 * math.sin(2.0 * math.pi * bass_root * t)
            bass += 0.045 * math.sin(2.0 * math.pi * bass_root * 2.0 * t)

            snare = 0.0
            if beat_index % 4 in (1, 3) and beat_phase < 0.12:
                snare_env = math.exp(-34.0 * beat_phase)
                snare = snare_env * (
                    0.112 * math.sin(2.0 * math.pi * 185.0 * beat_phase)
                    + 0.065 * math.sin(2.0 * math.pi * 1400.0 * beat_phase)
                    + 0.035 * math.sin(2.0 * math.pi * 3100.0 * beat_phase)
                )

            hat = 0.0
            if half_phase < 0.027:
                hat_env = math.exp(-115.0 * half_phase)
                hat = 0.047 * hat_env * (
                    math.sin(2.0 * math.pi * 7200.0 * half_phase)
                    + 0.42 * math.sin(2.0 * math.pi * 9700.0 * half_phase)
                )

            note_index = half_index % len(lead_notes)
            note = lead_notes[note_index]
            lead_env = math.exp(-7.4 * half_phase)
            lead = 0.128 * lead_env * (
                math.sin(2.0 * math.pi * note * half_phase)
                + 0.27 * math.sin(2.0 * math.pi * note * 2.0 * half_phase)
            )

            chord = chord_notes[(beat_index // 4) % len(chord_notes)]
            pad_env = 0.8 + 0.2 * math.sin(2.0 * math.pi * t / 2.0)
            pad = 0.022 * pad_env * sum(
                math.sin(2.0 * math.pi * frequency * t) for frequency in chord
            )

            fade_in = min(1.0, t / 0.16)
            fade_out = min(1.0, max(0.0, (duration - t) / 0.36))
            master = fade_in * fade_out
            center = (kick + bass + snare + hat + pad) * master
            pan = 0.5 + 0.20 * math.sin(2.0 * math.pi * t / 2.8)
            left = max(-0.92, min(0.92, (center + lead * (1.0 - pan)) * 0.91))
            right = max(-0.92, min(0.92, (center + lead * pan) * 0.91))
            block.extend(struct.pack("<hh", int(left * 32767), int(right * 32767)))

            if len(block) >= 65536:
                wav.writeframesraw(block)
                block.clear()

        if block:
            wav.writeframesraw(block)
        wav.writeframes(b"")

    if not target.is_file() or target.stat().st_size < rate:
        raise RuntimeError("Original soundtrack generation produced an empty audio file")
    return target
