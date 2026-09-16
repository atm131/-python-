"""
桌面宠物 UI 模块
基于 PyQt6 实现透明无边框窗口、图片宠物、拖拽移动、天气气泡。

交互方式：
- 左键单击：打开 AI 对话窗口
- 左键双击：查询天气 + 出行建议（气泡显示）
- 左键拖拽：移动宠物位置，松手即保存
- 右键单击：菜单（AI 对话 / 查询天气 / 系统状态 / 今日课程 / 设置 / 退出）

实现要点：
天气气泡是独立顶层窗口而非子控件 —— Qt 会将子控件裁剪到父窗口
矩形内，而气泡需显示在宠物窗口上方，做成子控件会完全不可见。
"""
from __future__ import annotations

import os
from PyQt6.QtCore import QPoint, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from course_service import CourseService
from db_manager import DBManager
from settings_dialog import SettingsDialog
from chat_dialog import ChatDialog
from weather_service import WeatherService
from system_status import SystemStatus


# ─── 宠物形象状态表 ────────────────────────────────────────
# 状态名 -> (中文说明, 图片文件, 缩放系数)
# 图片放在 assets/states/ 下，均为透明背景的鲸鱼少女立绘。
# 缩放系数用于微调各状态在窗口里的相对大小（立绘远近不同）。
PET_STATES: dict[str, tuple[str, str, float]] = {
    # 第 3 列是缩放系数：全身立绘铺满窗口，面部特写缩小一点，
    # 这样切换表情时不会忽大忽小地跳。可按喜好自行调整。
    "idle":    ("待机",     "idle.png",    0.90),
    "greet":   ("打招呼",   "greet.png",   1.00),
    "chat":    ("对话中",   "chat.png",    0.90),
    "weather": ("查天气",   "weather.png", 1.00),
    "status":  ("系统状态", "status.png",  0.90),
    "alert":   ("高负载",   "alert.png",   0.90),
    "happy":   ("开心",     "happy.png",   1.00),
}

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "states")


# ─── 天气查询线程 ──────────────────────────────────────────

class WeatherWorker(QThread):
    """后台线程查询天气，避免阻塞 UI"""
    finished = pyqtSignal(dict)

    def __init__(self, service: WeatherService):
        super().__init__()
        self.service = service

    def run(self):
        result = self.service.fetch()
        self.finished.emit(result)


# ─── 天气气泡组件 ──────────────────────────────────────────

