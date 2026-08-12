import sys
import cv2

from .config import load_config
from .face_alarm import FaceAlarm

# 预览画面最长边（480p：横屏 640×480，竖屏 480×640）
_PREVIEW_MAX = 480


def _on_mouse(event, x, y, flags, param):
    """鼠标回调：右键切换旋转，双击左键触发自动对焦。"""
    if event == cv2.EVENT_RBUTTONDOWN:
        param.cycle_display_rotation()
    elif event == cv2.EVENT_LBUTTONDBLCLK:
        param.trigger_autofocus()


def _fit_preview(frame):
    """将画面按比例缩放到最长边不超过 _PREVIEW_MAX（480p）。"""
    h, w = frame.shape[:2]
    long_side = max(w, h)
    if long_side <= _PREVIEW_MAX:
        return frame
    scale = _PREVIEW_MAX / long_side
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def main():
    print("=== 智能人脸抓拍系统 ===")
    cfg = load_config()

    # 统计摄像头源：本地索引 + 网络 URL
    local_ids = cfg.get("CAM_ID", [])
    cam_urls = cfg.get("CAM_URLS", [])
    rotations = cfg.get("CAM_ROTATE", [])

    if not local_ids and not cam_urls:
        print("[FATAL] 未配置任何摄像头：CAM_ID 和 CAM_URLS 均为空，请编辑 option.ini。")
        sys.exit(1)

    # 组装摄像头源：(source, label, display_rotation)
    overrides = cfg.get("CAM_OVERRIDES", [])
    sources = []
    for i, cam_id in enumerate(local_ids):
        rot = rotations[i] if i < len(rotations) else 0
        sources.append((cam_id, None, rot, i))
    offset = len(local_ids)
    for j, url in enumerate(cam_urls):
        idx = offset + j
        rot = rotations[idx] if idx < len(rotations) else 0
        sources.append((url, None, rot, idx))

    print(f"[INFO] 共配置 {len(sources)} 路摄像头（本地 {len(local_ids)} + 网络 {len(cam_urls)}）")

    alarms = []
    for source, label, rot, cam_idx in sources:
        try:
            # 合并全局配置与该摄像头的独立覆盖
            cam_cfg = dict(cfg)
            if cam_idx < len(overrides) and overrides[cam_idx]:
                cam_cfg.update(overrides[cam_idx])
            alarm = FaceAlarm(source, cam_cfg, camera_label=label, display_rotation=rot)
            alarms.append(alarm)
        except Exception as e:
            print(f"[ERROR] 初始化摄像头 {source} 失败: {e}")

    if not alarms:
        print("[FATAL] 没有可用的摄像头，程序退出。")
        sys.exit(1)

    print("[INFO] 系统启动成功。按 'q' 退出，右键画面切换旋转，双击画面触发对焦。")

    # 为每路摄像头注册鼠标回调
    for alarm in alarms:
        win_name = f"Face Alarm - Cam {alarm.camera_label}"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(win_name, _on_mouse, alarm)

    try:
        while True:
            for alarm in alarms:
                ret, frame = alarm.read_frame()
                if not ret:
                    continue
                processed_frame = alarm.process_frame(frame)
                if cfg["PREVIEW"]:
                    win_name = f"Face Alarm - Cam {alarm.camera_label}"
                    # 检查窗口是否已被关闭
                    try:
                        visible = cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE)
                        if visible < 1:
                            continue
                    except Exception:
                        continue
                    # 缩放到 480p 显示
                    display_frame = _fit_preview(processed_frame)
                    cv2.imshow(win_name, display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[INFO] 用户强制中断。")
    finally:
        for alarm in alarms:
            if alarm.cap:
                alarm.cap.release()
        cv2.destroyAllWindows()
        print("[INFO] 资源已释放，程序退出。")


if __name__ == "__main__":
    main()
