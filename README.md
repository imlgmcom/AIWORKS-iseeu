# iseeu · 智能人脸抓拍偷窥的老六系统

基于 MediaPipe 1.0 和 InsightFace 的实时人脸检测与抓拍系统，支持人脸识别、多摄像头（本地+网络）管理、ROI 区域检测、专属提示音、DroidCam 自动对焦等功能。

识别所需模型请自行下载

## 项目原理

系统采用状态机驱动架构，通过 MediaPipe 进行实时人脸检测，结合 InsightFace 实现人脸识别，支持自定义每个人脸的专属提示音和抓拍命名。

### 核心流程

```
摄像头输入 ──▶ 预处理器（变焦/旋转） ──▶ MediaPipe 人脸检测
                                          │
                                   正脸过滤（YAW<30°）
                                          │
                                          ▼
                                   InsightFace 人脸识别
                                          │
                                    模板匹配 + 侧脸过滤
                                          │
                                          ▼
                                   状态机判断（idle→waiting→bursting→cooldown）
                                          │
                                          ▼
                                    抓拍 + 专属提示音
```

### 状态机流转

```
idle ──检测到正脸──▶ waiting ──延迟──▶ bursting ──连拍──▶ cooldown ──冷却──▶ idle
```

| 状态 | 说明 |
|------|------|
| `idle` | 空闲状态，按 `CHECK_INTERVAL` 间隔检测 |
| `waiting` | 检测到人脸后等待 `TRIGGER_DELAY` 秒 |
| `bursting` | 连拍状态，按 `BURST_INTERVAL` 间隔拍 `BURST_COUNT` 张 |
| `cooldown` | 冷却状态，防止频繁触发 |

### 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 开发语言（项目内置便携版） |
| OpenCV | 5.x | 视频采集与图像处理 |
| MediaPipe | 1.0 | 人脸关键点检测（新版 API） |
| InsightFace | buffalo_l | 人脸识别（5 点关键点 + 特征向量） |
| ONNX Runtime | - | AI 模型推理 |
| Windows MCI | - | 音频播放（零外部依赖） |
| HTTP Client | - | DroidCam MJPEG 流读取 |

## 作用用途

- **安防监控**：检测陌生人进入指定区域自动报警
- **考勤签到**：识别员工身份自动抓拍存档
- **访客管理**：识别访客身份触发欢迎提示
- **多摄像头融合**：本地 USB 摄像头 + 手机 DroidCam 网络摄像头同时工作

## 目录结构

```
iseeu/
├── iseeu/                          # Python 包（模块化代码）
│   ├── __init__.py                 # 包标识
│   ├── audio_player.py             # 音频播放（Windows MCI）
│   ├── config.py                   # 配置管理（option.ini 解析 + 路径解析）
│   ├── detector.py                 # MediaPipe 人脸检测（ROI + YAW 过滤）
│   ├── face_alarm.py               # 核心业务逻辑（状态机 + 变焦 + 旋转）
│   ├── main.py                     # 程序入口（多摄像头调度 + 预览）
│   ├── mjpeg_stream.py             # DroidCam MJPEG 流读取器
│   └── recognizer.py               # InsightFace 人脸识别（YAW 过滤 + 面积排序）
├── face/                           # 人脸模板与提示音
│   ├── 姓名.jpg                    # 人脸模板图片（正脸清晰照）
│   └── 姓名.mp3                    # 对应提示音（可选）
├── models/
│   ├── buffalo_l/                  # InsightFace 预训练模型
│   │   ├── det_10g.onnx            #   人脸检测
│   │   ├── 2d106det.onnx           #   106 点关键点
│   │   ├── 1k3d68.onnx             #   3D 68 点关键点
│   │   ├── genderage.onnx          #   性别/年龄
│   │   └── w600k_r50.onnx          #   人脸识别
│   └── mediapipe/                  # MediaPipe 人脸检测模型
│       ├── blaze_face_short_range.tflite   # 短距离模型
│       └── blaze_face_full_range.tflite    # 全距离模型
├── py312/                          # Python 3.12 便携版（已含依赖）
├── snapshots/                      # 抓拍照片输出目录
├── tools/                          # 初始化工具
│   ├── setup.py                    #   首次运行引导（中文 UI）
│   └── check_cameras.py            #   摄像头检测工具
├── alarm.mp3                       # 默认报警音
├── iseeu.py                        # 启动代理
├── option.ini                      # 配置文件
├── run.bat                         # 启动脚本
└── first_run.bat                   # 首次运行初始化脚本
```

