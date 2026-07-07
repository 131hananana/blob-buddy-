"""
Face detection via MediaPipe.

We only need to know *whether* a face is visible (and roughly where), so the
lightweight FaceDetection model is used rather than the full face mesh.
"""

import mediapipe as mp


class FaceTracker:
    def __init__(self, min_confidence=0.6):
        # model_selection=0 -> short-range model, ideal for a webcam at a desk.
        self._detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=min_confidence,
        )

    def process(self, rgb_frame):
        """Returns (visible: bool, center: (x, y) normalized 0..1 or None).

        The frame is expected to be already horizontally mirrored, so the
        coordinates match what the user intuitively perceives.
        """
        results = self._detector.process(rgb_frame)
        if not results.detections:
            return False, None
        box = results.detections[0].location_data.relative_bounding_box
        center = (box.xmin + box.width / 2.0, box.ymin + box.height / 2.0)
        return True, center

    def close(self):
        self._detector.close()
