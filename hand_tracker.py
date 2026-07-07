"""
Hand tracking via MediaPipe Hands.

This module does two jobs:
  1. wrap the MediaPipe model and expose landmarks in a simple HandData
     structure (normalized coordinates, hand center, hand size), and
  2. classify *static* per-frame geometry — currently the "finger heart"
     gesture.  Temporal gestures (petting, waving) live in gestures.py
     because they need history across frames.

MediaPipe landmark indices used here:

        4 = thumb tip        8 = index tip
       10 = middle PIP      12 = middle tip
       14 = ring PIP        16 = ring tip
       18 = pinky PIP       20 = pinky tip
        0 = wrist            9 = middle finger MCP (a stable "hand center")
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import mediapipe as mp


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class HandData:
    landmarks: List[Tuple[float, float]] = field(default_factory=list)
    center: Tuple[float, float] = (0.5, 0.5)   # normalized 0..1
    size: float = 0.1                          # wrist -> middle MCP distance
    finger_heart: bool = False


class HandTracker:
    def __init__(self, min_confidence=0.6):
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,           # one hand is enough for every gesture
            model_complexity=0,        # lite model keeps the camera thread fast
            min_detection_confidence=min_confidence,
            min_tracking_confidence=0.5,
        )

    def process(self, rgb_frame):
        """Returns a list of HandData (0 or 1 entries) in normalized,
        already-mirrored coordinates."""
        results = self._hands.process(rgb_frame)
        hands = []
        if results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                pts = [(lm.x, lm.y) for lm in hand_lms.landmark]
                data = HandData(
                    landmarks=pts,
                    center=pts[9],
                    size=max(1e-4, _d(pts[0], pts[9])),
                )
                data.finger_heart = self._is_finger_heart(pts, data.size)
                hands.append(data)
        return hands

    @staticmethod
    def _is_finger_heart(pts, hand_size):
        """Detect the Korean "finger heart": thumb and index finger crossed
        at their tips, with the other three fingers folded into the palm.

        Geometry (all distances normalized by hand size so it works at any
        distance from the camera):
          - thumb tip (4) and index tip (8) must nearly touch, and
          - middle/ring/pinky are "folded" when each tip is not farther from
            the wrist than its PIP joint (a rotation-invariant curl test —
            comparing y coordinates would break when the hand is tilted).
        """
        wrist = pts[0]
        pinch = _d(pts[4], pts[8]) / hand_size
        if pinch > 0.45:
            return False
        for tip, pip in ((12, 10), (16, 14), (20, 18)):
            if _d(pts[tip], wrist) > _d(pts[pip], wrist) * 1.08:
                return False  # this finger is extended -> not a finger heart
        return True

    def close(self):
        self._hands.close()
