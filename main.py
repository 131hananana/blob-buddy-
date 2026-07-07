"""
Blob Buddy — a tiny virtual pet that watches you back. 🍮

Run with:  python main.py

Keys:
    M   toggle the soft background music
    C   toggle the little webcam preview (see what the blob sees)
    F   toggle debug overlay (FPS, state, tracking info)
    Esc / Q   quit (the blob's happiness is saved)

Architecture at a glance:
    main.py        60 FPS render loop; owns the window, HUD and wiring
    camera.py      background thread: webcam + MediaPipe (never blocks render)
    hand_tracker / face_tracker    MediaPipe wrappers + static pose geometry
    gestures.py    temporal gesture detectors (petting, wave, held poses)
    pet.py         the blob: state machine, emotions, procedural drawing
    animation.py   springs & easing
    particles.py   hearts / sparkles / Zzz / rain / puffs
    sounds.py      synthesized sound effects & music
"""

import os
import random
import sys
import time

import pygame

import config
import utils
from gestures import HoldDetector, PettingDetector, WaveDetector
from particles import ParticleSystem
from pet import Blob
from sounds import SoundBank

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


# ------------------------------------------------------------- background ---

def build_background(palette, night):
    """Pre-render the vertical gradient (and stars at night) once — cheaper
    than per-frame gradient drawing and it never changes within a mode."""
    bg = pygame.Surface((config.WIDTH, config.HEIGHT))
    top, bottom = palette["bg_top"], palette["bg_bottom"]
    for y in range(config.HEIGHT):
        t = y / config.HEIGHT
        bg.fill(utils.lerp_color(top, bottom, t),
                rect=pygame.Rect(0, y, config.WIDTH, 1))
    floor_y = config.HEIGHT - config.FLOOR_MARGIN
    pygame.draw.rect(bg, palette["floor"],
                     pygame.Rect(0, floor_y, config.WIDTH, config.FLOOR_MARGIN))
    if night:
        rng = random.Random(7)   # fixed seed -> the same starfield every night
        for _ in range(70):
            x = rng.randint(0, config.WIDTH)
            y = rng.randint(0, floor_y - 120)
            b = rng.randint(120, 230)
            pygame.draw.circle(bg, (b, b, min(255, b + 20)), (x, y), rng.choice((1, 1, 2)))
        # A soft crescent moon.
        pygame.draw.circle(bg, (240, 236, 214), (config.WIDTH - 110, 90), 30)
        pygame.draw.circle(bg, palette["bg_top"], (config.WIDTH - 98, 82), 26)
    return bg


# --------------------------------------------------------------------- HUD ---

