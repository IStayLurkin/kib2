from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import random
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

from core.config import (
    MUSIC_DEFAULT_QUALITY,
    MUSIC_PROVIDER,
    MUSIC_REQUEST_TIMEOUT_SECONDS,
    MUSIC_STUDIO_API_KEY,
    MUSIC_STUDIO_API_URL,
)
from core.feature_flags import MEDIA_OUTPUT_DIR


class MusicService:
    def __init__(self, performance_tracker=None) -> None:
        self.performance_tracker = performance_tracker
        self.output_dir = Path(MEDIA_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provider = MUSIC_PROVIDER
        self.studio_api_url = MUSIC_STUDIO_API_URL
        self.studio_api_key = MUSIC_STUDIO_API_KEY
        self.request_timeout_seconds = MUSIC_REQUEST_TIMEOUT_SECONDS
        self.default_quality = MUSIC_DEFAULT_QUALITY

    async def generate_melody(self, prompt: str) -> str:
        started_at = time.perf_counter()
        try:
            return await asyncio.to_thread(self._generate_melody_sync, prompt)
        finally:
            if self.performance_tracker is not None:
                self.performance_tracker.record_service_call(
                    "music.generate_melody",
                    (time.perf_counter() - started_at) * 1000,
                )

    async def generate_song_clip(
        self,
        vibe: str,
        bpm: int,
        voice_style: str,
        vocal_mode: str,
        quality_tier: str | None = None,
    ) -> str:
        started_at = time.perf_counter()
        try:
            effective_quality = (quality_tier or self.default_quality or "studio").strip().lower()
            if self._should_use_studio_provider():
                return await asyncio.to_thread(
                    self._generate_song_clip_studio_sync,
                    vibe,
                    bpm,
                    voice_style,
                    vocal_mode,
                    effective_quality,
                )
            return await asyncio.to_thread(
                self._generate_song_clip_sync,
                vibe,
                bpm,
                voice_style,
                vocal_mode,
            )
        finally:
            if self.performance_tracker is not None:
                self.performance_tracker.record_service_call(
                    "music.generate_song_clip",
                    (time.perf_counter() - started_at) * 1000,
                )

    def _generate_melody_sync(self, prompt: str) -> str:
        cleaned_prompt = prompt.strip() or "simple melody"
        profile = self._build_profile(cleaned_prompt)
        filename = f"melody_{uuid.uuid4().hex}.wav"
        path = self.output_dir / filename

        sample_rate = 44100
        notes = self._build_note_sequence(profile)
        audio = bytearray()

        for frequency, duration_seconds, amplitude in notes:
            total_samples = int(sample_rate * duration_seconds)
            for index in range(total_samples):
                envelope = min(1.0, index / (sample_rate * 0.02))
                release = min(1.0, (total_samples - index) / (sample_rate * 0.03))
                shaped_amplitude = amplitude * min(envelope, release)
                sample = 0.0
                if frequency > 0:
                    t = index / sample_rate
                    sample += math.sin(2 * math.pi * frequency * t) * 0.7
                    sample += math.sin(2 * math.pi * frequency * 2 * t) * 0.2
                    sample += math.sin(2 * math.pi * frequency * 0.5 * t) * 0.1
                pcm_value = int(max(-32767, min(32767, sample * shaped_amplitude)))
                audio.extend(pcm_value.to_bytes(2, byteorder="little", signed=True))

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(audio))

        return str(path)

    def _generate_song_clip_sync(self, vibe: str, bpm: int, voice_style: str, vocal_mode: str) -> str:
        prompt = f"{vibe} {voice_style} {vocal_mode} vocal song {bpm} bpm"
        profile = self._build_profile(prompt)
        profile["tempo"] = max(50, min(180, int(bpm)))
        profile["voice_style"] = voice_style.strip().lower() or "female"
        profile["vocal_mode"] = vocal_mode.strip().lower() or "humming"

        filename = f"song_{uuid.uuid4().hex}.wav"
        path = self.output_dir / filename
        sample_rate = 44100

        backing = self._build_note_sequence(profile)
        vocal = self._build_vocal_sequence(profile)
        total_seconds = sum(duration for _freq, duration, _amp in backing)
        total_samples = int(sample_rate * total_seconds)
        audio = bytearray()

        backing_segments = self._expand_segments(backing, sample_rate)
        vocal_segments = self._expand_segments(vocal, sample_rate)

        for index in range(total_samples):
            sample_value = 0.0
            sample_value += self._render_backing_sample(index, sample_rate, backing_segments) * 0.45
            sample_value += self._render_vocal_sample(
                index,
                sample_rate,
                vocal_segments,
                profile["voice_style"],
                profile["vocal_mode"],
            ) * 0.7
            pcm_value = int(max(-32767, min(32767, sample_value * 14000)))
            audio.extend(pcm_value.to_bytes(2, byteorder="little", signed=True))

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(audio))

        return str(path)

    def _generate_song_clip_studio_sync(
        self,
        vibe: str,
        bpm: int,
        voice_style: str,
        vocal_mode: str,
        quality_tier: str,
    ) -> str:
        if not self.studio_api_url:
            raise RuntimeError(
                "Studio vocal generation is not configured yet. Set MUSIC_STUDIO_API_URL to a studio-capable vocal generation endpoint."
            )

        payload = {
            "task": "generate_vocals",
            "vibe": vibe,
            "bpm": int(bpm),
            "voice_style": voice_style,
            "vocal_mode": vocal_mode,
            "quality_tier": quality_tier,
            "format": "wav",
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.studio_api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.studio_api_key}"} if self.studio_api_key else {}),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Studio vocal generation failed: HTTP {exc.code} {body}".strip()) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Studio vocal generation failed: {exc.reason}") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Studio vocal generation returned invalid JSON.") from exc

        file_path = payload.get("file_path")
        if isinstance(file_path, str) and Path(file_path).exists():
            return file_path

        audio_base64 = payload.get("audio_base64") or payload.get("b64_audio")
        if isinstance(audio_base64, str) and audio_base64.strip():
            audio_bytes = base64.b64decode(audio_base64)
            output_format = str(payload.get("format", "wav")).lower()
            return self._write_audio_file(audio_bytes, output_format)

        audio_url = payload.get("url") or payload.get("audio_url")
        if isinstance(audio_url, str) and audio_url.strip():
            return self._download_audio_file(audio_url.strip(), payload.get("format", "wav"))

        raise RuntimeError("Studio vocal generation did not return a usable audio file.")

    def _build_profile(self, prompt: str) -> dict:
        lowered = prompt.lower()
        seed_bytes = hashlib.sha256(prompt.encode("utf-8")).digest()
        seed = int.from_bytes(seed_bytes[:8], byteorder="big", signed=False)
        rng = random.Random(seed)

        major_scale = [0, 2, 4, 5, 7, 9, 11, 12]
        minor_scale = [0, 2, 3, 5, 7, 8, 10, 12]
        pentatonic_scale = [0, 2, 4, 7, 9, 12]

        if any(word in lowered for word in ("sad", "dark", "moody", "melancholy")):
            scale = minor_scale
            tempo = 78
        elif any(word in lowered for word in ("bright", "happy", "uplifting", "joyful")):
            scale = major_scale
            tempo = 118
        elif any(word in lowered for word in ("ambient", "calm", "dreamy", "soft")):
            scale = pentatonic_scale
            tempo = 72
        else:
            scale = major_scale if rng.random() > 0.45 else minor_scale
            tempo = 96

        if "fast" in lowered or "energetic" in lowered:
            tempo += 24
        if "slow" in lowered or "relaxing" in lowered:
            tempo -= 18

        root_midi = 57 if scale is minor_scale else 60
        if "low" in lowered or "bass" in lowered:
            root_midi -= 12
        if "high" in lowered or "chime" in lowered:
            root_midi += 12

        return {
            "prompt": prompt,
            "scale": scale,
            "tempo": max(56, min(152, tempo)),
            "root_midi": root_midi,
            "rng": rng,
        }

    def _build_note_sequence(self, profile: dict) -> list[tuple[float, float, float]]:
        beat_seconds = 60.0 / profile["tempo"]
        rng = profile["rng"]
        scale = profile["scale"]
        root_midi = profile["root_midi"]

        sequence = []
        current_degree = rng.randrange(0, len(scale) - 1)
        for step in range(16):
            leap = rng.choice([-2, -1, 0, 1, 2])
            current_degree = max(0, min(len(scale) - 1, current_degree + leap))
            midi_note = root_midi + scale[current_degree]
            frequency = self._midi_to_frequency(midi_note)

            if step % 4 == 3 and rng.random() < 0.25:
                sequence.append((0.0, beat_seconds * 0.5, 0.0))
                continue

            if rng.random() < 0.2:
                duration = beat_seconds * 1.5
            elif rng.random() < 0.45:
                duration = beat_seconds * 0.5
            else:
                duration = beat_seconds

            amplitude = 12000 if step % 4 == 0 else 9000
            sequence.append((frequency, duration, amplitude))

        return sequence

    def _build_vocal_sequence(self, profile: dict) -> list[tuple[float, float, float]]:
        beat_seconds = 60.0 / profile["tempo"]
        rng = profile["rng"]
        scale = profile["scale"]
        root_midi = profile["root_midi"] + (5 if profile["voice_style"] == "female" else -5)
        vocal_mode = profile.get("vocal_mode", "humming")

        sequence = []
        current_degree = rng.randrange(0, len(scale) - 1)
        step_count = 8
        if vocal_mode == "vocal chop":
            step_count = 14
        elif vocal_mode == "lyrics":
            step_count = 10

        for _step in range(step_count):
            movement = [-1, 0, 1]
            if vocal_mode == "lyrics":
                movement = [-2, -1, 0, 1, 2]
            current_degree = max(0, min(len(scale) - 1, current_degree + rng.choice(movement)))
            midi_note = root_midi + scale[current_degree]
            frequency = self._midi_to_frequency(midi_note)
            if vocal_mode == "humming":
                duration = beat_seconds * rng.choice((1.5, 2.0, 2.5))
            elif vocal_mode == "vocal chop":
                duration = beat_seconds * rng.choice((0.25, 0.5, 0.75))
            else:
                duration = beat_seconds * rng.choice((0.75, 1.0, 1.5))
            amplitude = 1.0
            sequence.append((frequency, duration, amplitude))
            if vocal_mode == "vocal chop" and rng.random() < 0.3:
                sequence.append((0.0, beat_seconds * 0.25, 0.0))
        return sequence

    def _expand_segments(self, sequence: list[tuple[float, float, float]], sample_rate: int) -> list[tuple[int, int, float, float]]:
        segments = []
        cursor = 0
        for frequency, duration, amplitude in sequence:
            segment_samples = int(duration * sample_rate)
            segments.append((cursor, cursor + segment_samples, frequency, amplitude))
            cursor += segment_samples
        return segments

    def _render_backing_sample(self, index: int, sample_rate: int, segments: list[tuple[int, int, float, float]]) -> float:
        for start, end, frequency, amplitude in segments:
            if start <= index < end:
                if frequency <= 0:
                    return 0.0
                local_index = index - start
                t = local_index / sample_rate
                envelope = min(1.0, local_index / (sample_rate * 0.02))
                release = min(1.0, (end - index) / (sample_rate * 0.04))
                shaped = amplitude * min(envelope, release)
                return (
                    math.sin(2 * math.pi * frequency * t) * 0.7
                    + math.sin(2 * math.pi * frequency * 2 * t) * 0.2
                    + math.sin(2 * math.pi * frequency * 0.5 * t) * 0.1
                ) * shaped
        return 0.0

    def _render_vocal_sample(
        self,
        index: int,
        sample_rate: int,
        segments: list[tuple[int, int, float, float]],
        voice_style: str,
        vocal_mode: str,
    ) -> float:
        formant_a = 900 if voice_style == "female" else 700
        formant_b = 1300 if voice_style == "female" else 1100
        for start, end, frequency, amplitude in segments:
            if start <= index < end:
                if frequency <= 0:
                    return 0.0
                local_index = index - start
                t = local_index / sample_rate
                attack = 0.03
                release_window = 0.07
                vibrato_depth = 0.01
                overtone_level = 0.25
                breath_level = 0.08
                shimmer_level = 0.05

                if vocal_mode == "humming":
                    attack = 0.05
                    release_window = 0.12
                    vibrato_depth = 0.016
                    breath_level = 0.04
                    shimmer_level = 0.03
                elif vocal_mode == "vocal chop":
                    attack = 0.008
                    release_window = 0.02
                    vibrato_depth = 0.003
                    overtone_level = 0.18
                    breath_level = 0.02
                    shimmer_level = 0.02
                elif vocal_mode == "lyrics":
                    attack = 0.02
                    release_window = 0.05
                    vibrato_depth = 0.009
                    overtone_level = 0.3
                    breath_level = 0.05
                    shimmer_level = 0.06

                envelope = min(1.0, local_index / (sample_rate * attack))
                release = min(1.0, (end - index) / (sample_rate * release_window))
                vibrato = 1 + vibrato_depth * math.sin(2 * math.pi * 5.5 * t)
                carrier = math.sin(2 * math.pi * frequency * vibrato * t)
                overtone = math.sin(2 * math.pi * (frequency * 2.02) * t) * overtone_level
                breath = math.sin(2 * math.pi * formant_a * t) * breath_level
                shimmer = math.sin(2 * math.pi * formant_b * t) * shimmer_level
                shaped = amplitude * min(envelope, release)
                if vocal_mode == "vocal chop":
                    gate = 1.0 if math.sin(2 * math.pi * 11.0 * t) > -0.25 else 0.35
                    shaped *= gate
                return (carrier * 0.75 + overtone + breath + shimmer) * shaped
        return 0.0

    def _midi_to_frequency(self, midi_note: int) -> float:
        return 440.0 * (2 ** ((midi_note - 69) / 12))

    def _should_use_studio_provider(self) -> bool:
        if self.provider == "studio_api":
            return True
        if self.provider == "auto" and self.studio_api_url:
            return True
        return False

    def _write_audio_file(self, audio_bytes: bytes, output_format: str) -> str:
        extension = output_format.lower().strip(".") or "wav"
        filename = f"song_{uuid.uuid4().hex}.{extension}"
        path = self.output_dir / filename
        path.write_bytes(audio_bytes)
        return str(path)

    def _download_audio_file(self, audio_url: str, output_format: str | None = None) -> str:
        request = urllib.request.Request(audio_url, headers={"User-Agent": "KibaBot/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                audio_bytes = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to download generated studio audio: {exc.reason}") from exc

        extension = "wav"
        if output_format:
            extension = str(output_format).lower().strip(".")
        elif "mpeg" in content_type or "mp3" in content_type:
            extension = "mp3"
        elif "ogg" in content_type:
            extension = "ogg"

        return self._write_audio_file(audio_bytes, extension)
