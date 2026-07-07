"""
Temporal gesture detectors — gestures that only exist *over time*.

Static geometry (like the finger-heart pose) is classified per frame in
hand_tracker.py; the detectors here consume a stream of hand positions from
the camera thread and answer questions like "is the user rubbing the blob?"
or "did the user just wave?".

All of them are written to be forgiving: virtual pets should reward the
user's intent, not demand pixel-perfect input.
"""

from collections import deque

from utils import dist


class PettingDetector:
    """Petting = the hand hovering over the blob while moving *slowly*.

    A "heat" accumulator makes this robust against tracking noise:

      - While the hand is inside the blob's petting zone and moving at a
        gentle rubbing speed, heat builds up.
      - Direction reversals (the back-and-forth of an actual rub) add bonus
        heat, so deliberate strokes trigger faster than a hand drifting by.
      - When the hand leaves, stops, or moves too fast, heat decays.
      - Hysteresis (ON at 0.45, OFF at 0.15) prevents flickering in and out
        of the petting state at the threshold.
    """

    MIN_SPEED = 25.0     # px/s — slower than this is just hovering
    MAX_SPEED = 650.0    # px/s — faster than this is not a gentle rub
    HEAT_ON = 0.45
    HEAT_OFF = 0.15

    def __init__(self):
        self.heat = 0.0
        self._active = False
        self._prev = None      # (t, x, y)
        self._prev_vx = 0.0

    def ingest(self, t, hand_pos, blob_center, zone_radius):
        """Feed one camera sample.  hand_pos is in *screen* pixels or None."""
        in_zone = hand_pos is not None and dist(hand_pos, blob_center) < zone_radius
        if not in_zone:
            self.heat = max(0.0, self.heat - 0.9 * self._dt(t))
            self._prev = None
            self._update_active()
            return

        if self._prev is not None:
            pt, px, py = self._prev
            dt = max(1e-3, t - pt)
            speed = dist(hand_pos, (px, py)) / dt
            vx = (hand_pos[0] - px) / dt
            if self.MIN_SPEED < speed < self.MAX_SPEED:
                self.heat += 1.6 * dt
                # Reward the back-and-forth of a genuine rubbing motion.
                if vx * self._prev_vx < 0 and abs(vx) > 40:
                    self.heat += 0.12
            else:
                self.heat -= 0.5 * dt
            self._prev_vx = vx
        self.heat = max(0.0, min(1.2, self.heat))
        self._prev = (t, hand_pos[0], hand_pos[1])
        self._update_active()

    def _dt(self, t):
        if self._prev is None:
            return 0.05
        return max(1e-3, t - self._prev[0])

    def _update_active(self):
        if self._active and self.heat < self.HEAT_OFF:
            self._active = False
        elif not self._active and self.heat > self.HEAT_ON:
            self._active = True

    @property
    def active(self):
        return self._active


class WaveDetector:
    """Waving = the hand's x position reversing direction quickly several
    times within a short window.

    We track horizontal "swings": a swing ends when the direction of travel
    flips after covering at least MIN_AMPLITUDE of the frame width.  Three
    or more swings inside WINDOW seconds counts as a wave.  A cooldown stops
    one long wave from firing repeatedly.
    """

    MIN_AMPLITUDE = 0.05   # normalized fraction of frame width per swing
    WINDOW = 1.2           # seconds
    NEEDED = 3             # direction reversals
    COOLDOWN = 2.5         # seconds between wave events

    def __init__(self):
        self._reversals = deque()
        self._dir = 0          # -1 left, +1 right, 0 unknown
        self._extreme_x = None  # x where the current swing started
        self._last_x = None
        self._last_fire = -999.0

    def ingest(self, t, hand_x):
        """Feed one camera sample. hand_x is normalized 0..1 or None.
        Returns True exactly once per detected wave."""
        if hand_x is None:
            self._dir, self._extreme_x, self._last_x = 0, None, None
            return False

        if self._last_x is not None:
            step = hand_x - self._last_x
            direction = 1 if step > 0 else -1 if step < 0 else 0
            if self._extreme_x is None:
                self._extreme_x = self._last_x
            if direction and direction != self._dir:
                # Direction flipped — did the previous swing travel far enough?
                if self._dir != 0 and abs(self._last_x - self._extreme_x) > self.MIN_AMPLITUDE:
                    self._reversals.append(t)
                self._dir = direction
                self._extreme_x = self._last_x
        self._last_x = hand_x

        while self._reversals and t - self._reversals[0] > self.WINDOW:
            self._reversals.popleft()

        if len(self._reversals) >= self.NEEDED and t - self._last_fire > self.COOLDOWN:
            self._last_fire = t
            self._reversals.clear()
            return True
        return False


class HoldDetector:
    """Debounces a boolean pose (like the finger heart): the pose must hold
    steadily for HOLD_TIME before firing, then a cooldown applies.  Brief
    single-frame dropouts are tolerated via a small grace period."""

    HOLD_TIME = 0.45
    GRACE = 0.15
    COOLDOWN = 3.0

    def __init__(self):
        self._since = None
        self._last_seen = -999.0
        self._last_fire = -999.0

    def ingest(self, t, flag):
        """Returns True exactly once when the pose has been held long enough."""
        if flag:
            self._last_seen = t
            if self._since is None:
                self._since = t
        elif t - self._last_seen > self.GRACE:
            self._since = None

        if (self._since is not None
                and t - self._since >= self.HOLD_TIME
                and t - self._last_fire > self.COOLDOWN):
            self._last_fire = t
            self._since = None
            return True
        return False