def draw_heart(screen, x, y, size, color):
    r = size // 2
    pygame.draw.circle(screen, color, (x - r + 1, y - r // 2), r)
    pygame.draw.circle(screen, color, (x + r - 1, y - r // 2), r)
    pygame.draw.polygon(screen, color, [
        (x - size + 1, y - r // 2 + 2), (x + size - 1, y - r // 2 + 2), (x, y + size - 2)])


def draw_hud(screen, font, blob, palette, music_on, camera_ok):
    # Happiness meter: heart + rounded bar, top-left.
    draw_heart(screen, 30, 30, 12, palette["heart"])
    bar = pygame.Rect(50, 24, 130, 12)
    pygame.draw.rect(screen, palette["hud"], bar, border_radius=6)
    fill = bar.inflate(-4, -4)
    fill.width = max(2, int(fill.width * blob.happiness / 100.0))
    pygame.draw.rect(screen, palette["heart"], fill, border_radius=4)

    hints = "M music " + ("♪" if music_on else "·") + "   C camera   F debug   Esc quit"
    if not camera_ok:
        hints = "no camera — blob is in daydream mode   |   " + hints
    text = font.render(hints, True, palette["text"])
    screen.blit(text, (config.WIDTH / 2 - text.get_width() / 2, config.HEIGHT - 26))


def draw_debug(screen, font, clock, blob, snap, palette):
    lines = [
        f"render {clock.get_fps():5.1f} fps",
        f"camera {snap.fps:5.1f} fps" if snap else "camera  --",
        f"state  {blob.state.value}",
        f"happy  {blob.happiness:5.1f}",
        f"face   {'yes' if snap and snap.face_visible else 'no'}"
        + (f"   hands {len(snap.hands)}" if snap else ""),
    ]
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, palette["text"]),
                    (config.WIDTH - 170, 14 + i * 18))


def draw_camera_preview(screen, snap):
    if snap is None or snap.preview_rgb is None:
        return
    h, w = snap.preview_rgb.shape[:2]
    surf = pygame.image.frombuffer(snap.preview_rgb.tobytes(), (w, h), "RGB")
    x, y = 12, config.HEIGHT - h - 42
    screen.blit(surf, (x, y))
    pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(x - 1, y - 1, w + 2, h + 2), 1)


# ------------------------------------------------------------------ camera ---

def start_camera():
    """Start the vision thread; return None if OpenCV/MediaPipe are missing
    or no webcam exists.  The pet still runs — it just daydreams."""
    try:
        from camera import CameraWorker
    except ImportError as exc:
        print(f"[blob buddy] camera disabled ({exc}); running in daydream mode.")
        return None
    worker = CameraWorker()
    worker.start()
    return worker


# -------------------------------------------------------------------- main ---

def main():
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass   # no audio device — SoundBank handles it gracefully

    screen = pygame.display.set_mode((config.WIDTH, config.HEIGHT))
    pygame.display.set_caption(config.TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 20)

    night = utils.is_night()
    palette = config.NIGHT_PALETTE if night else config.DAY_PALETTE
    background = build_background(palette, night)

    sounds = SoundBank(os.path.join(ASSET_DIR, "sounds"))
    particles = ParticleSystem()
    blob = Blob(config.WIDTH, config.HEIGHT, particles, sounds)
    blob.set_palette(palette)
    blob.happiness = float(utils.load_state().get("happiness", 55.0))

    camera = start_camera()
    petting = PettingDetector()
    wave = WaveDetector()
    finger_heart = HoldDetector()

    debug = False
    show_preview = False
    last_seq = 0
    wave_event = False
    heart_event = False
    minute_check = 0.0

    start = time.monotonic()
    running = True
    while running:
        dt = min(clock.tick(config.FPS) / 1000.0, 1 / 20)
        t = time.monotonic() - start

        # ------------------------------------------------------- input ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_m:
                    sounds.toggle_music()
                elif event.key == pygame.K_f:
                    debug = not debug
                elif event.key == pygame.K_c:
                    show_preview = not show_preview

        # ------------------------------------------------------ senses ---
        snap = camera.snapshot() if camera else None
        if snap and snap.seq != last_seq:
            # Feed gesture detectors exactly once per *camera* frame —
            # feeding the same snapshot 60x/second would corrupt their
            # velocity estimates.
            last_seq = snap.seq
            hand = snap.hands[0] if snap.hands else None
            hand_screen = (hand.center[0] * config.WIDTH,
                           hand.center[1] * config.HEIGHT) if hand else None
            petting.ingest(snap.timestamp, hand_screen, blob.center, blob.radius * 1.8)
            # Latch one-shot events until the blob consumes them below.
            wave_event = wave.ingest(snap.timestamp, hand.center[0] if hand else None) or wave_event
            heart_event = finger_heart.ingest(snap.timestamp, bool(hand and hand.finger_heart)) or heart_event

        if camera and snap and snap.seq > 0:
            # seq > 0 means the worker has delivered at least one real frame;
            # otherwise fall through to daydream mode (camera missing/denied).
            senses = {
                "face_visible": snap.face_visible,
                "petting": petting.active,
                "finger_heart": heart_event,
                "wave": wave_event,
            }
        else:
            # No camera: pretend the user is always here so the blob stays
            # a happy desk companion instead of eternally lonely.
            senses = {"face_visible": True, "petting": False,
                      "finger_heart": False, "wave": False}

        # ------------------------------------------------------ update ---
        blob.update(t, dt, senses, pygame.mouse.get_pos())
        wave_event = heart_event = False
        particles.update(dt)

        # Re-check day/night once a minute so a long-running pet follows
        # the sun without a restart.
        minute_check -= dt
        if minute_check <= 0:
            minute_check = 60.0
            if utils.is_night() != night:
                night = not night
                palette = config.NIGHT_PALETTE if night else config.DAY_PALETTE
                background = build_background(palette, night)
                blob.set_palette(palette)

        # -------------------------------------------------------- draw ---
        screen.blit(background, (0, 0))
        blob.draw(screen, t)
        particles.draw(screen)
        draw_hud(screen, font, blob, palette, sounds.music_on,
                 camera is not None and camera.error is None)
        if show_preview:
            draw_camera_preview(screen, snap)
        if debug:
            draw_debug(screen, font, clock, blob, snap, palette)
        pygame.display.flip()

    # ------------------------------------------------------------ shutdown ---
    utils.save_state({"happiness": round(blob.happiness, 1),
                      "saved_at": time.time()})
    if camera:
        camera.stop()
        camera.join(timeout=1.0)
    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
