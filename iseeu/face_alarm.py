import cv2
import time
import os
from urllib.parse import urlparse

from .detector import FaceDetector
from .recognizer import FaceRecognizer
from .audio_player import AudioPlayer
from .mjpeg_stream import MjpegStream

# 顺时针旋转角度 → OpenCV 旋转码
_ROTATE_MAP = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}
_ROTATE_CYCLE = [0, 90, 180, 270]


class FaceAlarm:
    def __init__(self, camera_source, cfg, camera_label=None, display_rotation=0):
        # camera_source: int（本地索引）或 str（网络 URL）
        self.camera_source = camera_source
        self.is_network = isinstance(camera_source, str)
        self.cfg = cfg
        self.display_rotation = display_rotation

        # 显示标签：网络摄像头取 host:port，本地用索引号
        if camera_label:
            self.camera_label = camera_label
        elif self.is_network:
            parsed = urlparse(camera_source)
            host = parsed.hostname or camera_source
            port = f":{parsed.port}" if parsed.port else ""
            self.camera_label = f"{host}{port}"
        else:
            self.camera_label = str(camera_source)

        self.detector = FaceDetector(cfg)
        self.recognizer = FaceRecognizer(cfg)
        self.player = AudioPlayer()

        self.alarm_sound = cfg["ALARM_SOUND"]
        self.person_sound = None

        # 数字变焦倍数（按中心放大），1.0 = 禁用
        self.zoom = cfg.get("ZOOM", 1.0)

        self.state = "idle"
        self.burst_count = 0
        self.cooldown_start_time = 0
        self.first_trigger_time = 0
        self.frame_count = 0
        self.recognized_name = None
        self.recognized_mp3 = None

        if not os.path.exists(cfg["SNAPSHOT_DIR"]):
            os.makedirs(cfg["SNAPSHOT_DIR"])

        self.cap = None
        if not self._open_camera():
            kind = "网络摄像头" if self.is_network else "摄像头"
            raise RuntimeError(f"无法打开{kind}: {self.camera_label}")

        kind = "网络摄像头" if self.is_network else "摄像头"
        print(f"[OK] {kind} {self.camera_label} 已就绪")

    def _open_camera(self) -> bool:
        """打开摄像头（区分本地索引与网络 MJPEG 流）"""
        if self.is_network:
            # 网络流：OpenCV VideoCapture 无法处理 DroidCam 的 multipart MJPEG，
            # 改用自定义 MjpegStream（后台线程持续读帧 + 自动重连 + 定期对焦）
            af_interval = self.cfg.get("DROIDCAM_AF_INTERVAL", 0.0)
            stream = MjpegStream(self.camera_source, timeout=5.0, af_interval=af_interval)
            if stream.start():
                self.cap = stream
                return True
            self.cap = None
            return False
        else:
            self.cap = cv2.VideoCapture(self.camera_source)
            # 仅本地摄像头可设置采集分辨率
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            opened = self.cap.isOpened()
            if not opened:
                self.cap = None
            return opened

    def trigger_autofocus(self):
        """手动触发 DroidCam 自动对焦（本地摄像头无效果）。"""
        if self.is_network and hasattr(self.cap, "trigger_autofocus"):
            self.cap.trigger_autofocus()
            print(f"[INFO] 摄像头 {self.camera_label} 已触发自动对焦")

    def read_frame(self):
        """读取一帧画面，依次应用数字变焦和方向旋转。

        旋转后的帧用于检测、识别、抓拍和显示，确保人脸方向正确，
        否则 MediaPipe 的 YAW 角过滤会拒绝横置的人脸。
        返回 (ret, frame)；ret=False 时 frame 为 None。
        """
        if self.cap is None:
            return False, None
        ret, frame = self.cap.read()
        if not ret:
            return False, None
        # 数字变焦：按中心裁剪后放大回原尺寸
        if self.zoom > 1.0:
            frame = self._digital_zoom(frame)
        # 方向旋转：校正画面方向（横屏→竖屏等），检测前必须旋转
        if self.display_rotation in _ROTATE_MAP:
            frame = cv2.rotate(frame, _ROTATE_MAP[self.display_rotation])
        return True, frame

    def _digital_zoom(self, frame):
        """按中心点裁剪并放大回原尺寸。

        zoom=2.0 → 裁剪中心 1/2 区域，放大到原尺寸（视觉等效2倍变焦）。
        """
        h, w = frame.shape[:2]
        crop_w = int(w / self.zoom)
        crop_h = int(h / self.zoom)
        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2
        cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

    def cycle_display_rotation(self):
        """顺时针切换旋转角度：0° → 90° → 180° → 270° → 0°

        旋转影响检测、识别、抓拍和显示（必须旋转到正确方向才能识别人脸）。
        """
        idx = _ROTATE_CYCLE.index(self.display_rotation)
        self.display_rotation = _ROTATE_CYCLE[(idx + 1) % len(_ROTATE_CYCLE)]
        print(f"[INFO] 摄像头 {self.camera_label} 旋转: {self.display_rotation}°")

    def play_alarm(self):
        if self.person_sound:
            self.player.play(self.person_sound)
        elif self.alarm_sound and os.path.exists(self.alarm_sound):
            self.player.play(self.alarm_sound)

    def load_person_sound(self, mp3_path):
        if not mp3_path or not os.path.exists(mp3_path):
            self.person_sound = None
            return
        self.person_sound = mp3_path
        print(f"[INFO] 加载提示音: {mp3_path}")

    def take_snapshot(self, frame):
        if self.recognized_name:
            filename = os.path.join(
                self.cfg["SNAPSHOT_DIR"],
                f"{self.recognized_name}_{int(time.time())}_{self.burst_count}.jpg"
            )
        else:
            filename = os.path.join(
                self.cfg["SNAPSHOT_DIR"],
                f"capture_{int(time.time())}_{self.burst_count}.jpg"
            )
        success, buffer = cv2.imencode(".jpg", frame)
        if success:
            buffer.tofile(filename)
            print(f"[INFO] Cam{self.camera_label} 已抓拍: {filename}")
        else:
            print(f"[ERROR] Cam{self.camera_label} 保存失败")

    def process_frame(self, frame):
        current_time = time.time()
        self.frame_count += 1
        cached_detections = []

        # --- 状态机 ---

        if self.state == "cooldown":
            if current_time - self.cooldown_start_time >= self.cfg["COOLDOWN_SECONDS"]:
                self.state = "idle"
                self.recognized_name = None
                self.recognized_mp3 = None
                self.person_sound = None

        elif self.state == "waiting":
            if current_time - self.first_trigger_time >= self.cfg["TRIGGER_DELAY"]:
                self.take_snapshot(frame)
                self.burst_count = 1
                self.state = "bursting"

        elif self.state == "bursting":
            if self.burst_count >= self.cfg["BURST_COUNT"]:
                self.state = "cooldown"
                self.cooldown_start_time = current_time
            else:
                expected_time = (
                    self.first_trigger_time
                    + self.cfg["TRIGGER_DELAY"]
                    + (self.burst_count * self.cfg["BURST_INTERVAL"])
                )
                if current_time >= expected_time:
                    self.take_snapshot(frame)
                    self.burst_count += 1

        elif self.state == "idle":
            if self.frame_count % self.cfg["CHECK_INTERVAL"] == 0:
                cached_detections = self.detector.find_faces(frame)
                if cached_detections:
                    self.recognized_name, mp3_path = self.recognizer.recognize(frame)
                    self.load_person_sound(mp3_path)
                    self.play_alarm()
                    self.first_trigger_time = current_time
                    self.state = "waiting"

        # --- 预览画面 ---
        if self.cfg["PREVIEW"]:
            frame = self.detector.draw_roi_overlay(frame)
            frame = self.detector.draw_face_boxes(frame, cached_detections)

            status_text = f"Cam{self.camera_label} | {self.state.upper()}"
            if self.recognized_name:
                status_text += f" | {self.recognized_name}"
            if self.state == "bursting":
                status_text += f" ({self.burst_count}/{self.cfg['BURST_COUNT']})"
            elif self.state == "cooldown":
                remaining = int(self.cfg["COOLDOWN_SECONDS"] - (current_time - self.cooldown_start_time))
                status_text += f" (Wait: {remaining}s)"

            cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        return frame
