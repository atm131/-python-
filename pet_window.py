"""
桌面宠物 UI 模块
基于 PyQt6 实现透明无边框窗口、图片宠物、拖拽移动、天气气泡。
"""
from __future__ import annotations

import os
from PyQt6.QtCore import QPoint, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from config import AppConfig
from weather_service import WeatherService


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

    def __init__(self, parent: QWidget, config: AppConfig):
        super().__init__(parent)
        self.ui_config = config.ui
        self._text = ""
        self._opacity = 0.0
        self._visible = False

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
        self._text = text
        self._opacity = 1.0
        self._visible = True
        self._fading_out = False
        self._adjust_size()
        self._fade_timer.start(50)
        self.update()
        # 定时开始淡出
        QTimer.singleShot(duration_ms, self._start_fade_out)

    def _adjust_size(self):
        """根据文字内容自动调整气泡尺寸"""
        from PyQt6.QtGui import QFontMetrics
        font = QFont(self.ui_config.font_family, 10)
        metrics = QFontMetrics(font)
        from PyQt6.QtCore import QRect
        rect = metrics.boundingRect(
            QRect(0, 0, self.ui_config.bubble_max_width - 24, 1000),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        self.setFixedSize(rect.width() + 24, rect.height() + 20)

    def _start_fade_out(self):
        self._fading_out = True

    def _fade_step(self):
        if self._fading_out:
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

        # 半透明圆角背景
        path = QPainterPath()
        path.addRoundedRect(2, 2, self.width() - 4, self.height() - 4,
                            self.ui_config.bubble_radius, self.ui_config.bubble_radius)
        painter.fillPath(path, QColor(self.ui_config.bubble_bg))

        # 文字
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

    核心特性：
    1. 透明背景 + 无边框 + 置顶
    2. 使用自定义图片作为宠物形象
    3. 鼠标左键拖拽移动，松开后固定在当前位置
    4. 左键单击触发天气查询
    5. 天气结果通过半透明气泡显示
    """

    def __init__(self, config: AppConfig, weather_service: WeatherService):
        super().__init__()
        self.config = config
        self.weather_service = weather_service
        self._weather_worker: WeatherWorker | None = None

        # 拖拽状态
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_threshold = 5  # 拖拽阈值，区分单击和拖拽
        self._mouse_press_pos = QPoint()

        # 加载宠物图片
        self._pet_pixmap = self._load_pet_image()

        # 初始化窗口
        self._init_window()

        # 天气气泡
        self.bubble = WeatherBubble(self, config)
        self._position_bubble()

    # ── 图片加载 ──────────────────────────────────

    def _load_pet_image(self) -> QPixmap:
        """加载宠物图片，按配置尺寸缩放"""
        img_path = self.config.pet.image_path
        if not os.path.isabs(img_path):
            img_path = os.path.join(os.path.dirname(__file__), img_path)

        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            # 图片加载失败时绘制一个占位圆
            print(f"[Pet] ⚠️ 图片加载失败: {img_path}，使用默认占位图")
            pixmap = QPixmap(self.config.pet.width, self.config.pet.height)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            from PyQt6.QtGui import QBrush, QPen
            painter.setBrush(QBrush(QColor("#4ecdc4")))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(10, 10,
                                self.config.pet.width - 20,
                                self.config.pet.height - 20)
            painter.end()
        else:
            # 缩放到目标尺寸，保持比例
            pixmap = pixmap.scaled(
                self.config.pet.width,
                self.config.pet.height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pixmap

    # ── 窗口初始化 ────────────────────────────────

    def _init_window(self):
        """
        设置窗口属性：
        - FramelessWindowHint: 无边框
        - WindowStaysOnTopHint: 置顶
        - Tool: 不在任务栏显示
        - WA_TranslucentBackground: 背景透明
        """
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.config.pet.width, self.config.pet.height)

        # 初始位置：屏幕右下角
        screen = QApplication.primaryScreen().geometry()
        default_x = screen.width() - self.config.pet.width - 100
        default_y = screen.height() - self.config.pet.height - 100
        x = self.config.window.get("init_x") or default_x
        y = self.config.window.get("init_y") or default_y
        self.move(x, y)

    # ── 绘制 ──────────────────────────────────────

    def paintEvent(self, event):
        """绘制宠物图片"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 居中绘制图片
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

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._mouse_press_pos
            # 超过阈值才开始拖拽
            if not self._dragging and (abs(delta.x()) > self._drag_threshold
                                        or abs(delta.y()) > self._drag_threshold):
                self._dragging = True
            if self._dragging:
                new_pos = current_pos - self._drag_start_pos
                self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragging:
                # 未发生拖拽 → 视为单击 → 查询天气
                self._on_clicked()
            self._dragging = False

    def _on_clicked(self):
        """左键单击：查询天气"""
        self._query_weather()

    # ── 天气查询 ──────────────────────────────────

    def _query_weather(self):
        """在后台线程中查询天气，结果通过气泡显示"""
        if self._weather_worker and self._weather_worker.isRunning():
            return  # 避免重复查询

        # 先显示"查询中"提示
        self.show_bubble("正在查询天气...", 2000)

        self._weather_worker = WeatherWorker(self.weather_service)
        self._weather_worker.finished.connect(self._on_weather_result)
        self._weather_worker.start()

    def _on_weather_result(self, data: dict):
        """天气查询完成回调"""
        self.bubble.show_weather(data, duration_ms=10000)
        self._position_bubble()

    # ── 气泡定位 ──────────────────────────────────

    def _position_bubble(self):
        """将气泡定位在宠物左侧"""
        bubble_width = self.bubble.width()
        # 气泡在宠物左侧，留 10px 间距
        bx = -bubble_width - 10
        # 垂直居中
        by = (self.height() - self.bubble.height()) // 2
        self.bubble.move(bx, by)

    # ── 公共接口 ──────────────────────────────────

    def show_bubble(self, text: str, duration_ms: int = 5000):
        """显示简单文本气泡"""
        self.bubble._show_text(text, duration_ms)
        self._position_bubble()