## 模块说明

### audio_player.py

使用 Windows 原生 `mciSendString` API 实现零依赖音频播放，支持 mp3/wav 等格式。

### config.py

负责加载 `option.ini` 配置，定义路径解析规则，支持：
- `CAM_URLS` 网络摄像头 URL 规范化（自动补全 `http://` 和 `/video` 路径）
- `DROIDCAM_RESOLUTION` 预设分辨率（240p/480p/720p/1080p 等）
- 每路摄像头独立配置覆盖（`[Cam0]`/`[Cam1]` 分段）

### detector.py

封装 MediaPipe 1.0 人脸检测（`vision.FaceDetector`），支持：
- **ROI 网格检测**：将画面划分为网格，仅检测指定区域
- **YAW 角度过滤**：通过关键点比例估算头部偏转角度，过滤侧脸
- **短距离/全距离模型**切换

### mjpeg_stream.py

自定义 DroidCam MJPEG 流读取器（OpenCV 原生不支持 DroidCam 的 multipart MJPEG）：
- 后台线程持续读帧，低延迟
- 自动重连（手机断开/休眠后恢复）
- 定期自动对焦（`/cam/1/af` API）

### recognizer.py

基于 InsightFace buffalo_l 模型实现人脸识别：
- **YAW 过滤**：识别阶段同样过滤侧脸，防止 embedding 质量差导致误识别
- **面积排序**：按人脸面积降序识别，优先最大正脸
- 自动扫描 `face/` 文件夹加载人脸模板
- 使用余弦相似度进行人脸比对

### face_alarm.py

实现状态机逻辑，协调检测、识别、抓拍、报警四大功能：
- **数字变焦**：按中心裁剪放大（放大 2 倍）
- **方向旋转**：校正画面方向（DroidCam 横屏→竖屏）
- **自动重连**：网络摄像头断流后自动恢复

### main.py

管理多摄像头调度，组织主循环：
- 多路摄像头并行处理（本地 + 网络）
- 预览窗口缩放至 480p（最长边 480px）
- 鼠标交互：右键切换旋转、双击触发对焦
- 关闭预览窗口后程序继续运行

## 使用方法

### 首次运行

双击 `first_run.bat`，自动完成：
1. 下载 Python 3.12（如未检测到）
2. 安装依赖（清华源加速）
3. 配置 pip 镜像源
4. 检测摄像头列表
5. 引导用户修改 `option.ini`

### 日常启动

```bash
# 方式一：双击启动
run.bat

# 方式二：命令行启动
py312\python.exe iseeu.py
```

### 添加人脸模板

1. 在 `face/` 文件夹中放入人脸图片（`.jpg` 格式，正脸清晰）
2. 放入同名的提示音文件（`.mp3` 格式，可选）

```
face/
├── 张三.jpg    # 人脸模板（正脸照）
├── 张三.mp3    # 专属提示音（可选）
├── 李四.jpg
└── 李四.mp3
```

### 操作说明

| 操作 | 说明 |
|------|------|
| 按 `q` | 退出程序（需预览窗口获焦） |
| 预览窗口右键 | 循环切换旋转：0°→90°→180°→270° |
| 预览窗口双击左键 | 触发该 DroidCam 自动对焦 |
| 关闭预览窗口 | 程序继续运行，仅停止该路预览 |

## 配置说明

编辑 `option.ini` 文件。

### 基础配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CAM_ID` | 0 | 本地摄像头索引，多个用逗号分隔（如 `0,1`） |
| `CAM_URLS` | - | 网络摄像头 URL（如 `192.168.3.161:4747`），支持 DroidCam |
| `CAM_ROTATE` | 0,90 | 每路摄像头旋转角度，按 CAM_ID + CAM_URLS 顺序对应 |
| `PREVIEW` | 1 | 是否显示预览窗口 |
| `SNAPSHOT_DIR` | snapshots | 抓拍照片保存目录 |
| `ALARM_SOUND` | alarm.mp3 | 默认报警音文件 |

