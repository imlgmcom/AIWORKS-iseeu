"""MJPEG 网络流读取器。

OpenCV 的 VideoCapture 无法直接打开 DroidCam 等 IP 摄像头的
multipart/x-mixed-replace MJPEG 流，因此用本模块自行解析 HTTP 流：
    1. 建立 HTTP 长连接
    2. 持续读取字节流，按 JPEG SOI/EOI 标记 (FF D8 ... FF D9) 截取帧
    3. cv2.imdecode 解码为 numpy 数组
    4. 后台线程持续读帧，read() 立即返回最新帧，降低延迟
"""

import threading
import time
import http.client
from urllib.parse import urlparse

import cv2
import numpy as np

# JPEG 起始/结束标记
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"


class MjpegStream:
    """线程安全的 MJPEG 流读取器，接口兼容 cv2.VideoCapture。"""

    def __init__(self, url: str, timeout: float = 5.0, af_interval: float = 0.0):
        parsed = urlparse(url)
        self._host = parsed.hostname
        self._port = parsed.port or 80
        self._path = parsed.path or "/"
        if parsed.query:
            self._path += "?" + parsed.query
        self._timeout = timeout

        # DroidCam 自动对焦间隔（秒），0 = 禁用
        self._af_interval = af_interval
        self._last_af_time = 0.0

        self._conn = None
        self._response = None
        self._buffer = b""

        self._latest_frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def _open_connection(self) -> bool:
        try:
            if self._conn:
                self._close_connection()
            self._conn = http.client.HTTPConnection(
                self._host, self._port, timeout=self._timeout
            )
            self._conn.request("GET", self._path)
            self._response = self._conn.getresponse()
            if self._response.status != 200:
                self._close_connection()
                return False
            self._buffer = b""
            return True
        except Exception:
            self._close_connection()
            return False

    def _close_connection(self):
        try:
            if self._response:
                self._response.close()
        except Exception:
            pass
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._response = None
        self._conn = None

    # ------------------------------------------------------------------
    # DroidCam 自动对焦
    # ------------------------------------------------------------------
    def trigger_autofocus(self):
        """向 DroidCam 发送自动对焦命令 (GET /cam/1/af)。"""
        try:
            conn = http.client.HTTPConnection(self._host, self._port, timeout=3)
            conn.request("GET", "/cam/1/af")
            conn.getresponse().read()
            conn.close()
            self._last_af_time = time.time()
        except Exception:
            pass  # 非 DroidCam 摄像头会静默失败

    def _maybe_autofocus(self, force: bool = False):
        """按间隔触发自动对焦；force=True 时立即触发。"""
        if self._af_interval <= 0 and not force:
            return
        now = time.time()
        if force or now - self._last_af_time >= self._af_interval:
            self.trigger_autofocus()

    # ------------------------------------------------------------------
    # 后台读帧线程
    # ------------------------------------------------------------------
    def _read_loop(self):
        """持续读取 MJPEG 流，保持最新帧，断流时自动重连。"""
        first_connect = True
        while self._running:
            # 无连接时先尝试连接
            if self._response is None:
                if not self._open_connection():
                    time.sleep(2.0)
                    continue
                # 连接成功后触发一次自动对焦
                if first_connect:
                    self._maybe_autofocus(force=True)
                    first_connect = False

            frame = self._read_one_frame()
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
                # 定期自动对焦
                self._maybe_autofocus()
            else:
                # 读取失败，关闭连接，下一轮重连
                self._close_connection()
                time.sleep(2.0)

    def _read_one_frame(self):
        """从流中解析一帧 JPEG 并解码，失败返回 None。"""
        if self._response is None:
            return None
        try:
            # 不断读取直到找到完整的 JPEG 帧
            while self._running:
                soi = self._buffer.find(_JPEG_SOI)
                if soi != -1:
                    eoi = self._buffer.find(_JPEG_EOI, soi + 2)
                    if eoi != -1:
                        jpg_data = self._buffer[soi:eoi + 2]
                        self._buffer = self._buffer[eoi + 2:]
                        frame = cv2.imdecode(
                            np.frombuffer(jpg_data, dtype=np.uint8),
                            cv2.IMREAD_COLOR,
                        )
                        if frame is not None:
                            return frame
                        # 解码失败，丢弃 SOI 之前的数据继续找
                        self._buffer = self._buffer[soi + 2:]
                        continue

                # 缓冲区中没有完整帧，继续读取
                chunk = self._response.read(8192)
                if not chunk:
                    return None  # 流断开
                self._buffer += chunk
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # 公共接口（兼容 cv2.VideoCapture）
    # ------------------------------------------------------------------
    def isOpened(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def read(self):
        """返回 (ret, frame)；无可用帧时 ret=False。"""
        with self._lock:
            if self._latest_frame is not None:
                return True, self._latest_frame.copy()
        return False, None

    def release(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._close_connection()
        with self._lock:
            self._latest_frame = None

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------
    def start(self) -> bool:
        """启动后台读帧线程（即使初始连接失败也会持续重连）。

        返回 True 表示线程已启动；初始连接是否成功需通过 read() 判断。
        """
        initial_ok = self._open_connection()
        if not initial_ok:
            print(f"[INFO] 网络摄像头 {self._host}:{self._port} 暂未连接，后台将持续重试...")
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True