class WeatherBubble(QWidget):
    """
    天气信息气泡，显示在宠物旁边。
    半透明圆角矩形，自动隐藏。

    实现要点：
    必须做成【独立顶层窗口】而非 PetWindow 的子控件。
    因为 Qt 会把子控件裁剪到父窗口范围内，而气泡需要显示在
    宠物窗口上方（父窗口矩形之外），作为子控件时会被整个裁掉、完全不可见。
    """

    def __init__(self, ui_config):
        super().__init__(None)  # 顶层窗口，无父控件
        self.ui_config = ui_config
        self._text = ""
        self._opacity = 0.0
        self._visible = False
        self._fading_out = False
        self._fade_out_timer = None  # 淡出定时器

        # 顶层窗口标志：
        # Tool                    — 不在任务栏显示
        # FramelessWindowHint     — 无边框
        # WindowStaysOnTopHint    — 置顶
        # WindowDoesNotAcceptFocus— 不抢焦点（不影响用户正在操作的窗口）
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 鼠标穿透：气泡不拦截点击
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(self.ui_config.bubble_max_width)

        # 淡出动画定时器
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_step)

    def show_weather(self, data: dict, duration_ms: int = 8000):
        """格式化并显示天气信息"""
        if data.get("error"):
            text = f"⚠️ {data['error']}"
        else:
            text = (
                f"📍 {data['city']}\n"
                f"🌡️ {data['temp']}℃（体感 {data['feels_like']}℃）\n"
                f"🌤️ {data['description']}\n"
                f"💧 湿度 {data['humidity']}%\n"
                f"\n💡 {data['advice']}"
            )
        self.show_text(text, duration_ms)

    def show_text(self, text: str, duration_ms: int):
        """显示文本气泡（自动调整尺寸、置顶、定时淡出）"""
        # 取消之前的淡出定时器
        if self._fade_out_timer:
            self._fade_out_timer.stop()
            self._fade_out_timer = None

        self._text = text
        self._opacity = 1.0
        self._visible = True
        self._fading_out = False
        self._fade_timer.stop()
        self._adjust_size()
        self.update()
        # 顶层窗口需显式显示并置顶，否则不会绘制
        self.show()
        self.raise_()

        # 创建新的淡出定时器（父对象为 self，随窗口销毁自动清理）
        self._fade_out_timer = QTimer(self)
        self._fade_out_timer.setSingleShot(True)
        self._fade_out_timer.timeout.connect(self._start_fade_out)
        self._fade_out_timer.start(duration_ms)

    def _adjust_size(self):
        """根据文字内容自动调整气泡尺寸"""
        from PyQt6.QtGui import QFontMetrics
        from PyQt6.QtCore import QRect
        font = QFont(self.ui_config.font_family, 10)
        metrics = QFontMetrics(font)
        rect = metrics.boundingRect(
            QRect(0, 0, self.ui_config.bubble_max_width - 24, 1000),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        self.setFixedSize(rect.width() + 24, rect.height() + 20)

    def _start_fade_out(self):
        self._fading_out = True
        self._fade_out_timer = None
        self._fade_timer.start(50)

    def _fade_step(self):
        if not self._fading_out:
            return
        self._opacity -= 0.04
        if self._opacity <= 0:
            self._opacity = 0
            self._visible = False
            self._fading_out = False
            self._fade_timer.stop()
            self.hide()  # 顶层窗口需要显式隐藏
        self.update()

    def hide_bubble(self):
        """立即隐藏气泡并停止所有定时器"""
        if self._fade_out_timer:
            self._fade_out_timer.stop()
            self._fade_out_timer = None
        self._fade_timer.stop()
        self._opacity = 0.0
        self._visible = False
        self._fading_out = False
        self.hide()

    def paintEvent(self, event):
        if not self._visible or self._opacity <= 0:
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(2, 2, self.width() - 4, self.height() - 4,
                            self.ui_config.bubble_radius, self.ui_config.bubble_radius)
        painter.fillPath(path, QColor(self.ui_config.bubble_bg))

        painter.setPen(QColor(self.ui_config.bubble_fg))
        font = QFont(self.ui_config.font_family, 10)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(12, 10, -12, -10),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        painter.end()


# ─── 桌面宠物主窗口 ────────────────────────────────────────

class PetWindow(QWidget):
    """
    桌面宠物主窗口。

    交互方式：
    - 左键单击 → 打开 AI 对话窗口
    - 左键双击 → 查询天气 + 出行建议
    - 左键拖拽 → 移动（松手保存位置）
    - 右键菜单 → 对话 / 天气 / 系统状态 / 今日课程 / 设置 / 退出
    """

    def __init__(self, db: DBManager, weather_service: WeatherService, ui_config,
                 plugin_manager=None):
        super().__init__()
        self.db = db
        self.weather_service = weather_service
        self.ui_config = ui_config
        self.plugin_manager = plugin_manager  # 传入对话窗口，支持 /命令
        self._weather_worker: WeatherWorker | None = None

        # 拖拽状态
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_threshold = 5
        self._mouse_press_pos = QPoint()

        # 单击/双击区分：复用同一个定时器，避免每次点击都新建子定时器越积越多
        self._last_click_time = 0.0
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._execute_single_click)

        # 加载全部状态立绘，默认待机
        self._pet_pixmaps = self._load_pet_images()
        self._state = "idle"

        # 状态自动回退定时器（如"查天气"表情维持几秒后回到待机）
        self._revert_timer = QTimer(self)
        self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(lambda: self.set_state("idle"))

        # 初始化窗口
        self._init_window()

        # 天气气泡（独立顶层窗口，不随宠物窗口被裁剪）
        self.bubble = WeatherBubble(ui_config)

        # 订阅事件总线：对话回复完成 → 开心表情；插件也可通过 pet.state 事件切换形象
        if plugin_manager is not None:
            bus = plugin_manager.bus
            bus.on("chat.reply", lambda e: self.set_state("happy", 4000))
            bus.on("pet.state", lambda e: self.set_state(
                e.data.get("state", "idle"), e.data.get("revert_after_ms", 0)))

    # ── 图片加载 ──────────────────────────────────

    def _placeholder_pixmap(self) -> QPixmap:
        """所有立绘都加载失败时的兜底占位图（青色圆）"""
        width = int(self.db.get("pet_width", "200"))
        height = int(self.db.get("pet_height", "200"))
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PyQt6.QtGui import QBrush, QPen
        painter.setBrush(QBrush(QColor("#4ecdc4")))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(10, 10, width - 20, height - 20)
        painter.end()
        return pixmap

    def _load_pet_images(self) -> dict[str, QPixmap]:
        """
        加载全部状态的宠物立绘，返回 {状态名: QPixmap}。

        图片来自 assets/states/（相对项目路径，换台电脑也能用）。
        若数据库 pet_image 指定了自定义图片，则所有状态都用它，
        方便只想换一张图、不想准备整套立绘的场景。
        """
        width = int(self.db.get("pet_width", "200"))
        height = int(self.db.get("pet_height", "200"))
        project_dir = os.path.dirname(os.path.abspath(__file__))

        def fit(pm: QPixmap, scale: float) -> QPixmap:
            return pm.scaled(
                int(width * scale), int(height * scale),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        # 自定义单图：所有状态共用
        custom = self.db.get("pet_image", "")
        if custom:
            path = custom if os.path.isabs(custom) else os.path.join(project_dir, custom)
            pm = QPixmap(path)
            if not pm.isNull():
                print(f"[Pet] 使用自定义形象: {path}")
                return {key: fit(pm, 1.0) for key in PET_STATES}
            print(f"[Pet] ⚠️ 自定义形象加载失败: {path}")

        pixmaps: dict[str, QPixmap] = {}
        for key, (label, filename, scale) in PET_STATES.items():
            pm = QPixmap(os.path.join(STATE_DIR, filename))
            if pm.isNull():
                print(f"[Pet] ⚠️ 状态立绘缺失: {filename}（{label}）")
                continue
            pixmaps[key] = fit(pm, scale)

        if not pixmaps:
            print("[Pet] ⚠️ 未找到任何状态立绘，使用占位图")
            pixmaps["idle"] = self._placeholder_pixmap()
        elif "idle" not in pixmaps:
            pixmaps["idle"] = next(iter(pixmaps.values()))
        return pixmaps

    # ── 状态切换 ──────────────────────────────────

    def set_state(self, state: str, revert_after_ms: int = 0):
        """
        切换宠物形象。

        state           —— PET_STATES 中的状态名
        revert_after_ms —— >0 时，指定毫秒后自动回到 idle
        """
        if state not in self._pet_pixmaps:
            return
        self._revert_timer.stop()
        if state != self._state:
            self._state = state
            self.update()
        if revert_after_ms > 0 and state != "idle":
            self._revert_timer.start(revert_after_ms)

    @property
    def state(self) -> str:
        """当前状态名"""
        return self._state

    # ── 窗口初始化 ────────────────────────────────

    def _init_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        width = int(self.db.get("pet_width", "200"))
        height = int(self.db.get("pet_height", "200"))
        self.setFixedSize(width, height)

        # 初始位置
        screen = QApplication.primaryScreen().geometry()
        init_x = self.db.get("window_x", "")
        init_y = self.db.get("window_y", "")
        x = int(init_x) if init_x else screen.width() - width - 100
        y = int(init_y) if init_y else screen.height() - height - 100
        self.move(x, y)

    # ── 绘制 ──────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pixmap = self._pet_pixmaps.get(self._state) or self._pet_pixmaps["idle"]
        # 水平居中、底边对齐：各状态共用同一条"地面线"，切换时不会上下跳
        x = (self.width() - pixmap.width()) // 2
        y = self.height() - pixmap.height()
        painter.drawPixmap(x, y, pixmap)
        painter.end()

    # ── 鼠标事件 ──────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._mouse_press_pos = event.globalPosition().toPoint()
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._mouse_press_pos
            if not self._dragging and (abs(delta.x()) > self._drag_threshold
                                        or abs(delta.y()) > self._drag_threshold):
                self._dragging = True
            if self._dragging:
                new_pos = current_pos - self._drag_start_pos
                self.move(new_pos)
                # 气泡是独立窗口，拖动时需跟随宠物
                if self.bubble.isVisible():
                    self._position_bubble()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                # 拖拽结束立即持久化位置，避免异常退出时丢失
                self._save_position()
            else:
                self._handle_click()
            self._dragging = False

    def _handle_click(self):
        """处理左键点击：单击 vs 双击"""
        import time
        current_time = time.time()

        # 400ms 内的第二次点击视为双击：取消待执行的单击，触发双击
        if 0 < current_time - self._last_click_time < 0.4:
            self._single_click_timer.stop()
            self._last_click_time = 0.0
            self._on_double_click()
            return

        # 记录本次点击时间，400ms 内没有第二次点击则执行单击
        self._last_click_time = current_time
        self._single_click_timer.start(400)

    def _execute_single_click(self):
        """执行单击操作（400ms 内没有第二次点击）"""
        self._last_click_time = 0.0
        self._on_single_click()

    def _on_single_click(self):
        """单击：打开对话窗口"""
        self._open_chat()

    def _on_double_click(self):
        """双击：显示随机问候"""
        self._show_random_greeting()

    # ── 右键菜单 ──────────────────────────────────

    def _show_context_menu(self, pos: QPoint):
        """显示右键上下文菜单"""
        self._build_context_menu().exec(pos)

    def _build_context_menu(self) -> QMenu:
        """
        构建右键菜单。

        拆出独立方法是为了可测试：菜单 exec() 会阻塞事件循环，
        测试里改成断言菜单项列表，不必真的弹出。
        """
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #4ecdc4;
                color: #000;
            }
        """)

        # 对话
        act_chat = QAction("💬 AI 对话", self)
        act_chat.triggered.connect(self._open_chat)
        menu.addAction(act_chat)

        # 天气查询
        act_weather = QAction("🌤️ 查询天气", self)
        act_weather.triggered.connect(self._query_weather)
        menu.addAction(act_weather)

        # 系统状态
        act_system = QAction("📊 系统状态", self)
        act_system.triggered.connect(self._show_system_status)
        menu.addAction(act_system)

        # 今日课程（数据来自设置页「📅 课程表」）
        act_course = QAction("📅 今日课程", self)
        act_course.triggered.connect(self._show_today_courses)
        menu.addAction(act_course)

        menu.addSeparator()

        # 设置
        act_settings = QAction("⚙️ 设置", self)
        act_settings.triggered.connect(self._open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()

        # 退出
        act_quit = QAction("🚪 退出", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_quit)

        return menu

    # ── 天气查询 ──────────────────────────────────

    def _query_weather(self):
        """在后台线程中查询天气"""
        if self._weather_worker and self._weather_worker.isRunning():
            return

        self.set_state("weather", 15000)
        self.show_bubble("正在查询天气...", 3000)

        # 旧 worker 已结束，直接丢弃换新（结束的 QThread 析构是安全的）
        self._weather_worker = WeatherWorker(self.weather_service)
        self._weather_worker.finished.connect(self._on_weather_result)
        self._weather_worker.start()

    def _on_weather_result(self, data: dict):
        """天气查询完成回调"""
        if data.get("error"):
            self.show_bubble(f"天气查询失败: {data['error']}", 5000)
        else:
            # 先填充内容（尺寸随文字变化），再定位
            self.bubble.show_weather(data, duration_ms=15000)
            self._position_bubble()

    # ── 对话窗口 ──────────────────────────────────

    def _open_chat(self):
        """打开对话窗口"""
        self.set_state("chat", 3000)
        dlg = ChatDialog(self.db, self, plugin_manager=self.plugin_manager)
        dlg.exec()
        # 对话窗口关闭后回到待机
        self.set_state("idle")

    # ── 随机问候（含天气） ──────────────────────────

    def _show_random_greeting(self):
        """双击显示天气信息和出行建议"""
        # 直接查询天气，结果显示在气泡中
        self._query_weather()

    # ── 系统状态 ──────────────────────────────────

    def _show_system_status(self):
        """显示系统状态"""
        self.set_state("status", 10000)
        status_text = SystemStatus.get_status_summary()
        self.show_bubble(status_text, 8000)

    # ── 今日课程 ──────────────────────────────────

    def _show_today_courses(self):
        """
        右键菜单「📅 今日课程」：把当天的课拼成气泡显示。

        课程数据由设置页「📅 课程表」录入，这里只读不写；
        读取失败（数据库里的 JSON 被改坏）时 CourseService 会返回空表，
        因此会走"今天没有课"分支，不会抛异常。
        """
        text = CourseService(self.db).day_text()
        self.set_state("greet", 8000)
        self.show_bubble(text, 10000)

    # ── 设置对话框 ────────────────────────────────

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self.db, self)
        dlg.exec()

    # ── 退出 ──────────────────────────────────────

    def _save_position(self):
        """把当前窗口位置写入数据库"""
        pos = self.pos()
        self.db.set("window_x", str(pos.x()))
        self.db.set("window_y", str(pos.y()))

    def _quit_app(self):
        """保存窗口位置并退出"""
        self._save_position()
        self.bubble.hide_bubble()
        QApplication.quit()

    def closeEvent(self, event):
        """关闭主窗口时一并收起气泡顶层窗口"""
        self.bubble.hide_bubble()
        super().closeEvent(event)

    # ── 气泡定位 ──────────────────────────────────

    def _position_bubble(self):
        """
        将气泡定位在宠物上方（全局屏幕坐标）。

        气泡是独立顶层窗口，因此这里全部使用屏幕绝对坐标；
        若上方空间不足则翻转到宠物下方，左右也做边界收敛。
        """
        screen = QApplication.primaryScreen().availableGeometry()
        bubble_width = self.bubble.width()
        bubble_height = self.bubble.height()
        pet_rect = self.frameGeometry()

        # 水平居中对齐宠物
        bx = pet_rect.center().x() - bubble_width // 2

        # 垂直方向：优先显示在宠物上方，空间不足则改到下方
        by = pet_rect.top() - bubble_height - 10
        if by < screen.top():
            by = pet_rect.bottom() + 10

        # 左右边界收敛
        bx = max(screen.left(), min(bx, screen.right() - bubble_width))

        self.bubble.move(bx, by)

    # ── 公共接口 ──────────────────────────────────

    def show_bubble(self, text: str, duration_ms: int = 5000):
        """显示简单文本气泡"""
        self.bubble.show_text(text, duration_ms)
        self._position_bubble()
