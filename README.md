# 🐾 Windows 智能桌面宠物助手

一个基于 **PyQt6** 的 Windows 桌面宠物：常驻桌面、可拖拽，支持天气查询、AI 对话、
系统状态监控与出行建议。天气服务使用免费 API，无需注册即可运行。

---

## 一、运行环境

| 项目 | 说明 |
|---|---|
| Python | 3.10+（实测 3.12.7） |
| 操作系统 | Windows 10 / 11 |
| 第三方依赖 | `PyQt6`、`requests`、`psutil` |
| 可选依赖 | `sentence-transformers`（RAG 知识库的真实向量检索，缺失时自动降级） |

```bash
pip install PyQt6 requests psutil
python main.py
```

---

## 二、交互方式

| 操作 | 功能 |
|---|---|
| 左键单击 | 打开 AI 对话窗口（默认免费本地对话） |
| 左键双击 | 查询天气 + 出行建议（气泡显示在宠物头顶） |
| 左键拖拽 | 移动宠物位置，**松手即自动保存** |
| 右键单击 | 菜单：AI 对话 / 查询天气 / 系统状态 / 设置 / 退出 |

对话窗口中还支持插件命令：`/天气 北京`、`/weather Shanghai`。

---

## 三、系统架构

### 3.1 模块分层

```
                    ┌──────────────┐
                    │   main.py    │  组装模块 / 生命周期管理
                    └──────┬───────┘
          ┌────────────────┼─────────────────┐
          ▼                ▼                 ▼
   ┌─────────────┐  ┌────────────┐  ┌──────────────┐
   │ EventBus    │  │ PetWindow  │  │ SystemMonitor│
   │ PluginMgr   │  │  (主界面)   │  │  (后台线程)   │
   └──────┬──────┘  └──────┬─────┘  └──────┬───────┘
          │                │               │ 事件
          ▼                ▼               │
   ┌─────────────┐  ┌──────────────────┐  │
   │ plugins/    │  │ ChatDialog       │◄─┘
   │ weather_... │  │ SettingsDialog   │
   └─────────────┘  └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ AIService        │
                    │ WeatherService   │  ← 网络 / 业务服务层
                    │ SystemStatus     │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ DBManager        │  ← SQLite 设置持久化
                    │ config.py        │  ← 全局配置
                    └──────────────────┘
```

### 3.2 模块职责

| 模块 | 职责 | 是否主流程 |
|---|---|---|
| [main.py](main.py) | 应用入口：组装模块、启动监控线程与插件系统、异常处理 | ✅ |
| [pet_window.py](pet_window.py) | 桌面宠物主窗口：贴图绘制、气泡、点击/拖拽、右键菜单 | ✅ |
| [chat_dialog.py](chat_dialog.py) | AI 对话窗口：气泡式消息、异步回复、插件命令分发 | ✅ |
| [settings_dialog.py](settings_dialog.py) | 设置窗口：城市定位模式、多 AI 模型 API 配置 | ✅ |
| [ai_service.py](ai_service.py) | AI 服务：免费本地关键词对话 + 5 个 OpenAI 兼容模型 | ✅ |
| [weather_service.py](weather_service.py) | 天气服务：wttr.in 查询、4 级 IP 定位容灾、中文翻译、出行建议 | ✅ |
| [system_status.py](system_status.py) | 系统状态：CPU/内存/磁盘/网络/电池的即时采集与摘要 | ✅ |
| [system_monitor.py](system_monitor.py) | 后台监控线程：定时采集、阈值事件、历史记录 | ✅ |
| [plugin_manager.py](plugin_manager.py) | 事件总线（发布-订阅）与插件加载/命令路由 | ✅ |
| [plugins/](plugins/) | 插件目录，`weather_plugin.py` 提供 `/天气` 命令 | ✅ |
| [db_manager.py](db_manager.py) | SQLite 设置持久化（线程安全、连接即时关闭） | ✅ |
| [config.py](config.py) | 全局配置类：UI / 宠物 / 监控 / RAG / LLM | ✅ |
| [pet_ui.py](pet_ui.py) | 动画状态机版宠物 UI（自主巡逻 + 事件联动），独立演示 | ⭕ 可选 |
| [rag_engine.py](rag_engine.py) | 本地知识库：分块 → 向量化 → 检索 + LLM 流式客户端 | ⭕ 可选 |

