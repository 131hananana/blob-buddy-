"""
Sound effects for Blob Buddy.

All sounds are synthesized with numpy at startup (tiny sine sweeps with
envelopes), so the app works with zero binary assets.  If you drop WAV files
into assets/sounds/ (chirp.wav, yawn.wav, sigh.wav, pop.wav, music.wav) they
are used instead of the synthesized placeholders.

The background music is a soft generated chord pad that loops seamlessly.
"""

import os
import time

import numpy as np
import pygame

SAMPLE_RATE = 22050


# ------------------------------------------------------------- synthesis ---

def _envelope(n, attack=0.02, release=0.08):
    """Linear attack / release envelope so tones never click."""
    env = np.ones(n)
    a = max(1, int(attack * SAMPLE_RATE))
    r = max(1, int(release * SAMPLE_RATE))
    a, r = min(a, n), min(r, n)
    env[:a] = np.linspace(0.0, 1.0, a)
    env[-r:] = np.linspace(1.0, 0.0, r)
    return env


def _sweep(f0, f1, dur, vibrato_hz=0.0, vibrato_depth=0.0, harmonics=(1.0,)):
    """A sine tone sweeping from f0 to f1 Hz, with optional vibrato and
    softer harmonic overtones.  Returns a float array in [-1, 1]."""
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0.0, dur, n, endpoint=False)
    freq = np.linspace(f0, f1, n)
    if vibrato_hz:
        freq = freq + vibrato_depth * np.sin(2 * np.pi * vibrato_hz * t)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    out = np.zeros(n)
    for i, amp in enumerate(harmonics, start=1):
        out += amp * np.sin(phase * i)
    return out / max(1.0, sum(harmonics))


def _silence(dur):
    return np.zeros(int(dur * SAMPLE_RATE))


def _to_sound(mono, volume=1.0):
    """float [-1,1] mono -> stereo int16 pygame Sound."""
    mono = np.clip(mono * volume, -1.0, 1.0)
    pcm = (mono * 32767).astype(np.int16)
    stereo = np.ascontiguousarray(np.column_stack([pcm, pcm]))
    return pygame.sndarray.make_sound(stereo)


def _make_chirp():
    """Two quick rising tweets — the blob's happy noise."""
    a = _sweep(880, 1500, 0.10, harmonics=(1.0, 0.25)) * _envelope(int(0.10 * SAMPLE_RATE), 0.01, 0.04)
    b = _sweep(1100, 1750, 0.10, harmonics=(1.0, 0.25)) * _envelope(int(0.10 * SAMPLE_RATE), 0.01, 0.05)
    return _to_sound(np.concatenate([a, _silence(0.06), b]), 0.45)


def _make_yawn():
    """A slow descending 'aaah' with vibrato."""
    n = int(1.1 * SAMPLE_RATE)
    tone = _sweep(390, 170, 1.1, vibrato_hz=5.0, vibrato_depth=10.0,
                  harmonics=(1.0, 0.4, 0.15))
    return _to_sound(tone * _envelope(n, 0.20, 0.35), 0.4)


def _make_sigh():
    """A breathy falling sound: low-passed noise over a soft descending tone."""
    dur = 0.9
    n = int(dur * SAMPLE_RATE)
    noise = np.random.uniform(-1, 1, n)
    # Cheap low-pass: moving average smooths the noise into "breath".
    noise = np.convolve(noise, np.ones(48) / 48, mode="same")
    tone = _sweep(300, 150, dur, harmonics=(1.0, 0.3))
    return _to_sound((0.55 * noise + 0.45 * tone) * _envelope(n, 0.25, 0.45), 0.35)


def _make_pop():
    """Tiny blip for heart pops."""
    n = int(0.06 * SAMPLE_RATE)
    return _to_sound(_sweep(520, 950, 0.06) * _envelope(n, 0.005, 0.03), 0.35)


def _make_music():
    """A 12-second soft chord pad (C add9-ish) with slow shimmer, crossfaded
    at the seam so it loops without a click."""
    dur, fade = 12.0, 0.6
    n = int((dur + fade) * SAMPLE_RATE)
    t = np.linspace(0.0, dur + fade, n, endpoint=False)
    notes = [(261.63, 0.9, 0.11), (329.63, 0.7, 0.07),
             (392.00, 0.6, 0.09), (587.33, 0.35, 0.05)]
    pad = np.zeros(n)
    for freq, amp, lfo in notes:
        tremolo = 0.75 + 0.25 * np.sin(2 * np.pi * lfo * t)
        pad += amp * tremolo * np.sin(2 * np.pi * freq * t)
    pad /= len(notes)
    # Crossfade the tail over the head for a seamless loop.
    f = int(fade * SAMPLE_RATE)
    ramp = np.linspace(0.0, 1.0, f)
    pad[:f] = pad[:f] * ramp + pad[-f:] * (1.0 - ramp)
    return _to_sound(pad[:int(dur * SAMPLE_RATE)], 0.30)


# ------------------------------------------------------------- sound bank ---

class SoundBank:
    """Owns every sound; play() has per-sound cooldowns so rapid state churn
    never machine-guns audio."""

    _BUILDERS = {
        "chirp": _make_chirp,
        "yawn": _make_yawn,
        "sigh": _make_sigh,
        "pop": _make_pop,
        "music": _make_music,
    }

    def __init__(self, sound_dir):
        self.ok = pygame.mixer.get_init() is not None
        self.sounds = {}
        self._last_played = {}
        self.music_on = False
        if not self.ok:
            return
        for name, builder in self._BUILDERS.items():
            path = os.path.join(sound_dir, name + ".wav")
            try:
                if os.path.isfile(path):
                    self.sounds[name] = pygame.mixer.Sound(path)
                else:
                    self.sounds[name] = builder()
            except pygame.error:
                pass
        if "music" in self.sounds:
            self.sounds["music"].set_volume(0.30)

    def play(self, name, cooldown=0.3):
        if not self.ok or name not in self.sounds:
            return
        now = time.monotonic()
        if now - self._last_played.get(name, -999.0) < cooldown:
            return
        self._last_played[name] = now
        self.sounds[name].play()

    def toggle_music(self):
        if not self.ok or "music" not in self.sounds:
            return False
        self.music_on = not self.music_on
        if self.music_on:
            self.sounds["music"].play(loops=-1, fade_ms=800)
        else:
            self.sounds["music"].fadeout(800)
        return self.music_on
