# 🍮 Blob Buddy

A tiny pastel jelly creature that lives at the bottom of a window and reacts
to *you* through your webcam. It gets happy when it sees your face, melts
when you pet it with your hand, gets lonely (complete with a personal rain
cloud) when you leave, and falls asleep when you make a finger heart. 💜

No mouse, no clicks — the whole interaction is your face and your hands.

## Features

- **Idle** — face detected → soft smile, gentle bouncing, occasional sparkles.
- **Petting** — hover your hand over the blob and rub slowly → big smile,
  squeezed-happy eyes, jelly jiggles, floating hearts, happy chirps.
- **Lonely** — leave for 5 s → drooping ears, watery eyes, a tiny rain cloud,
  it looks around for you and sighs. After 15 s it curls into a little ball.
- **Sleep** — make a **finger heart** 🫰 → it yawns, lies down on a tiny
  pillow, and "Zzz" bubbles float up. **Wave** 👋 to wake it (big stretch!).
- Natural blinking, breathing float, squash & stretch, eyes that subtly
  follow your mouse, random idle behaviours (hop / stretch / spin / wiggle)
  every 20–40 s.
- Day/night theme from your system clock (stars + moon at night 🌙).
- Happiness meter that grows when petted, shrinks when ignored, and is
  **saved to `savedata.json`** so your blob remembers you between runs.
- Synthesized sound effects + soft loopable background music (toggle with M).
- Camera processing runs on a background thread — rendering stays at 60 FPS.

## Installation

> **Python 3.10 – 3.12 required** for the webcam features — MediaPipe does
> not ship wheels for 3.13+ yet. (Without MediaPipe/OpenCV the app still
> runs in "daydream mode": a happy blob with no camera senses.)

```bash
cd blob_buddy
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

On macOS the first launch will ask for **camera permission** — grant it to
your terminal app, then restart Blob Buddy.

### Keys

| key | action |
|-----|--------|
| `M` | toggle background music |
| `C` | toggle a small webcam preview (see what the blob sees) |
| `F` | debug overlay: FPS, camera FPS, state, tracking info |
| `Esc` / `Q` | quit (happiness is saved) |

## How the gestures work

All tracking runs in `camera.py` on a worker thread; per-frame geometry is
classified in `hand_tracker.py`, and gestures that only exist *over time*
live in `gestures.py`.

- **Petting** (`PettingDetector`) — a "heat" accumulator. Heat builds while
  your hand is inside the blob's zone moving at gentle rubbing speed
  (25–650 px/s), with bonus heat for direction reversals (real back-and-forth
  strokes). Heat decays when you stop or leave, and on/off hysteresis stops
  the state from flickering. No clicks involved.
- **Finger heart** (`HandTracker._is_finger_heart` + `HoldDetector`) —
  thumb tip and index tip nearly touching while middle/ring/pinky are curled
  (tip closer to the wrist than its middle joint — rotation-invariant). The
  pose must hold for ~0.5 s to fire, so passing hand poses don't trigger it.
- **Wave** (`WaveDetector`) — counts horizontal direction reversals: three
  swings of sufficient amplitude within 1.2 s = a wave.

## How the animation works

- Every expression parameter (smile, eye openness, droop, curl, sleep…) is a
  **critically damped spring** chasing a per-state target (`animation.py`),
  so state changes always *melt* rather than snap.
- The body squash is an **under-damped spring**: petting and hops "nudge" its
  velocity and the whole silhouette ripples like jelly, including a fast
  five-lobe wobble scaled by the spring's energy.
- **Squash & stretch**: `rx = R(1+s)`, `ry = R(1−s)` keeps volume roughly
  constant; breathing is a slow sine added to `s`, so the blob inflates
  rather than just moving up and down.
- Blinks fire on a random 2–5 s timer (25 % chance of a double-blink).

## Project layout

```
blob_buddy/
├── main.py          # window, 60 FPS loop, HUD, wiring
├── camera.py        # webcam + MediaPipe on a background thread
├── hand_tracker.py  # MediaPipe Hands + finger-heart geometry
├── face_tracker.py  # MediaPipe FaceDetection wrapper
├── gestures.py      # petting / wave / held-pose detectors
├── pet.py           # the blob: state machine, emotions, drawing
├── animation.py     # springs & easing
├── particles.py     # hearts, sparkles, Zzz, rain, puffs
├── sounds.py        # synthesized SFX & music (WAV override supported)
├── config.py        # sizes, timings, day & night palettes
├── utils.py         # math helpers, JSON persistence, day/night
├── assets/sounds/   # optional custom WAVs (see assets/README.md)
└── requirements.txt
```

## Troubleshooting

- **Black preview / "no camera"** — another app may be holding the webcam,
  or permission was denied (macOS: System Settings → Privacy → Camera).
- **Petting won't trigger** — press `C` to see the tracking preview; keep
  your hand well lit and rub *slowly* over the blob's on-screen position.
- **`pip install mediapipe` fails** — your Python is too new; create the
  venv with Python 3.10–3.12.

## Future ideas

- Feeding: detect a pinch gesture "carrying" food to the blob's mouth.
- Head-tilt mirroring — the blob tilts when you tilt.
- Multiple pets that interact with each other.
- Mood memory: greet you extra-excitedly after long absences (the save file
  already stores `saved_at`).
- Blow-a-kiss gesture → blushing overload state.
- Desktop-widget mode: borderless always-on-top transparent window.
- Voice: react to whistling or its name via a microphone.
- Achievements & accessories (tiny hats!) unlocked by happiness milestones.
