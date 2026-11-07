"""Generate OfferChin's original 12-second funk / nu-disco product-ad groove.

The arrangement follows the funk groove selected from the private fuse-box preview,
but every sound is synthesized here from elementary oscillators and seeded noise.
No third-party recording, SoundFont, or external audio file is required.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from array import array
from pathlib import Path

TAU = 2.0 * math.pi


def _hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((int(midi_note) - 69) / 12.0))


def _pan_gains(pan: float) -> tuple[float, float]:
    pan = max(-1.0, min(1.0, float(pan)))
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def _add_note(
    left: array,
    right: array,
    sample_rate: int,
    start: float,
    duration: float,
    note: int,
    velocity: int,
    voice: str,
    pan: float = 0.0,
    seed: int = 0,
) -> None:
    start_frame = max(0, int(round(start * sample_rate)))
    end_frame = min(len(left), int(round((start + duration) * sample_rate)))
    if end_frame <= start_frame:
        return

    hz = _hz(note)
    peak = max(0.0, min(1.0, velocity / 127.0))
    lg, rg = _pan_gains(pan)
    length = (end_frame - start_frame) / sample_rate
    phase_seed = (seed % 97) / 97.0 * TAU

    if voice == "bass":
        attack, decay, release = 0.006, 3.6, 0.055
        harmonics = ((1, 0.68), (2, 0.30), (3, 0.13), (4, 0.055), (5, 0.02))
        pitch_bloom = 0.08
    elif voice == "guitar":
        attack, decay, release = 0.003, 15.0, 0.035
        harmonics = ((1, 0.62), (2, 0.48), (3, 0.24), (4, 0.12), (6, 0.045))
        pitch_bloom = 0.0
    elif voice == "clav":
        attack, decay, release = 0.002, 12.5, 0.025
        harmonics = ((1, 0.58), (2, 0.58), (3, 0.30), (4, 0.20), (5, 0.10), (7, 0.035))
        pitch_bloom = 0.0
    elif voice == "brass":
        attack, decay, release = 0.022, 5.0, 0.075
        harmonics = ((1, 0.70), (2, 0.38), (3, 0.22), (4, 0.12), (5, 0.06))
        pitch_bloom = 0.0
    elif voice == "lead":
        attack, decay, release = 0.008, 4.8, 0.055
        harmonics = ((1, 0.72), (2, 0.34), (3, 0.16), (4, 0.075))
        pitch_bloom = 0.0
    elif voice == "bell":
        attack, decay, release = 0.002, 3.0, 0.11
        harmonics = ((1, 0.82), (2, 0.32), (3, 0.18), (4, 0.08), (6, 0.025))
        pitch_bloom = 0.0
    else:
        raise ValueError(f"unsupported synthesized voice: {voice}")

    norm = sum(weight for _, weight in harmonics)
    for frame in range(start_frame, end_frame):
        t = (frame - start_frame) / sample_rate
        attack_env = min(1.0, t / max(0.001, attack))
        release_env = min(1.0, max(0.0, (length - t) / max(0.001, release)))
        env = attack_env * release_env * math.exp(-decay * t)

        # A restrained downward pitch bloom gives the plucked bass a less static edge.
        phase = TAU * hz * (t + pitch_bloom * 0.028 * (1.0 - math.exp(-t / 0.028)))
        if voice == "lead":
            phase += 0.018 * math.sin(TAU * 5.2 * t)
        elif voice == "brass":
            phase += 0.008 * math.sin(TAU * 4.0 * t)

        tone = 0.0
        for multiple, weight in harmonics:
            tone += weight * math.sin(phase * multiple + phase_seed * multiple)

        # A tiny pick transient on plucked instruments, synthesized rather than sampled.
        transient = 0.0
        if voice in {"guitar", "clav"} and t < 0.018:
            transient = 0.075 * math.exp(-t * 190.0) * math.sin(
                TAU * (2400.0 + 250.0 * math.sin(TAU * 31.0 * t)) * t
            )

        value = peak * (tone / norm + transient) * env * 0.21
        left[frame] += value * lg
        right[frame] += value * rg


def _add_kick(left: array, right: array, sample_rate: int, start: float, velocity: int) -> None:
    first = max(0, int(start * sample_rate))
    last = min(len(left), first + int(0.19 * sample_rate))
    amp = min(1.0, velocity / 127.0)
    for frame in range(first, last):
        t = (frame - first) / sample_rate
        phase = TAU * (48.0 * t + 78.0 * (1.0 - math.exp(-t * 28.0)) / 28.0)
        body = math.sin(phase) + 0.18 * math.sin(phase * 2.0)
        value = amp * 0.39 * math.exp(-t * 22.0) * body
        left[frame] += value * 0.72
        right[frame] += value * 0.72


def _add_snare(left: array, right: array, sample_rate: int, start: float, velocity: int, rng: random.Random) -> None:
    first = max(0, int(start * sample_rate))
    last = min(len(left), first + int(0.16 * sample_rate))
    amp = min(1.0, velocity / 127.0)
    previous = 0.0
    for frame in range(first, last):
        t = (frame - first) / sample_rate
        raw = rng.uniform(-1.0, 1.0)
        high = raw - previous * 0.82
        previous = raw
        body = 0.30 * math.sin(TAU * 185.0 * t) + 0.70 * high
        value = amp * 0.16 * math.exp(-t * 27.0) * body
        left[frame] += value * 0.74
        right[frame] += value * 0.74


def _add_hat(left: array, right: array, sample_rate: int, start: float, velocity: int, rng: random.Random, pan: float) -> None:
    first = max(0, int(start * sample_rate))
    last = min(len(left), first + int(0.045 * sample_rate))
    amp = min(1.0, velocity / 127.0)
    previous = 0.0
    lg, rg = _pan_gains(pan)
    for frame in range(first, last):
        t = (frame - first) / sample_rate
        raw = rng.uniform(-1.0, 1.0)
        high = raw - previous * 0.9
        previous = raw
        value = amp * 0.075 * math.exp(-t * 95.0) * high
        left[frame] += value * lg
        right[frame] += value * rg


def write_original_soundtrack(
    output_path: str | Path,
    duration_seconds: float,
    *,
    sample_rate: int = 22050,
) -> Path:
    """Write the selected original funk / nu-disco advertising groove as stereo PCM WAV.

    The arrangement echoes the private fuse-box preview: plucked bass, muted guitar
    and clavinet off-beats, occasional brass accents, syncopated drums, a compact
    melodic hook, and the three-note OfferChin signature. All sounds are generated
    here from oscillators and seeded noise; no third-party sample library is loaded.
    """
    target = Path(output_path)
    duration = max(5.0, min(12.0, float(duration_seconds)))
    rate = max(16000, min(44100, int(sample_rate)))
    frames = int(round(duration * rate))
    left = array("f", [0.0]) * frames
    right = array("f", [0.0]) * frames

    bpm = 116.0
    beat = 60.0 / bpm
    bar = beat * 4.0
    rng = random.Random(20261107)

    # Original three-note signature, repeated at the close as in the selected demo.
    signature = (
        (0.06, 76, 76), (0.22, 80, 84), (0.40, 83, 96),
        (10.72, 76, 68), (10.90, 80, 77), (11.10, 83, 90),
    )
    for index, (at, note, velocity) in enumerate(signature):
        _add_note(left, right, rate, at, 0.24, note, velocity, "bell", pan=0.10, seed=index + 11)

    chords = (
        (45, (57, 60, 64, 67)),  # A minor 7 colour
        (41, (53, 57, 60, 64)),  # F major 7 colour
        (43, (55, 59, 62, 65)),  # G dominant colour
        (38, (50, 53, 57, 60)),  # D minor colour
        (45, (57, 60, 64, 67)),
    )

    # Five bars of syncopated rhythm leave room for a clear branded ending.
    for bar_index, (root, chord) in enumerate(chords):
        offset = bar_index * bar
        bass_pattern = (0.0, 0.75, 1.5, 2.0, 2.75, 3.5)
        for note_index, beat_offset in enumerate(bass_pattern):
            pitch = root + (12 if note_index == 3 else 0)
            velocity = 105 if note_index in (0, 3) else (72 if note_index == 2 else 84)
            _add_note(
                left, right, rate, offset + beat_offset * beat, beat * 0.34,
                pitch, velocity, "bass", pan=-0.06, seed=bar_index * 20 + note_index,
            )

        # Muted guitar off-beat chord chops.
        for hit_index, beat_offset in enumerate((0.5, 1.5, 2.5, 3.5)):
            for chord_index, pitch in enumerate(chord[:3]):
                _add_note(
                    left, right, rate, offset + beat_offset * beat, 0.12,
                    pitch + 12, 58 + chord_index * 3, "guitar", pan=-0.28,
                    seed=bar_index * 31 + hit_index * 3 + chord_index,
                )

        # Clavinet answers the guitar with a sharper syncopation.
        for hit_index, beat_offset in enumerate((0.75, 2.75)):
            for chord_index, pitch in enumerate(chord[:3]):
                _add_note(
                    left, right, rate, offset + beat_offset * beat, 0.16,
                    pitch + 24, 70 + chord_index * 2, "clav", pan=0.25,
                    seed=bar_index * 41 + hit_index * 3 + chord_index,
                )

        # Brass punctuations on alternating bars, not a constant wall of sound.
        if bar_index in (1, 3):
            for chord_index, pitch in enumerate(chord[:3]):
                _add_note(
                    left, right, rate, offset + 2.0 * beat, beat * 0.25,
                    pitch + 12, 65 + chord_index * 2, "brass", pan=0.08,
                    seed=bar_index * 17 + chord_index,
                )

        # Snare backbeat and syncopated kick; hats carry a subtle 8th-note motion.
        for beat_index in range(4):
            at = offset + beat_index * beat
            if beat_index in (0, 2):
                _add_kick(left, right, rate, at, 106 if beat_index == 0 else 88)
            else:
                _add_snare(left, right, rate, at, 90, rng)
            _add_hat(left, right, rate, at, 66 if beat_index % 2 == 0 else 58, rng, -0.34)
            _add_hat(left, right, rate, at + beat * 0.5, 50, rng, 0.34)
        if bar_index in (1, 3):
            _add_snare(left, right, rate, offset + 3.5 * beat, 55, rng)

    # Three repeated passes of a compact melodic hook.
    hook = (81, 84, 86, 88, 86, 84, 81, 79)
    for repeat in range(3):
        for index, note in enumerate(hook):
            at = 0.90 + repeat * (2.0 * bar) + index * beat * 0.5
            _add_note(
                left, right, rate, at, beat * 0.24, note,
                75 if index % 4 else 91, "lead", pan=0.16, seed=repeat * 13 + index,
            )

    # A subtle stereo echo adds space without introducing an external effect.
    delay = int(rate * 0.075)
    for frame in range(delay, frames):
        left[frame] += right[frame - delay] * 0.045
        right[frame] += left[frame - delay] * 0.045

    # Smooth fade and gentle saturation; never allow clipping in the final PCM.
    fade_in = max(1, int(rate * 0.035))
    fade_out = max(1, int(rate * 0.52))
    peak = 0.0
    for frame in range(frames):
        t = frame / rate
        env = min(1.0, t / (fade_in / rate))
        if frame >= frames - fade_out:
            env *= max(0.0, (frames - frame) / fade_out)
        sample_left = math.tanh(left[frame] * env * 1.55) / math.tanh(1.55)
        sample_right = math.tanh(right[frame] * env * 1.55) / math.tanh(1.55)
        left[frame] = sample_left
        right[frame] = sample_right
        peak = max(peak, abs(sample_left), abs(sample_right))

    normalizer = 0.88 / peak if peak > 0.88 else 1.0
    target.parent.mkdir(parents=True, exist_ok=True)
    block = bytearray()
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for frame in range(frames):
            sample_left = int(max(-1.0, min(1.0, left[frame] * normalizer)) * 32767)
            sample_right = int(max(-1.0, min(1.0, right[frame] * normalizer)) * 32767)
            block.extend(struct.pack("<hh", sample_left, sample_right))
            if len(block) >= 65536:
                wav.writeframesraw(block)
                block.clear()
        if block:
            wav.writeframesraw(block)
        wav.writeframes(b"")

    if not target.is_file() or target.stat().st_size < rate:
        raise RuntimeError("Original funk soundtrack generation produced an empty audio file")
    return target
