import os
import sys
import configparser
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "option.ini")


def resolve_path(relative_path: str) -> str:
    path = os.path.join(PROJECT_ROOT, relative_path)
    return os.path.abspath(path)


def normalize_cam_url(raw: str, resolution_spec: str = "") -> str:
    """规范化网络摄像头 URL（兼容 DroidCam 简写）。

    - 缺少 scheme 时自动补 http://
    - 仅 ip:port 形式（无路径）时自动补 /video（DroidCam 默认路径）
    - 当 URL 未显式带分辨率参数时，根据 resolution_spec 附加 ?宽x高
    - 完整 URL 原样返回，方便兼容其他 IP 摄像头
    """
    raw = raw.strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    parsed = urlparse(raw)
    if not parsed.path or parsed.path == "/":
        raw = raw.rstrip("/") + "/video"

    # 若 URL 本身无分辨率参数，则根据配置附加
    if not parsed.query and resolution_spec:
        reso = _parse_resolution(resolution_spec)
        if reso:
            sep = "?" if "?" not in raw else "&"
            raw += f"{sep}{reso[0]}x{reso[1]}"

    return raw


# 预设分辨率简写 → (宽, 高)
_RESOLUTION_PRESETS = {
    "240p": (320, 240),
    "480p": (640, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "fhd 720p": (1280, 720),
    "fhd720p": (1280, 720),
    "fhd 1080p": (1920, 1080),
    "fhd1080p": (1920, 1080),
}


def _parse_resolution(spec: str):
    """解析清晰度配置，返回 (宽, 高) 或 None。

    支持：预设简写 "480p" / "720p" / "1080p" / "FHD 1080p"
          自定义 "1920x1080" / "1280x720"
    """
    spec = spec.strip()
    if not spec:
        return None
    # 预设简写
    if spec.lower() in _RESOLUTION_PRESETS:
        return _RESOLUTION_PRESETS[spec.lower()]
    # 自定义 宽x高
    if "x" in spec.lower():
        try:
            w, h = spec.lower().split("x", 1)
            return int(w.strip()), int(h.strip())
        except ValueError:
            return None
    return None


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"[FATAL] 未找到配置文件: {CONFIG_FILE}，请检查！")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')

    cfg = {
        "ALARM_SOUND": resolve_path(config.get("Settings", "ALARM_SOUND")),
        "SNAPSHOT_DIR": resolve_path(config.get("Settings", "SNAPSHOT_DIR")),
        "FACE_DIR": resolve_path(config.get("Settings", "FACE_DIR", fallback="face")),
        "SOUND_DIR": resolve_path(config.get("Settings", "SOUND_DIR", fallback="sounds")),

        # 本地摄像头索引（支持留空）
        "CAM_ID": [int(x.strip()) for x in config.get("Settings", "CAM_ID").split(",") if x.strip()],

        # 网络摄像头 URL（DroidCam 等，支持留空）
        "CAM_URLS": [normalize_cam_url(u) for u in config.get("Settings", "CAM_URLS", fallback="").split(",") if u.strip()],

        # 每路摄像头旋转角度（顺时针 0/90/180/270），按 CAM_ID + CAM_URLS 顺序
        "CAM_ROTATE": [int(x.strip()) for x in config.get("Settings", "CAM_ROTATE", fallback="").split(",") if x.strip()],

        "PREVIEW": config.getboolean("Settings", "PREVIEW"),
        "FACE_FRAME": config.getboolean("Settings", "FACE_FRAME"),

        "CHECK_INTERVAL": config.getint("Settings", "CHECK_INTERVAL"),
        "TRIGGER_DELAY": config.getfloat("Settings", "TRIGGER_DELAY"),
        "BURST_COUNT": config.getint("Settings", "BURST_COUNT"),
        "BURST_INTERVAL": config.getfloat("Settings", "BURST_INTERVAL"),
        "COOLDOWN_SECONDS": config.getfloat("Settings", "COOLDOWN_SECONDS"),

        "Face_Detection_Model": config.getint("Settings", "Face_Detection_Model"),
        "MIN_DETECTION_CONFIDENCE": config.getfloat("Settings", "MIN_DETECTION_CONFIDENCE"),
        "MAX_YAW_ANGLE": config.getfloat("Settings", "MAX_YAW_ANGLE"),

        "ROI_MODE": config.getint("Settings", "ROI_MODE"),
        "ROI_GRIDS": config.get("Settings", "ROI_GRIDS"),
        "ROI_TARGETS": [int(x.strip()) for x in config.get("Settings", "ROI_TARGETS").split(",")],

        "ENABLE_RECOGNITION": config.getboolean("Settings", "ENABLE_RECOGNITION", fallback=False),
        "RECOGNITION_THRESHOLD": config.getfloat("Settings", "RECOGNITION_THRESHOLD", fallback=0.45),

        # DroidCam 自动对焦间隔（秒），0 = 禁用
        "DROIDCAM_AF_INTERVAL": config.getfloat("Settings", "DROIDCAM_AF_INTERVAL", fallback=0.0),

        # 数字变焦倍数（按中心放大），1.0 = 禁用；2.0 = 放大2倍
        "ZOOM": config.getfloat("Settings", "ZOOM", fallback=1.0),

        # DroidCam 清晰度（预设简写 240p/480p/720p/1080p 或 1920x1080）
        # 留空 = 使用 DroidCam 默认，URL 中显式写 ?1920x1080 则以此为准
        "DROIDCAM_RESOLUTION": config.get("Settings", "DROIDCAM_RESOLUTION", fallback="").strip(),
    }

    # URL 规范化时附加清晰度参数（覆盖之前用默认规范化解析的 CAM_URLS）
    resolution_spec = cfg["DROIDCAM_RESOLUTION"]
    raw_urls = [u.strip() for u in config.get("Settings", "CAM_URLS", fallback="").split(",") if u.strip()]
    cfg["CAM_URLS"] = [normalize_cam_url(u, resolution_spec) for u in raw_urls]

    # 解析每路摄像头的独立配置（[Cam0] [Cam1] ... 按顺序对应 CAM_ID + CAM_URLS）
    cfg["CAM_OVERRIDES"] = _load_cam_overrides(config, len(cfg["CAM_ID"]) + len(cfg["CAM_URLS"]))

    return cfg


# 支持按摄像头覆盖的参数及其类型
_CAM_OVERRIDE_KEYS = {
    "ROI_MODE": "int",
    "ROI_GRIDS": "str",
    "ROI_TARGETS": "int_list",
    "Face_Detection_Model": "int",
    "MIN_DETECTION_CONFIDENCE": "float",
    "MAX_YAW_ANGLE": "float",
    "ZOOM": "float",
}


def _load_cam_overrides(config: configparser.ConfigParser, num_cams: int) -> list:
    """从 [Cam0] [Cam1] ... 分段加载每路摄像头的参数覆盖。

    返回 list[dict]，每个 dict 仅包含需覆盖的键；缺失的键沿用全局值。
    """
    overrides = []
    for i in range(num_cams):
        section = f"Cam{i}"
        override = {}
        if config.has_section(section):
            for key, vtype in _CAM_OVERRIDE_KEYS.items():
                if not config.has_option(section, key):
                    continue
                raw = config.get(section, key).strip()
                if not raw:
                    continue
                if vtype == "int":
                    override[key] = int(raw)
                elif vtype == "float":
                    override[key] = float(raw)
                elif vtype == "int_list":
                    override[key] = [int(x.strip()) for x in raw.split(",") if x.strip()]
                else:
                    override[key] = raw
        overrides.append(override)
    return overrides
