# -*- coding: utf-8 -*-
"""
首次初始化向导 - 中文 UI
由 first_run.bat 调用，负责依赖检查/安装和摄像头检测
"""
import os
import sys
import subprocess
import platform
import re
import time

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

REQUIRED_PACKAGES = [
    "opencv-contrib-python>=5.0.0.93",
    "mediapipe>=1.0.0",
    "insightface>=1.0.1",
    "onnxruntime>=1.28.0",
    "numpy>=2.5.0",
    "scikit-image>=0.26.0",
    "scipy>=1.18.0",
    "sounddevice>=0.5.0",
    "matplotlib>=3.11.0",
]

MEDIAPIPE_MODELS = {
    "blaze_face_short_range.tflite":
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    "blaze_face_full_range.tflite":
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
}


def print_header():
    print()
    print("=" * 60)
    print("  智能人脸抓拍系统 - 首次初始化向导")
    print("=" * 60)
    print()
    print(f"  操作系统: {platform.platform()}")
    print(f"  Python:   {sys.version.split()[0]}")
    print()


def step_check_python():
    """Step 1 已由 bat 完成，这里仅显示确认"""
    print("  [1/4] Python 环境检查 ...")
    print(f"        [OK] Python {sys.version.split()[0]} 已就绪")
    print()


def get_pkg_name(spec):
    """从 'pkg>=1.0' 提取 'pkg'"""
    return re.split(r"[<>=!~\[ ]", spec)[0].strip()


def step_check_deps():
    """Step 2: 检查并安装依赖"""
    print("  [2/4] 正在检查 Python 依赖包 ...")
    print()

    missing = []
    for spec in REQUIRED_PACKAGES:
        name = get_pkg_name(spec)
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 f"import importlib.metadata as m; print(m.version('{name}'))"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                ver = result.stdout.strip()
                print(f"        [OK]   {name} ({ver})")
            else:
                print(f"        [缺失] {name}")
                missing.append(spec)
        except Exception:
            print(f"        [缺失] {name}")
            missing.append(spec)

    print()

    if not missing:
        print("        [OK] 所有依赖已就绪，无需安装。")
        print()
        return True

    print(f"        检测到 {len(missing)} 个依赖缺失，开始安装 ...")
    print("        （首次安装可能需要 3~10 分钟，取决于网络速度）")
    print()

    # 先升级 pip 基础工具
    print("        升级 pip / setuptools / wheel ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        timeout=120
    )

    # 批量安装缺失的依赖
    print(f"        正在安装: {' '.join(missing)}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing,
        timeout=600
    )

    if result.returncode != 0:
        print()
        print("        [错误] 部分依赖安装失败！")
        print("        请手动执行:")
        print(f"        py312\\python.exe -m pip install {' '.join(REQUIRED_PACKAGES)}")
        print()
        return False

    print()
    print("        [OK] 所有依赖安装完成。")
    print()
    return True


def download_mediapipe_models():
    """Step 3: 下载 MediaPipe 人脸检测模型"""
    print("  [3/4] 正在检查 MediaPipe 模型文件 ...")
    print()

    model_dir = os.path.join(PROJECT_ROOT, "models", "mediapipe")
    os.makedirs(model_dir, exist_ok=True)

    all_ok = True
    for filename, url in MEDIAPIPE_MODELS.items():
        filepath = os.path.join(model_dir, filename)
        if os.path.exists(filepath):
            size_kb = os.path.getsize(filepath) // 1024
            print(f"        [OK]   {filename} ({size_kb} KB)")
            continue

        print(f"        下载 {filename} ...")
        try:
            import urllib.request
            print(f"        URL: {url}")
            urllib.request.urlretrieve(url, filepath)
            size_kb = os.path.getsize(filepath) // 1024
            print(f"        [OK]   {filename} ({size_kb} KB)")
        except Exception as e:
            print(f"        [错误] 下载失败: {e}")
            print(f"        请手动下载: {url}")
            print(f"        保存到: {filepath}")
            all_ok = False

    print()
    if all_ok:
        print("        [OK] 所有模型文件已就绪。")
    else:
        print("        [警告] 部分模型文件缺失，请手动下载后重新运行。")
    print()
    return all_ok


def list_cameras():
    """Step 4: 检测摄像头设备（本地 + 网络）"""
    print("  [4/4] 正在检测系统中的摄像头设备 ...")
    print()

    # --- 方法 1: 尝试 OpenCV ---
    try:
        import cv2
    except ImportError:
        print("        [警告] OpenCV 未安装，跳过摄像头索引检测")
        return False

    os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

    available = []
    for idx in range(8):
        cap = None
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
            if cap and cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available.append(idx)
        except Exception:
            pass
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    # --- 方法 2: WMI 获取设备名称 ---
    devices = []
    try:
        ps_script = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.PNPClass -in @('Image','Camera','MEDIA') -or ($_.Name -and "
            "($_.Name -match 'Camera|Webcam|Video|摄像头|视频')) } | "
            "Select-Object -ExpandProperty Name"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20
        )
        raw = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        seen = set()
        for n in raw:
            if n not in seen:
                seen.add(n)
                devices.append(n)
    except Exception:
        pass

    if devices:
        print(f"        系统识别到 {len(devices)} 个视频/图像相关设备：")
        for i, d in enumerate(devices, 1):
            print(f"          {i}. {d}")
        print()

    if available:
        # 显示 CAM_ID -> 设备名 对照表
        rows = []
        video_kw = ["camera", "webcam", "video", "摄像头", "视频"]
        filtered = [d for d in devices if any(k.lower() in d.lower() for k in video_kw)]
        if not filtered:
            filtered = devices

        for i, idx in enumerate(available):
            name = filtered[i] if i < len(filtered) else "(未识别名称)"
            rows.append((idx, name))

        print(f"        OpenCV 可用的本地摄像头索引（即 option.ini 的 CAM_ID）：")
        print()
        print(f"        {'CAM_ID':<10} 对应设备（顺序供参考）")
        print(f"        {'-' * 10}  {'-' * 42}")
        for idx, name in rows:
            print(f"        {idx:<10} {name}")
        print()
        print("        使用说明：")
        print("          1. 编辑 option.ini，修改 CAM_ID 参数")
        print("          2. 从 0 开始试起；无画面再试 1、2 ...")
        print("          3. 多路摄像头示例：CAM_ID = 0,1")
        print()
    else:
        print("        [提示] OpenCV 未检测到可用的本地摄像头。")
        print("        如果使用网络摄像头（DroidCam 等），可跳过此项。")
        print()

    # --- 网络摄像头说明 ---
    print("        ── 网络摄像头（DroidCam 等）配置说明 ──")
    print()
    print("        1. 手机安装 DroidCam 并启动，记录显示的 IP 和端口")
    print("           （例如 192.168.6.161:4747）")
    print("        2. 在 option.ini 的 CAM_URLS 填入地址，支持以下写法：")
    print("             CAM_URLS = 192.168.6.161:4747")
    print("             CAM_URLS = http://192.168.6.161:4747/video")
    print("        3. 多路网络摄像头用逗号分隔")
    print("        4. 可与本地 CAM_ID 同时使用")
    print()
    print("        提示：程序运行时会自动检测网络摄像头连接，断流后自动重连。")
    print()
    return True


def print_footer():
    print("=" * 60)
    print()
    print("  初始化完成！接下来请：")
    print()
    print("    1. 打开 option.ini")
    print("    2. 配置摄像头：")
    print("       - 本地摄像头：修改 CAM_ID 参数")
    print("       - 网络摄像头（DroidCam）：填入 CAM_URLS")
    print("    3. 如需人脸识别，将人脸图片放入 face\\ 目录")
    print("       （同名 .jpg + .mp3 可配置专属提示音）")
    print("    4. 双击 run.bat 启动程序")
    print()


def main():
    try:
        print_header()
        step_check_python()

        deps_ok = step_check_deps()
        if not deps_ok:
            print()
            print("[错误] 依赖安装失败，请检查网络后重新运行。")
            input("按回车键退出...")
            return 1

        models_ok = download_mediapipe_models()
        if not models_ok:
            print()
            print("[警告] 部分模型文件未就绪，人脸识别可能无法正常工作。")
            print("        请手动下载上述模型文件后重新运行。")
            print()

        cam_ok = list_cameras()

        print_footer()
        return 0
    except KeyboardInterrupt:
        print()
        print("[中断] 用户取消操作。")
        return 130
    except Exception as e:
        print()
        print(f"[错误] 初始化过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
