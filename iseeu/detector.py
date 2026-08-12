import os
import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision

from .config import resolve_path


class FaceDetector:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        model_idx = cfg.get("Face_Detection_Model", 0)
        model_name = (
            "blaze_face_short_range" if model_idx == 0 else "blaze_face_full_range"
        )
        model_path = resolve_path(f"models/mediapipe/{model_name}.tflite")

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"MediaPipe model not found: {model_path}. "
                f"Please download from https://developers.google.com/mediapipe/solutions/vision/face_detector"
            )

        options = vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=cfg.get("MIN_DETECTION_CONFIDENCE", 0.5),
            min_suppression_threshold=0.3,
        )
        self.face_detector = vision.FaceDetector.create_from_options(options)
        print(f"[OK] MediaPipe FaceDetector loaded: {model_name}")

        self.roi_cols = 1
        self.roi_rows = 1
        if cfg["ROI_MODE"] > 0:
            try:
                cols, rows = cfg["ROI_GRIDS"].lower().split("x")
                self.roi_cols, self.roi_rows = int(cols), int(rows)
                print(f"[OK] ROI mode enabled: {self.roi_cols}x{self.roi_rows} grid")
            except ValueError:
                print("[WARNING] ROI_GRIDS format error, using full frame detection")
                cfg["ROI_MODE"] = 0

    def get_roi_frame(self, frame):
        if self.cfg["ROI_MODE"] == 0:
            return [(frame, (0, 0))]
        h, w, _ = frame.shape
        cell_w = w // self.roi_cols
        cell_h = h // self.roi_rows
        regions = []
        for r in range(self.roi_rows):
            for c in range(self.roi_cols):
                grid_index = r * self.roi_cols + c + 1
                if self.cfg["ROI_MODE"] == 2 and grid_index not in self.cfg["ROI_TARGETS"]:
                    continue
                x1 = c * cell_w
                y1 = r * cell_h
                regions.append((frame[y1:y1 + cell_h, x1:x1 + cell_w], (x1, y1)))
        return regions

    @staticmethod
    def calculate_yaw(landmarks):
        try:
            right_eye, left_eye, nose_tip = landmarks[0], landmarks[1], landmarks[2]
            dist_r = abs(nose_tip.x - right_eye.x)
            dist_l = abs(nose_tip.x - left_eye.x)
            if dist_l == 0 or dist_r == 0:
                return 90
            ratio = dist_r / (dist_l + 1e-6)
            return abs((ratio - 1.0) * 60)
        except Exception:
            return 90

    def find_faces(self, frame):
        roi_regions = self.get_roi_frame(frame)
        detections_found = []
        for roi_img, (offset_x, offset_y) in roi_regions:
            rgb_frame = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            result = self.face_detector.detect(mp_image)
            if result.detections:
                for detection in result.detections:
                    landmarks = detection.keypoints
                    yaw = self.calculate_yaw(landmarks)
                    if yaw < self.cfg["MAX_YAW_ANGLE"]:
                        detections_found.append({
                            "yaw": yaw,
                            "offset": (offset_x, offset_y),
                            "roi_img": roi_img,
                            "detection": detection,
                        })
        return detections_found

    def check_face_exists(self, frame):
        return len(self.find_faces(frame)) > 0

    def draw_roi_overlay(self, frame):
        if self.cfg["ROI_MODE"] > 0:
            h, w, _ = frame.shape
            for c in range(1, self.roi_cols):
                cv2.line(frame, ((w // self.roi_cols) * c, 0), ((w // self.roi_cols) * c, h), (200, 200, 200), 1)
            for r in range(1, self.roi_rows):
                cv2.line(frame, (0, (h // self.roi_rows) * r), (w, (h // self.roi_rows) * r), (200, 200, 200), 1)
        return frame

    def draw_face_boxes(self, frame, detections):
        for det in detections:
            if self.cfg["FACE_FRAME"]:
                bbox = det["detection"].bounding_box
                ox, oy = det["offset"]
                x = ox + bbox.origin_x
                y = oy + bbox.origin_y
                bw = bbox.width
                bh = bbox.height
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
        return frame
