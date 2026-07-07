"""
Camera capture + vision processing on a background thread.

Rendering must never wait for the webcam: MediaPipe takes 10-40 ms per frame,
which would tank a 60 FPS render loop.  So this worker owns the camera and
both trackers, runs them as fast as the camera delivers frames, and publishes
an immutable Snapshot under a lock.  The render loop grabs the latest
snapshot each frame (a dictionary read, effectively free) and uses the `seq`
counter to feed gesture detectors exactly once per *camera* frame.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2

from face_tracker import FaceTracker
from hand_tracker import HandData, HandTracker

PREVIEW_SIZE = (160, 120)


@dataclass
class Snapshot:
    seq: int = 0
    timestamp: float = 0.0
    face_visible: bool = False
    face_center: Optional[Tuple[float, float]] = None
    hands: List[HandData] = field(default_factory=list)
    preview_rgb: Optional[object] = None   # small numpy RGB frame for the debug preview
    fps: float = 0.0


class CameraWorker(threading.Thread):
    def __init__(self, camera_index=0, capture_width=640, capture_height=480):
        super().__init__(daemon=True, name="camera-worker")
        self.camera_index = camera_index
        self.capture_size = (capture_width, capture_height)
        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        # Note: named _stop_event because Thread has a private _stop() method
        # that must not be shadowed.
        self._stop_event = threading.Event()
        self.error = None

    # ------------------------------------------------------------- public ---

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def stop(self):
        self._stop_event.set()

    # -------------------------------------------------------------- worker ---

    def run(self):
        cap = cv2.VideoCapture(self.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[1])
        if not cap.isOpened():
            self.error = "Could not open the webcam."
            return

        face_tracker = FaceTracker()
        hand_tracker = HandTracker()
        seq = 0
        last_t = time.monotonic()
        fps = 0.0

        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue

                # Mirror the frame so on-screen motion matches the user's own
                # sense of left/right — crucial for petting to feel natural.
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False   # lets MediaPipe skip a copy

                face_visible, face_center = face_tracker.process(rgb)
                hands = hand_tracker.process(rgb)

                rgb.flags.writeable = True
                preview = cv2.resize(rgb, PREVIEW_SIZE)
                self._annotate(preview, face_center, hands)

                now = time.monotonic()
                fps = 0.9 * fps + 0.1 * (1.0 / max(1e-3, now - last_t))
                last_t = now
                seq += 1

                snap = Snapshot(
                    seq=seq,
                    timestamp=now,
                    face_visible=face_visible,
                    face_center=face_center,
                    hands=hands,
                    preview_rgb=preview,
                    fps=fps,
                )
                with self._lock:
                    self._snapshot = snap
        finally:
            cap.release()
            face_tracker.close()
            hand_tracker.close()

    @staticmethod
    def _annotate(preview, face_center, hands):
        """Draw tiny markers on the debug preview so the user can see what
        the trackers see."""
        w, h = PREVIEW_SIZE
        if face_center:
            cv2.circle(preview, (int(face_center[0] * w), int(face_center[1] * h)),
                       6, (120, 255, 160), 1)
        for hand in hands:
            cv2.circle(preview, (int(hand.center[0] * w), int(hand.center[1] * h)),
                       4, (255, 160, 200), -1)
