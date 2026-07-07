"""
The blob itself: state machine, emotions, and procedural rendering.

There are no sprite images — the blob is drawn every frame from a wobbling
polygon plus simple shapes, driven entirely by a handful of continuous
emotion parameters (smile, eye openness, droop, curl, sleep...).  Each
parameter is a damped Spring (see animation.py) chasing a per-state target,
which is what makes every expression change melt smoothly into the next:
the state machine flips *targets* instantly, but the visible values glide.

Body shape:
    radius(angle) = R * (1 + slow_wobble + jiggle * fast_wobble)
    The slow wobble makes it read as soft jelly; the fast wobble term is
    scaled by the under-damped squash spring's energy, so nudging the spring
    (petting!) makes the whole silhouette ripple.

Squash & stretch:
    rx = R * (1 + squash), ry = R * (1 - squash) — volume roughly preserved,
    the classic cartoon principle.  Breathing is a small sine added to
    squash, so the blob inflates/deflates instead of just translating.
"""

import math
import random
from enum import Enum

import pygame

import config
from animation import Spring, bounce_arc, ease_in_out
from utils import clamp01, lerp, lerp_color

TAU = math.tau


class BlobState(Enum):
    IDLE = "idle"
    PETTING = "petting"
    LONELY = "lonely"
    CURLED = "curled"
    FALLING_ASLEEP = "falling asleep"
    SLEEPING = "sleeping"
    WAKING = "waking"


# Per-state targets for the emotion springs:
#          smile  eye_open  droop  curl  sleep  scale
_EMOTIONS = {
    BlobState.IDLE:           (0.35, 1.00, 0.0, 0.0, 0.0, 1.00),
    BlobState.PETTING:        (1.00, 0.10, 0.0, 0.0, 0.0, 1.00),
    BlobState.LONELY:         (-0.55, 0.75, 1.0, 0.0, 0.0, 1.00),
    BlobState.CURLED:         (-0.25, 0.10, 1.0, 1.0, 0.0, 0.62),
    BlobState.FALLING_ASLEEP: (0.25, 0.35, 0.0, 0.0, 0.3, 1.00),
    BlobState.SLEEPING:       (0.20, 0.00, 0.0, 0.0, 1.0, 1.00),
    BlobState.WAKING:         (0.70, 1.00, 0.0, 0.0, 0.0, 1.00),
}


