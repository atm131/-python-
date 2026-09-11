"""
桌面宠物 UI 模块
基于 PyQt6 实现透明无边框窗口、图片宠物、拖拽移动、天气气泡。

交互方式：
- 左键拖拽：移动宠物位置
- 左键单击：查询天气 + 显示地址
- 左键双击：打开设置对话框（API 配置、城市设置）
- 右键单击：弹出菜单（退出、设置、关于）
"""
from __future__ import annotations

import os
from PyQt6.QtCore import QPoint, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget

from db_manager import DBManager
from settings_dialog import SettingsDialog
from chat_dialog import ChatDialog
from weather_service import WeatherService
from system_status import SystemStatus


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
    """

    def __init__(self, parent: QWidget, ui_config):
        super().__init__(parent)
        self.ui_config = ui_config
        self._text = ""
        self._opacity = 0.0
        self._visible = False
        self._fading_out = False
        self._fade_out_timer = None  # 淡出定时器

        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_step)

        # 鼠标穿透：气泡不拦截点击
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(self.ui_config.bubble_max_width)

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
        self._show_text(text, duration_ms)

    def _show_text(self, text: str, duration_ms: int):
        """显示文本气泡"""
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

        # 创建新的淡出定时器
        self._fade_out_timer = QTimer()
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
        self.update()

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
    - 左键拖拽 → 移动
    - 左键单击 → 查询天气 + 地址
    - 左键双击 → 打开设置对话框
    - 右键菜单 → 退出 / 设置 / 关于
    """

    def __init__(self, db: DBManager, weather_service: WeatherService, ui_config):
        super().__init__()
        self.db = db
        self.weather_service = weather_service
        self.ui_config = ui_config
        self._weather_worker: WeatherWorker | None = None

        # 拖拽状态
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_threshold = 5
        self._mouse_press_pos = QPoint()

        # 双击检测
        self._last_click_time = 0

        # 加载宠物图片
        self._pet_pixmap = self._load_pet_image()

        # 初始化窗口
        self._init_window()

        # 天气气泡
        self.bubble = WeatherBubble(self, ui_config)
        self._position_bubble()

    # ── 图片加载 ──────────────────────────────────

    def _load_pet_image(self) -> QPixmap:
        """加载宠物图片，按配置尺寸缩放"""
        img_path = self.db.get("pet_image", r"E:\毕业设计\shuchaiku\nv.png")
        if not os.path.isabs(img_path):
            img_path = os.path.join(os.path.dirname(__file__), img_path)

        width = int(self.db.get("pet_width", "200"))
        height = int(self.db.get("pet_height", "200"))

        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            print(f"[Pet] ⚠️ 图片加载失败: {img_path}，使用默认占位图")
            pixmap = QPixmap(width, height)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            from PyQt6.QtGui import QBrush, QPen
            painter.setBrush(QBrush(QColor("#4ecdc4")))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(10, 10, width - 20, height - 20)
            painter.end()
        else:
            pixmap = pixmap.scaled(
                width, height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pixmap

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
        x = (self.width() - self._pet_pixmap.width()) // 2
        y = (self.height() - self._pet_pixmap.height()) // 2
        painter.drawPixmap(x, y, self._pet_pixmap)
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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragging:
                self._handle_click()
            self._dragging = False

    def _handle_click(self):
        """处理左键点击：单击 vs 双击"""
        import time
        current_time = time.time()

        # 检查是否是双击（400ms 内的第二次点击）
        if hasattr(self, '_last_click_time') and self._last_click_time > 0:
            time_diff = current_time - self._last_click_time
            if time_diff < 0.4:  # 400ms 内两次点击视为双击
                # 取消待执行的单击定时器
                if hasattr(self, '_single_click_timer') and self._single_click_timer.isActive():
                    self._single_click_timer.stop()
                self._last_click_time = 0
                self._on_double_click()
                return

        # 记录本次点击时间
        self._last_click_time = current_time

        # 创建单击定时器，等待可能的第二次点击
        if hasattr(self, '_single_click_timer') and self._single_click_timer.isActive():
            self._single_click_timer.stop()

        self._single_click_timer = QTimer()
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._execute_single_click)
        self._single_click_timer.start(400)  # 400ms 后执行单击

    def _execute_single_click(self):
        """执行单击操作（400ms 内没有第二次点击）"""
        self._last_click_time = 0
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

        menu.exec(pos)

    # ── 天气查询 ──────────────────────────────────

    def _query_weather(self):
        """在后台线程中查询天气"""
        if self._weather_worker and self._weather_worker.isRunning():
            return

        # 断开旧连接
        if self._weather_worker:
            try:
                self._weather_worker.finished.disconnect(self._on_weather_result)
            except:
                pass

        self.show_bubble("正在查询天气...", 3000)

        self._weather_worker = WeatherWorker(self.weather_service)
        self._weather_worker.finished.connect(self._on_weather_result)
        self._weather_worker.start()

    def _on_weather_result(self, data: dict):
        """天气查询完成回调"""
        if data.get("error"):
            self.show_bubble(f"天气查询失败: {data['error']}", 5000)
        else:
            # 显示天气信息气泡
            self.bubble.show_weather(data, duration_ms=15000)
            self._position_bubble()
            # 确保气泡可见
            self.bubble.show()
            self.bubble.raise_()

    # ── 对话窗口 ──────────────────────────────────

    def _open_chat(self):
        """打开对话窗口"""
        dlg = ChatDialog(self.db, self)
        dlg.exec()

    # ── 随机问候（含天气） ──────────────────────────

    def _show_random_greeting(self):
        """双击显示天气信息和出行建议"""
        # 直接查询天气，结果显示在气泡中
        self._query_weather()

    # ── 系统状态 ──────────────────────────────────

    def _show_system_status(self):
        """显示系统状态"""
        status_text = SystemStatus.get_status_summary()
        self.show_bubble(status_text, 8000)

    # ── 设置对话框 ────────────────────────────────

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self.db, self)
        dlg.exec()

    # ── 退出 ──────────────────────────────────────

    def _quit_app(self):
        """保存窗口位置并退出"""
        pos = self.pos()
        self.db.set("window_x", str(pos.x()))
        self.db.set("window_y", str(pos.y()))
        QApplication.quit()

    # ── 气泡定位 ──────────────────────────────────

    def _position_bubble(self):
        """将气泡定位在宠物上方（本地坐标系）"""
        bubble_width = self.bubble.width()
        bubble_height = self.bubble.height()
        pet_width = self.width()
        pet_height = self.height()

        # 水平居中对齐宠物
        bx = (pet_width - bubble_width) // 2

        # 垂直方向：在宠物上方
        by = -bubble_height - 10

        # 边界检查（全部使用屏幕全局坐标）
        screen = QApplication.primaryScreen().geometry()
        pet_x = self.x()
        pet_y = self.y()

        # 气泡屏幕坐标
        bubble_screen_x = pet_x + bx
        bubble_screen_y = pet_y + by

        # 如果气泡超出屏幕上方，改为显示在宠物下方
        if bubble_screen_y < 0:
            by = pet_height + 10

        # 如果气泡超出屏幕右侧，向左调整
        if bubble_screen_x + bubble_width > screen.width():
            bx = pet_width - bubble_width - 10

        # 如果气泡超出屏幕左侧，向右调整
        if bubble_screen_x < 0:
            bx = 10

        self.bubble.move(bx, by)

    # ── 公共接口 ──────────────────────────────────

    def show_bubble(self, text: str, duration_ms: int = 5000):
        """显示简单文本气泡"""
        self.bubble._show_text(text, duration_ms)
        self._position_bubble()
        self.bubble.show()
        self.bubble.raise_()
