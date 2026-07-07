"""
Global configuration for Blob Buddy.

Everything tunable lives here: window size, timings, and the two pastel
palettes (day / night).  Colors are plain RGB tuples so any module can use
them directly with pygame.
"""

# ---------------------------------------------------------------- window ---
WIDTH = 900
HEIGHT = 640
FPS = 60
TITLE = "Blob Buddy"

# ------------------------------------------------------------------ blob ---
BLOB_RADIUS = 92          # base body radius in pixels
FLOOR_MARGIN = 70         # distance of the "floor" from the bottom edge

# ------------------------------------------------------------- behaviour ---
LONELY_AFTER = 5.0        # seconds without a face before the blob gets sad
CURL_AFTER = 15.0         # seconds without a face before it curls into a ball
YAWN_DURATION = 2.2       # length of the falling-asleep animation
WAKE_DURATION = 1.6       # length of the wake-up stretch
FLOURISH_EVERY = (20, 40) # random idle behaviours happen this often (seconds)

# ------------------------------------------------------------- happiness ---
HAPPY_PET_RATE = 8.0      # happiness gained per second of petting
HAPPY_IDLE_RATE = 0.2     # slow drift upward while you are around (cap 70)
HAPPY_LONELY_RATE = -1.0  # decay while lonely
HAPPY_CURLED_RATE = -1.5  # decay while curled up

# ------------------------------------------------------------------ day ----
DAY_PALETTE = {
    "bg_top":    (207, 232, 255),
    "bg_bottom": (255, 231, 242),
    "floor":     (255, 214, 231),
    "body":      (255, 168, 200),
    "body_dark": (231, 122, 165),
    "highlight": (255, 210, 228),
    "cheek":     (255, 122, 163),
    "eye":       (72, 58, 82),
    "mouth":     (156, 74, 106),
    "shadow":    (216, 176, 200),
    "text":      (120, 96, 128),
    "cloud":     (176, 186, 205),
    "heart":     (255, 106, 150),
    "sparkle":   (255, 205, 110),
    "zzz":       (140, 150, 220),
    "drop":      (128, 168, 228),
    "puff":      (200, 200, 215),
    "pillow":    (222, 226, 255),
    "hud":       (255, 255, 255),
}

# ----------------------------------------------------------------- night ---
NIGHT_PALETTE = {
    "bg_top":    (30, 34, 62),
    "bg_bottom": (58, 48, 82),
    "floor":     (72, 60, 96),
    "body":      (226, 148, 186),
    "body_dark": (188, 108, 150),
    "highlight": (244, 186, 212),
    "cheek":     (236, 110, 152),
    "eye":       (48, 40, 60),
    "mouth":     (132, 64, 94),
    "shadow":    (24, 26, 46),
    "text":      (200, 190, 215),
    "cloud":     (110, 116, 140),
    "heart":     (255, 120, 160),
    "sparkle":   (255, 224, 150),
    "zzz":       (170, 178, 240),
    "drop":      (140, 172, 230),
    "puff":      (150, 150, 175),
    "pillow":    (170, 176, 220),
    "hud":       (235, 232, 245),
}

# Hours considered "day" for the automatic day/night theme.
DAY_STARTS = 7
NIGHT_STARTS = 19