class Blob:
    def __init__(self, screen_w, screen_h, particles, sounds):
        self.W, self.H = screen_w, screen_h
        self.particles = particles
        self.sounds = sounds

        self.state = BlobState.IDLE
        self.state_since = 0.0
        self.last_face_time = 0.0
        self.happiness = 55.0

        # --- emotion springs (critically damped -> smooth glides) ---------
        self.smile = Spring(0.35, omega=6.0)
        self.eye_open = Spring(1.0, omega=9.0)
        self.droop = Spring(0.0, omega=4.0)
        self.curl = Spring(0.0, omega=5.0)
        self.sleep = Spring(0.0, omega=4.0)
        self.scale = Spring(1.0, omega=6.0)
        self.angle = Spring(0.0, omega=6.0)

        # --- body physics: under-damped so it wobbles like jelly ----------
        self.squash = Spring(0.0, omega=14.0, zeta=0.22)

        # --- eyes ----------------------------------------------------------
        self._blink_timer = random.uniform(2.0, 5.0)
        self._blink_phase = 1.0          # >= 1 means "not blinking"
        self._pupil = Spring(0.0, omega=8.0)   # x offset, follows the mouse
        self._pupil_y = Spring(0.0, omega=8.0)

        # --- transient animation state --------------------------------------
        self._flourish = None            # {"type", "start", "dur"}
        self._next_flourish = random.uniform(*config.FLOURISH_EVERY)
        self._mouth_open = 0.0           # yawn amount
        self._tear = 0.0                 # grows, then drips as a particle
        self._sigh_timer = random.uniform(4.0, 7.0)
        self._emit_timer = 0.0           # generic particle-emission clock

        # geometry computed each update, consumed by draw() and by main
        # (for the petting zone)
        self.cx = screen_w / 2.0
        self.cy = screen_h - config.FLOOR_MARGIN - config.BLOB_RADIUS
        self.rx = self.ry = config.BLOB_RADIUS

    # ------------------------------------------------------------- public ---

    @property
    def center(self):
        return (self.cx, self.cy)

    @property
    def radius(self):
        return max(self.rx, self.ry)

    def update(self, t, dt, senses, mouse_pos):
        """senses: dict with face_visible, petting, finger_heart, wave."""
        self._update_state(t, senses)
        self._update_emotions(dt)
        self._update_happiness(dt)
        self._update_motion(t, dt)
        self._update_eyes(t, dt, mouse_pos)
        self._update_effects(t, dt)

    # ------------------------------------------------------- state machine ---

    def _set_state(self, state, t):
        if state == self.state:
            return
        self.state = state
        self.state_since = t

        # Entry effects — one-shot reactions to the transition itself.
        if state == BlobState.PETTING:
            self.sounds.play("chirp", cooldown=1.5)
        elif state == BlobState.FALLING_ASLEEP:
            self.sounds.play("yawn")
        elif state == BlobState.WAKING:
            self.sounds.play("chirp")
            self.squash.nudge(-2.2)   # stretch taaall
        elif state == BlobState.CURLED:
            self.squash.nudge(0.8)

    def _update_state(self, t, senses):
        s = self.state

        # ----- asleep branch: only a wave matters -------------------------
        if s == BlobState.FALLING_ASLEEP:
            # Yawn animation plays out on a fixed timeline, then sleep.
            phase = (t - self.state_since) / config.YAWN_DURATION
            self._mouth_open = bounce_arc(phase)   # mouth opens then closes
            if phase >= 1.0:
                self._mouth_open = 0.0
                self._set_state(BlobState.SLEEPING, t)
            return
        if s == BlobState.SLEEPING:
            if senses["wave"]:
                self._set_state(BlobState.WAKING, t)
            return
        if s == BlobState.WAKING:
            if t - self.state_since >= config.WAKE_DURATION:
                self._set_state(BlobState.IDLE, t)
                self.last_face_time = t   # fresh start, don't be insta-lonely
            return

        # ----- awake branch ------------------------------------------------
        if senses["finger_heart"]:
            self._set_state(BlobState.FALLING_ASLEEP, t)
            return

        if senses["face_visible"]:
            if s in (BlobState.LONELY, BlobState.CURLED):
                # Reunion! A happy hop, sparkles and a chirp.
                self._set_state(BlobState.IDLE, t)
                self._start_flourish("hop", t)
                self.particles.spawn("sparkle", self.cx, self.cy,
                                     self._palette["sparkle"], count=8)
                self.sounds.play("chirp")
                self.happiness = min(100.0, self.happiness + 4.0)
            self.last_face_time = t

        if senses["petting"]:
            self._set_state(BlobState.PETTING, t)
            return
        if s == BlobState.PETTING:
            self._set_state(BlobState.IDLE, t)
            return

        away = t - self.last_face_time
        if away > config.CURL_AFTER:
            self._set_state(BlobState.CURLED, t)
        elif away > config.LONELY_AFTER:
            self._set_state(BlobState.LONELY, t)

    # ------------------------------------------------------------ emotions ---

    def _update_emotions(self, dt):
        smile, eye, droop, curl, sleep, scale = _EMOTIONS[self.state]
        self.smile.update(smile, dt)
        self.eye_open.update(eye, dt)
        self.droop.update(droop, dt)
        self.curl.update(curl, dt)
        self.sleep.update(sleep, dt)
        self.scale.update(scale, dt)
        # Lying down: a gentle tilt while asleep.
        angle_target = -0.14 * self.sleep.value
        self.angle.update(angle_target, dt)

    def _update_happiness(self, dt):
        if self.state == BlobState.PETTING:
            self.happiness += config.HAPPY_PET_RATE * dt
        elif self.state == BlobState.LONELY:
            self.happiness += config.HAPPY_LONELY_RATE * dt
        elif self.state == BlobState.CURLED:
            self.happiness += config.HAPPY_CURLED_RATE * dt
        elif self.state == BlobState.IDLE and self.happiness < 70.0:
            self.happiness += config.HAPPY_IDLE_RATE * dt
        self.happiness = max(0.0, min(100.0, self.happiness))

    # -------------------------------------------------------------- motion ---

    def _update_motion(self, t, dt):
        st = self.state
        asleep = self.sleep.value

        # Breathing: a slow sine added onto the squash so the body inflates
        # and deflates.  Sleep breathing is slower and deeper.
        breath_rate = lerp(1.9, 1.1, asleep)
        breath_amp = lerp(0.030, 0.050, asleep)
        breath = breath_amp * math.sin(t * breath_rate)

        # Idle bounce: happy states gently pump the jelly spring.
        if st == BlobState.IDLE:
            self.squash.nudge(0.28 * math.sin(t * 2.4) * dt * 8.0)
        elif st == BlobState.PETTING:
            # Happy wiggle: constant little kicks keep the jelly rippling.
            self.squash.nudge(0.9 * math.sin(t * 9.0) * dt * 10.0)

        self.squash.update(0.0, dt)

        # ----- flourish (random idle behaviours + wake-up stretch) ---------
        hop_y, spin, sway_extra = 0.0, 0.0, 0.0
        squash_extra = 0.0
        if st == BlobState.WAKING:
            # A big stretch: tall and thin, easing back to normal.
            k = ease_in_out((t - self.state_since) / config.WAKE_DURATION)
            squash_extra = -0.28 * bounce_arc(k)

        fl = self._flourish
        if fl is not None:
            k = (t - fl["start"]) / fl["dur"]
            if k >= 1.0:
                self._flourish = None
            elif fl["type"] == "hop":
                hop_y = 46.0 * bounce_arc(k)
                squash_extra += 0.16 * math.sin(k * TAU)   # anticipate + land
            elif fl["type"] == "stretch":
                squash_extra += -0.22 * bounce_arc(k)
            elif fl["type"] == "spin":
                spin = TAU * ease_in_out(k)
            elif fl["type"] == "wiggle":
                sway_extra = 18.0 * math.sin(k * TAU * 3.0) * (1.0 - k)

        # Schedule the next random idle behaviour (only while idling).
        if st == BlobState.IDLE and self._flourish is None:
            self._next_flourish -= dt
            if self._next_flourish <= 0:
                self._start_flourish(random.choice(["hop", "stretch", "spin", "wiggle"]), t)

        # ----- final geometry ----------------------------------------------
        base_r = config.BLOB_RADIUS * self.scale.value
        squash = self.squash.value + breath + squash_extra
        # Sleeping bodies puddle out wide.
        squash += 0.22 * asleep
        squash = max(-0.45, min(0.45, squash))
        self.rx = base_r * (1.0 + squash)
        self.ry = base_r * (1.0 - squash)

        # Hovering float while awake; asleep it rests on the ground.
        hover = (7.0 + 4.0 * math.sin(t * 1.6)) * (1.0 - asleep) * (1.0 - 0.6 * self.curl.value)
        floor_y = self.H - config.FLOOR_MARGIN
        self.cy = floor_y - self.ry - hover - hop_y
        self.cx = self.W / 2.0 + sway_extra + 4.0 * math.sin(t * 0.7) * (1.0 - asleep)
        self._spin = spin

    def _start_flourish(self, kind, t):
        durations = {"hop": 0.7, "stretch": 1.1, "spin": 0.9, "wiggle": 1.0}
        self._flourish = {"type": kind, "start": t, "dur": durations[kind]}
        self._next_flourish = random.uniform(*config.FLOURISH_EVERY)
        if kind == "hop":
            self.squash.nudge(1.2)

    # ---------------------------------------------------------------- eyes ---

    def _update_eyes(self, t, dt, mouse_pos):
        # Natural blinking: a random 2-5 s timer; each blink is a quick
        # 0.22 s close-open driven by a sine arc.  No blinking while asleep
        # or while the eyes are already happily squeezed shut.
        if self._blink_phase < 1.0:
            self._blink_phase += dt / 0.22
        elif self.eye_open.value > 0.5 and self.sleep.value < 0.5:
            self._blink_timer -= dt
            if self._blink_timer <= 0:
                self._blink_phase = 0.0
                # Occasionally double-blink — tiny touches read as "alive".
                self._blink_timer = random.uniform(0.25, 0.4) if random.random() < 0.25 \
                    else random.uniform(2.0, 5.0)

        # Pupils: follow the mouse a little; when lonely, slowly look around
        # the room instead (searching for you).
        if self.droop.value > 0.5:
            look_x = math.sin(t * 0.5) * 4.0
            look_y = math.sin(t * 0.31 + 1.0) * 2.0
        else:
            dx = (mouse_pos[0] - self.cx) / self.W
            dy = (mouse_pos[1] - self.cy) / self.H
            look_x = max(-4.0, min(4.0, dx * 14.0))
            look_y = max(-3.0, min(3.0, dy * 10.0))
        self._pupil.update(look_x, dt)
        self._pupil_y.update(look_y, dt)

    def _blink_mult(self):
        """1 = open, 0 = closed, following a smooth close-open arc."""
        if self._blink_phase >= 1.0:
            return 1.0
        return 1.0 - math.sin(self._blink_phase * math.pi)

    # ------------------------------------------------------------- effects ---

    def _update_effects(self, t, dt):
        pal = self._palette
        self._emit_timer -= dt

        if self.state == BlobState.PETTING and self._emit_timer <= 0:
            self.particles.spawn("heart", self.cx, self.cy - self.ry, pal["heart"])
            self.sounds.play("pop", cooldown=0.5)
            self._emit_timer = random.uniform(0.25, 0.5)

        elif self.state == BlobState.IDLE and self._emit_timer <= 0:
            self.particles.spawn("sparkle", self.cx, self.cy - self.ry * 0.3, pal["sparkle"])
            self._emit_timer = random.uniform(1.5, 3.5)

        elif self.state == BlobState.SLEEPING and self._emit_timer <= 0:
            self.particles.spawn("zzz", self.cx + self.rx * 0.5, self.cy - self.ry, pal["zzz"])
            self._emit_timer = random.uniform(1.0, 1.6)

        if self.state in (BlobState.LONELY, BlobState.CURLED):
            # Rain from the little cloud.
            if random.random() < dt * 2.0:
                self.particles.spawn("drop", self.cx, self.cy - self.ry - 52, pal["drop"])
            # Occasional sigh: sound + a small escaping puff of air.
            self._sigh_timer -= dt
            if self._sigh_timer <= 0:
                self.sounds.play("sigh")
                self.particles.spawn("puff", self.cx + self.rx * 0.4, self.cy + self.ry * 0.2, pal["puff"])
                self.squash.nudge(0.5)   # a deflating slump
                self._sigh_timer = random.uniform(5.0, 8.0)
            # Watery eyes: a tear swells, then drips off.
            self._tear = min(1.0, self._tear + dt * 0.25)
            if self._tear >= 1.0:
                self.particles.spawn("drop", self.cx - self.rx * 0.32, self.cy - self.ry * 0.02, pal["drop"])
                self._tear = 0.2
        else:
            self._tear = max(0.0, self._tear - dt * 2.0)

    # ---------------------------------------------------------------- draw ---

    _palette = config.DAY_PALETTE   # main.py swaps this for day/night

    def set_palette(self, palette):
        self._palette = palette

    def _off(self, dx, dy):
        """Offset from the blob center, rotated by the body angle (tilt +
        spin flourish) — so the face rides along when the blob rotates."""
        a = self.angle.value + self._spin
        ca, sa = math.cos(a), math.sin(a)
        return (self.cx + dx * ca - dy * sa, self.cy + dx * sa + dy * ca)

    def draw(self, screen, t):
        pal = self._palette
        droop, curl, asleep = self.droop.value, self.curl.value, self.sleep.value

        # Lonely blobs turn a touch pale and blue.
        body = lerp_color(pal["body"], (176, 178, 220), droop * 0.35)
        body_dark = lerp_color(pal["body_dark"], (140, 142, 190), droop * 0.35)

        self._draw_shadow(screen, pal)
        if asleep > 0.4:
            self._draw_pillow(screen, pal, asleep)
        if droop > 0.4:
            self._draw_cloud(screen, pal, t, droop)

        self._draw_body(screen, t, body, body_dark)
        self._draw_face(screen, t, pal, body_dark)

    # ----- body -------------------------------------------------------------

    def _draw_body(self, screen, t, body, body_dark):
        jiggle = min(1.0, abs(self.squash.velocity) * 0.5)
        a0 = self.angle.value + self._spin
        pts = []
        n = 48
        for i in range(n):
            a = i / n * TAU
            # Slow triple-lobe wobble = soft jelly; fast five-lobe wobble
            # scaled by spring energy = ripple when poked/petted.
            wob = 1.0 + 0.022 * math.sin(3 * a + t * 2.0) \
                      + jiggle * 0.06 * math.sin(5 * a - t * 16.0)
            x, y = math.cos(a) * self.rx * wob, math.sin(a) * self.ry * wob
            ca, sa = math.cos(a0), math.sin(a0)
            pts.append((self.cx + x * ca - y * sa, self.cy + x * sa + y * ca))

        # Ears/nubs first so the body overlaps their base.
        self._draw_nubs(screen, body, body_dark)

        pygame.draw.polygon(screen, body, pts)
        pygame.draw.aalines(screen, body_dark, True, pts)

        # Soft top-left highlight — reads as glossy jelly.
        hl = pygame.Surface((int(self.rx * 0.9), int(self.ry * 0.6)), pygame.SRCALPHA)
        pygame.draw.ellipse(hl, (*self._palette["highlight"], 110), hl.get_rect())
        hx, hy = self._off(-self.rx * 0.30, -self.ry * 0.42)
        screen.blit(hl, (hx - hl.get_width() / 2, hy - hl.get_height() / 2))

    def _draw_nubs(self, screen, body, body_dark):
        """Two little bumps on top of the head; they slide down the sides
        and shrink when the blob is sad (drooping 'ears')."""
        droop = self.droop.value
        r = self.rx * 0.15 * (1.0 - 0.35 * droop)
        for side in (-1, 1):
            dx = side * self.rx * (0.42 + 0.16 * droop)
            dy = -self.ry * (0.90 - 0.42 * droop)
            x, y = self._off(dx, dy)
            pygame.draw.circle(screen, body, (int(x), int(y)), int(r))
            pygame.draw.circle(screen, body_dark, (int(x), int(y)), int(r), 1)

    def _draw_shadow(self, screen, pal):
        floor_y = self.H - config.FLOOR_MARGIN
        hover = floor_y - (self.cy + self.ry)
        w = self.rx * 1.5 * max(0.55, 1.0 - hover / 220.0)
        sh = pygame.Surface((int(w), 18), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (*pal["shadow"], 90), sh.get_rect())
        screen.blit(sh, (self.cx - w / 2, floor_y - 8))

    # ----- face ---------------------------------------------------------------

    def _draw_face(self, screen, t, pal, body_dark):
        smile = self.smile.value
        asleep = self.sleep.value
        open_k = clamp01(self.eye_open.value) * self._blink_mult()
        eye_dx = self.rx * 0.34
        eye_dy = -self.ry * 0.16
        eye_w = max(3.0, self.rx * 0.115)
        eye_h = max(3.0, self.ry * 0.21)

        for side in (-1, 1):
            ex, ey = self._off(side * eye_dx, eye_dy)
            if asleep > 0.6:
                # Peaceful closed eyes: gentle downward curves.
                self._curve(screen, pal["eye"], (ex - eye_w, ey), (ex + eye_w, ey),
                            bend=eye_h * 0.5, width=3)
            elif smile > 0.75 or open_k < 0.12:
                if smile > 0.4:
                    # Happy squeezed-shut eyes: upward arches (^ ^).
                    self._curve(screen, pal["eye"], (ex - eye_w, ey + 2), (ex + eye_w, ey + 2),
                                bend=-eye_h * 0.8, width=3)
                else:
                    self._curve(screen, pal["eye"], (ex - eye_w, ey), (ex + eye_w, ey),
                                bend=eye_h * 0.3, width=3)
            else:
                # Open eyes: dark rounded ovals with a light glint, pupils
                # shifted slightly toward whatever the blob is looking at.
                px, py = self._pupil.value, self._pupil_y.value
                h = max(3.0, eye_h * open_k)
                rect = pygame.Rect(0, 0, int(eye_w * 2), int(h * 2))
                rect.center = (int(ex + px), int(ey + py))
                pygame.draw.ellipse(screen, pal["eye"], rect)
                glint = max(2, int(eye_w * 0.38))
                pygame.draw.circle(screen, (255, 255, 255),
                                   (rect.centerx - glint, rect.centery - int(h * 0.4)), glint)
                if self.droop.value > 0.35:
                    # Watery shine along the bottom of the eye.
                    wet = pygame.Rect(0, 0, int(eye_w * 1.6), max(2, int(h * 0.5)))
                    wet.center = (rect.centerx, rect.bottom - 2)
                    pygame.draw.ellipse(screen, pal["drop"], wet)

        # Growing teardrop under the left eye while lonely.
        if self._tear > 0.25 and self.droop.value > 0.5:
            tx, ty = self._off(-eye_dx, eye_dy + eye_h + 6)
            pygame.draw.circle(screen, pal["drop"], (int(tx), int(ty)),
                               max(2, int(4 * self._tear)))

        # Cheeks — blush shows when happy.
        if smile > 0.1:
            blush = int(60 + 140 * clamp01(smile))
            for side in (-1, 1):
                bx, by = self._off(side * self.rx * 0.55, self.ry * 0.10)
                cheek = pygame.Surface((22, 12), pygame.SRCALPHA)
                pygame.draw.ellipse(cheek, (*pal["cheek"], blush), cheek.get_rect())
                screen.blit(cheek, (bx - 11, by - 6))

        # Mouth: a yawning oval, or a curve whose bend follows the smile
        # value (positive = smile, negative = worried frown).
        mx, my = self._off(0, self.ry * 0.26)
        if self._mouth_open > 0.08:
            w = int(self.rx * (0.10 + 0.16 * self._mouth_open))
            h = int(self.ry * (0.08 + 0.30 * self._mouth_open))
            rect = pygame.Rect(0, 0, w * 2, h * 2)
            rect.center = (int(mx), int(my))
            pygame.draw.ellipse(screen, pal["mouth"], rect)
        else:
            w = self.rx * 0.20 * (0.55 + 0.45 * abs(smile))
            self._curve(screen, pal["mouth"], (mx - w, my), (mx + w, my),
                        bend=smile * self.ry * 0.16, width=3)

    @staticmethod
    def _curve(screen, color, p0, p1, bend, width=2):
        """Draw a quadratic curve between two points; `bend` bows it down
        (positive) or up (negative).  Used for mouths and closed eyes."""
        cx = (p0[0] + p1[0]) / 2
        cy = (p0[1] + p1[1]) / 2 + bend
        pts = []
        for i in range(13):
            s = i / 12
            x = (1 - s) ** 2 * p0[0] + 2 * (1 - s) * s * cx + s ** 2 * p1[0]
            y = (1 - s) ** 2 * p0[1] + 2 * (1 - s) * s * cy + s ** 2 * p1[1]
            pts.append((x, y))
        pygame.draw.lines(screen, color, False, pts, width)

    # ----- props ----------------------------------------------------------------

    def _draw_cloud(self, screen, pal, t, droop):
        """A tiny personal rain cloud bobbing above the lonely blob."""
        alpha = int(200 * clamp01((droop - 0.4) / 0.6))
        cx = self.cx + math.sin(t * 0.9) * 6
        cy = self.cy - self.ry - 62 + math.sin(t * 1.3) * 3
        cloud = pygame.Surface((110, 46), pygame.SRCALPHA)
        col = (*pal["cloud"], alpha)
        pygame.draw.circle(cloud, col, (28, 30), 15)
        pygame.draw.circle(cloud, col, (55, 22), 19)
        pygame.draw.circle(cloud, col, (82, 30), 14)
        pygame.draw.ellipse(cloud, col, pygame.Rect(18, 22, 74, 22))
        screen.blit(cloud, (cx - 55, cy - 23))

    def _draw_pillow(self, screen, pal, asleep):
        k = clamp01((asleep - 0.4) / 0.6)
        w, h = int(120 * k) or 1, int(34 * k) or 1
        pillow = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(pillow, (*pal["pillow"], 235), pillow.get_rect())
        pygame.draw.ellipse(pillow, (*pal["shadow"], 60), pillow.get_rect(), 2)
        x = self.cx - self.rx * 0.85 - w / 2
        y = self.H - config.FLOOR_MARGIN - h + 4
        screen.blit(pillow, (x, y))
