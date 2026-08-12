"""
辅助脚本：检测系统可用的摄像头设备列表
优先展示 OpenCV 实际可用的索引（对应 option.ini 的 CAM_ID）
"""
import sys
import platform
import re
import subprocess
import os

# 提前屏蔽 OpenCV 冗余日志
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"


def list_camera_devices_wmi():
    """
    通过 PowerShell + WMI 列出所有视频/图像设备
    注意：PowerShell 变量要写成 $_ 形式，用 -Command 内嵌文件避免转义问题
    """
    ps_script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12; "
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -in @('Image','Camera','MEDIA') -or ($_.Name -and "
        "($_.Name -match 'Camera|Webcam|Video|影像|摄像头|视频|USB2.0 PC|HD WebCam|IRiun')) } | "
        "Select-Object -ExpandProperty Name"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20
        )
        raw = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        seen = set()
        out = []
        for n in raw:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out
    except Exception:
        return []


def list_opencv_indices():
    """暴力探测 OpenCV 实际可用的摄像头索引"""
    try:
        import cv2
    except ImportError:
        return []

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
    return available


def build_mapping_table(devices, indices):
    """
    直接给出 CAM_ID 与可能名称的对照表。
    因为 Windows 设备枚举顺序不总一致，优先显示设备名列表，再给出建议索引。
    """
    rows = []
    for i, idx in enumerate(indices):
        if i < len(devices):
            name = devices[i]
        else:
            name = "(未识别名称的视频设备)"
        rows.append((idx, name))
    return rows


def main():
    print("=" * 60)
    print("  摄像头设备检测工具")
    print("=" * 60)
    print(f"  操作系统: {platform.platform()}")
    print()

    devices = list_camera_devices_wmi()
    indices = list_opencv_indices()

    if devices:
        print(f"  系统识别到 {len(devices)} 个视频/图像相关设备：")
        for i, d in enumerate(devices, 1):
            print(f"    {i}. {d}")
        print()

    if not indices:
        print("  [警告] OpenCV 没有检测到任何可用的摄像头索引。")
        print("  请检查：摄像头是否连接、驱动是否安装、是否被其他程序占用。")
        print()
        return 1

    rows = build_mapping_table(devices, indices)

    print(f"  OpenCV 可用的摄像头索引（即 option.ini 的 CAM_ID）：")
    print()
    print(f"  {'CAM_ID':<10} 对应设备（顺序供参考）")
    print(f"  {'-' * 10}  {'-' * 42}")
    for idx, name in rows:
        print(f"  {idx:<10} {name}")
    print()
    print("  快速提示：")
    print("    1. 编辑 option.ini，修改 CAM_ID 参数值")
    print("    2. 从 0 开始试起；无画面再试 1、2 …")
    print("    3. 多路摄像头示例：CAM_ID = 0,1")
    print()
    first = indices[0]
    print(f"  ➤ 推荐初始配置：CAM_ID = {first}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