`pet_ui.py` 与 `rag_engine.py` 不参与主流程，可单独运行演示：

```bash
python pet_ui.py       # 动画状态机 + 自主巡逻 + 事件联动演示
python rag_engine.py   # 离线验证「分块 → 向量化 → 检索」流程
```

### 3.3 事件驱动机制

`EventBus` 实现发布-订阅，用于解耦后台监控与 UI：

| 事件 | 触发时机 | 订阅方 |
|---|---|---|
| `monitor.snapshot` | 每次采集完成 | — |
| `monitor.cpu_high` | CPU 超阈值（10 秒冷却去抖） | `main.py` → 气泡提醒 |
| `monitor.mem_high` | 内存超阈值（10 秒冷却去抖） | `main.py` → 气泡提醒 |
| `monitor.load_change` | 综合负载等级变化 | `pet_ui.py` 状态切换 |
| `pet.show_bubble` | 插件请求显示气泡 | `pet_ui.py` |
| `llm.stream_start/token/end` | 大模型流式输出 | `pet_ui.py` |

---

## 四、关键设计说明

### 4.1 气泡为什么必须是独立顶层窗口

Qt 会把**子控件裁剪到父窗口矩形范围内**。气泡需要显示在宠物窗口上方（父窗口之外，
相对坐标为负），若做成 `PetWindow` 的子控件会被整个裁掉 —— 表现为
`isVisible() == True`、`opacity == 1.0`，但屏幕上看不到任何东西。

因此 `WeatherBubble` / `ChatBubble` 均为无父控件的顶层窗口：

```python
self.setWindowFlags(
    Qt.WindowType.Tool                    # 不在任务栏显示
    | Qt.WindowType.FramelessWindowHint   # 无边框
    | Qt.WindowType.WindowStaysOnTopHint  # 置顶
    | Qt.WindowType.WindowDoesNotAcceptFocus  # 不抢焦点
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)   # 背景透明
self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)   # 显示时不激活
self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # 鼠标穿透
```

定位全部改用屏幕绝对坐标，宠物拖动/巡逻时同步跟随。

### 4.2 截图验证方法

气泡这类"窗口可见性"问题无法靠 `isVisible()` 判断，必须实际截图比对：

```python
QApplication.primaryScreen().grabWindow(0, x, y, w, h).save("shot.png")
```

### 4.3 线程模型

| 任务 | 执行位置 | 原因 |
|---|---|---|
| 天气查询 | `WeatherWorker(QThread)` | 网络请求最长 10 秒，不能阻塞 UI |
| AI 对话 | `ChatWorker(QThread)` | API 请求最长 30 秒 |
| 系统监控采集 | `SystemMonitor` 守护线程 | 周期性采集，事件通知 UI |
| 设置读写 | 主线程 / 工作线程各自建连接 | SQLite 连接不跨线程共享 |

### 4.4 数据库

- 单表 `settings(key, value)`，`INSERT OR REPLACE` 写入
- **每次操作新建连接并用 `contextlib.closing` 显式关闭**：
  `with sqlite3.connect(...)` 只管理事务，不会关闭连接，长期运行会泄漏文件句柄
- 连接设置 `timeout=5.0`，避免工作线程与 UI 线程并发写入时立即报锁冲突

### 4.5 宠物形象与图标

形象图必须**带透明通道**。桌宠窗口是 `WA_TranslucentBackground` 的透明无边框窗口，
但窗口透明并不等于图片透明——若 PNG 自身是不透明的白底，角色就会被一个大白方块
包住，贴在什么壁纸上都很难看。

原始素材（8 张 720×720 左右的 DeepSeek 鲸鱼少女立绘）是**不透明的纯白背景**，
且带各种对话气泡、DeepSeek 界面截图、贴纸文字等浮层。抠图脚本保存在
[tools/cutout_states.py](tools/cutout_states.py)（离线构建工具，不参与程序运行）：

```bash
pip install pillow numpy scipy
python tools/cutout_states.py          # 重新生成 assets/states/*.png
```

逐张做了三步处理：