### 网络摄像头配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DROIDCAM_RESOLUTION` | 1080p | DroidCam 清晰度（240p/480p/720p/1080p） |
| `DROIDCAM_AF_INTERVAL` | 30 | 自动对焦间隔（秒），0=禁用定期对焦 |
| `ZOOM` | 1.0 | 数字变焦倍数（按中心放大），2.0 = 放大 2 倍 |

### 检测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CHECK_INTERVAL` | 5 | 每 N 帧检测一次（降低性能消耗） |
| `MIN_DETECTION_CONFIDENCE` | 0.8 | MediaPipe 最小检测置信度 |
| `MAX_YAW_ANGLE` | 30 | 最大允许头部偏转角度（度），超过则过滤侧脸 |
| `Face_Detection_Model` | 1 | 0=短距离模型，1=全距离模型 |

### 抓拍参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TRIGGER_DELAY` | 0.5 | 检测到人脸后延迟触发时间（秒） |
| `BURST_COUNT` | 3 | 连拍张数 |
| `BURST_INTERVAL` | 1.0 | 连拍间隔（秒） |
| `COOLDOWN_SECONDS` | 6 | 两次触发间的冷却时间（秒） |

### ROI 区域配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ROI_MODE` | 2 | 0=全屏检测，1=全网格检测，2=指定网格检测 |
| `ROI_GRIDS` | 2x2 | 网格划分（2x2, 3x3, 1x4 等） |
| `ROI_TARGETS` | 3 | 目标网格序号（从1开始，逗号分隔） |

网格编号示例（2x2）：

```
┌──────┬──────┐
│  1   │  2   │
├──────┼──────┤
│  3   │  4   │
└──────┴──────┘
```

`ROI_TARGETS = 1,3` 表示只检测左上和左下区域。

### 人脸识别配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_RECOGNITION` | 1 | 开/关人脸识别 |
| `FACE_DIR` | face | 人脸模板目录 |
| `RECOGNITION_THRESHOLD` | 0.45 | 识别相似度阈值（0~1，越高越严格） |

### 每路摄像头独立配置

在 `[Cam0]`、`[Cam1]` 等分段中按摄像头单独覆盖全局配置：

```ini
[Cam0]              ; 第1路：本地摄像头
ROI_MODE = 2
ROI_GRIDS = 2x2
ROI_TARGETS = 3
ZOOM = 1.0

[Cam1]              ; 第2路：DroidCam 网络摄像头
ROI_MODE = 2
ROI_GRIDS = 1x4
ROI_TARGETS = 2,3
ZOOM = 2.0          ; DroidCam 放大2倍，人脸占比更大
```

可覆盖参数：`ROI_MODE` / `ROI_GRIDS` / `ROI_TARGETS` / `Face_Detection_Model` / `MIN_DETECTION_CONFIDENCE` / `MAX_YAW_ANGLE` / `ZOOM`

## 抓拍命名规则

- **识别成功**：`姓名_时间戳_序号.jpg`（如 `张三_1700000000_1.jpg`）
- **识别失败**：`capture_时间戳_序号.jpg`（如 `capture_1700000000_1.jpg`）

## 注意事项

1. **摄像头 ID**：本地摄像头 ID 可能为 0 或 1，如无画面请尝试修改
2. **Python 版本**：当前使用 3.12，MediaPipe 1.0 要求 Python >= 3.9
3. **模型路径**：InsightFace 模型需放在 `models/buffalo_l/`，MediaPipe 模型需放在 `models/mediapipe/`
4. **中文路径**：项目已处理中文文件名保存问题（`cv2.imencode` + `buffer.tofile`）
5. **DroidCam 连接**：确保手机和电脑在同一局域网，DroidCam 处于运行状态
6. **性能优化**：`CHECK_INTERVAL` 值越大性能越好，但检测频率越低
7. **侧脸过滤**：检测和识别两阶段均进行 YAW 角度过滤，防止侧脸误识别

## 许可证

本项目仅供学习和研究使用。
