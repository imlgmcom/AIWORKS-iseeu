import os
import sys
import cv2
import numpy as np

from .config import resolve_path, PROJECT_ROOT


class FaceRecognizer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.enabled = cfg.get("ENABLE_RECOGNITION", False)
        self.threshold = cfg.get("RECOGNITION_THRESHOLD", 0.45)
        self.templates = {}

        if not self.enabled:
            print("[INFO] 人脸识别已关闭")
            return

        try:
            from insightface.app import FaceAnalysis
            model_root = PROJECT_ROOT
            self.app = FaceAnalysis(
                name="buffalo_l",
                root=model_root,
                providers=["CPUExecutionProvider"],
            )
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            print("[OK] InsightFace 模型加载成功")
        except Exception as e:
            print(f"[ERROR] InsightFace 初始化失败: {e}")
            self.enabled = False
            return

        self._load_templates()

    def _load_templates(self):
        face_dir = resolve_path("face")
        if not os.path.isdir(face_dir):
            print(f"[WARNING] 人脸目录不存在: {face_dir}")
            return

        for fname in sorted(os.listdir(face_dir)):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue

            name = os.path.splitext(fname)[0]
            img_path = os.path.join(face_dir, fname)
            mp3_path = os.path.join(face_dir, f"{name}.mp3")

            img = cv2.imdecode(
                np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if img is None:
                print(f"[WARNING] 无法读取模板图像: {img_path}")
                continue

            faces = self.app.get(img)
            if not faces:
                print(f"[WARNING] 模板 '{name}' 中未检测到人脸，已跳过")
                continue

            if len(faces) > 1:
                print(f"[WARNING] 模板 '{name}' 检测到多张人脸，使用最大的一张")
                best_face = max(faces, key=lambda f: f.bbox[2] - f.bbox[0])
            else:
                best_face = faces[0]

            self.templates[name] = {
                "embedding": best_face.embedding,
                "mp3": mp3_path if os.path.exists(mp3_path) else None,
            }
            status = f"[OK] 加载模板: {name}"
            if self.templates[name]["mp3"]:
                status += f" (提示音: face/{name}.mp3)"
            else:
                status += " (无提示音)"
            print(status)

        if self.templates:
            print(f"[INFO] 共加载 {len(self.templates)} 个人脸模板")
        else:
            print("[WARNING] 未加载任何人脸模板，识别功能将无效")
            self.enabled = False

    @staticmethod
    def _compute_yaw(face):
        """从 InsightFace 关键点计算偏航角（度）。

        kps: 5 个关键点 [右眼, 左眼, 鼻尖, 右嘴角, 左嘴角]
        通过鼻尖与双眼的水平距离比值估算偏航角，
        与 MediaPipe 的 calculate_yaw 算法一致，确保两套检测标准统一。
        """
        try:
            kps = face.kps
            if kps is None:
                return 90
            right_eye, left_eye, nose = kps[0], kps[1], kps[2]
            dist_r = abs(nose[0] - right_eye[0])
            dist_l = abs(nose[0] - left_eye[0])
            if dist_l == 0 or dist_r == 0:
                return 90
            ratio = dist_r / (dist_l + 1e-6)
            return abs((ratio - 1.0) * 60)
        except Exception:
            return 90

    def recognize(self, frame):
        """对画面进行人脸识别，返回匹配到的身份名称。

        流程：
        1. InsightFace 检测画面中所有人脸
        2. 按面积降序排序，优先识别最大（最可能正面面对镜头）的人脸
        3. 用 MAX_YAW_ANGLE 过滤侧脸，避免 embedding 质量差导致误识别
        4. 仅对通过姿态过滤的人脸进行模板匹配

        返回: (name, mp3_path) 或 (None, None)
        """
        if not self.enabled or not self.templates:
            return None, None

        faces = self.app.get(frame)
        if not faces:
            return None, None

        # 按人脸面积降序排序，优先识别最大的人脸
        faces_sorted = sorted(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
            reverse=True,
        )

        max_yaw = self.cfg.get("MAX_YAW_ANGLE", 30)

        for face in faces_sorted:
            # 跳过侧脸：偏航角过大的人脸 embedding 质量差，容易误识别
            yaw = self._compute_yaw(face)
            if yaw >= max_yaw:
                continue

            embedding = face.embedding
            if embedding is None:
                continue

            best_name = None
            best_score = -1

            for name, tmpl in self.templates.items():
                score = self._cosine_similarity(embedding, tmpl["embedding"])
                if score > best_score:
                    best_score = score
                    best_name = name

            if best_score >= self.threshold and best_name:
                mp3_path = self.templates[best_name]["mp3"]
                return best_name, mp3_path

        return None, None

    @staticmethod
    def _cosine_similarity(a, b):
        a = np.asarray(a)
        b = np.asarray(b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def get_all_names(self):
        return list(self.templates.keys())