1. **抠底**：从图片四边做泛洪填充，把与边缘连通的近白像素（`min(RGB) ≥ 225`
   且饱和度低）置为透明。用泛洪而非"全局白色转透明"，是为了保住角色身上
   同样是白色的部分（围裙、头饰）——它们不与边缘连通，不会被误伤。
2. **去浮层**：气泡内部是白色、被深色描边围住，泛洪吃不到。处理方式是从气泡
   内部**指定种子点再泛洪**（描边天然挡住，不会外溢到角色），然后把这个区域
   **膨胀几像素吞掉描边环**；剩下的零散元件（文字、音符、问号、指人的手）
   靠**连通域分析**丢弃——只保留面积最大的那个连通域，也就是角色本体。
   个别图里角色与深色 UI 面板粘连，则按**颜色**擦除面板（面板是均匀的
   `RGB(28,32,41)`，与头发 `RGB(82,104,167)` 区分明显），断开粘连后
   连通域过滤即可生效。
3. **裁边**：按 alpha 包围盒裁掉四周留白，让角色在窗口里更大更居中。

图标 `assets/pet.ico` 内含 16/24/32/48/64/128/256 共 7 种尺寸，
在 `main.py` 中通过 `QApplication.setWindowIcon()` 设为应用级图标，
对话框标题栏与 Alt+Tab 都会显示宠物形象（多尺寸可保证小图标不糊）。

### 4.6 宠物状态切换

宠物有 7 套表情立绘，放在 `assets/states/`，由 `pet_window.py` 顶部的
`PET_STATES` 表驱动：

| 状态 | 表情 | 触发时机 |
|---|---|---|
| `idle` | 眯眼微笑 | 默认待机；其它状态超时后自动回退 |
| `greet` | 举手打招呼 | 程序启动 |
| `chat` | 眨眼俏皮 | 打开 AI 对话窗口 |
| `weather` | 惊讶摊手 | 查询天气 |
| `status` | 半月眼 | 查看系统状态 |
| `alert` | 晕乎乎吐舌 | CPU / 内存持续高负载 |
| `happy` | 闭眼唱歌 | AI 回复到达（订阅 `chat.reply` 事件） |

```python
pet.set_state("happy", revert_after_ms=4000)   # 4 秒后自动回到 idle
```

表里第 3 列是**缩放系数**：全身立绘铺满窗口，面部特写缩小到 0.9，
否则切换表情时会忽大忽小地跳。想换素材只要替换 `assets/states/*.png`
并保持文件名一致；也可以在数据库里把 `pet_image` 键设为某张图的路径，
让所有状态都用同一张图。

插件同样可以驱动表情——向总线发一个事件即可：

```python
bus.emit("pet.state", {"state": "happy", "revert_after_ms": 3000})
```

---

## 五、天气服务说明

```
IP 定位（4 级容灾）             天气查询
ipinfo.io          ─┐
ip-api.com          │          wttr.in/{city}?format=j1&lang=zh
ip.seeip.org        ├─► 城市 ──► 解析 current_condition
ipapi.co           ─┘                │
                                     ├─► 英文描述 → 中文翻译（23 种）
                                     ├─► 出行建议（雨/雪/雷/高温/低温/雾霾/湿度）
                                     └─► 气泡展示（15 秒淡出）
```

- **无需注册**：wttr.in 与全部 IP 定位接口均为免费公开服务
- **城市映射**：内置 45 个常用城市的中英文对照，兼容中英文手动输入
- **降级策略**：定位或查询失败时返回 `_fallback()` 结果，气泡提示错误而非崩溃

---

## 六、扩展方式

### 添加插件命令

在 `plugins/` 下新建继承 `PluginBase` 的类：

```python
from plugin_manager import EventBus, PluginBase

class MyPlugin(PluginBase):
    name = "示例插件"
    version = "1.0.0"

    def setup(self):
        self.register_command("你好", "示例命令", self.handle)

    def handle(self, args: dict) -> str:
        return f"收到参数: {args.get('args')}"
```

重启应用后，在对话窗口输入 `/你好` 即可触发。

### 添加 AI 模型

在 [ai_service.py](ai_service.py) 与 [settings_dialog.py](settings_dialog.py) 的
`AI_MODELS` 字典中同步添加条目（两处 key 必须一致，API Key 以
`模型名_api_key` 的形式存库）。
