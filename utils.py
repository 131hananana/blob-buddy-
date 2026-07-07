"""
Small shared helpers: math utilities, save/load of the pet's persistent
state, and the day/night check.
"""

import json
import math
import os
import time

import config


def clamp(value, lo, hi):
    return lo if value < lo else hi if value > hi else value


def clamp01(value):
    return clamp(value, 0.0, 1.0)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    """Blend two RGB tuples.  t=0 -> c1, t=1 -> c2."""
    t = clamp01(t)
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_night(now=None):
    """Day/night theme is driven by the local system clock."""
    hour = (now or time.localtime()).tm_hour
    return hour < config.DAY_STARTS or hour >= config.NIGHT_STARTS


# ------------------------------------------------------------ persistence ---

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "savedata.json")


def load_state():
    """Load the pet's saved state.  Returns {} when there is no save yet."""
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(data):
    """Persist the pet's state.  Failures are non-fatal (the pet just forgets)."""
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass
