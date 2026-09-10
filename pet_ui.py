"""
桌面宠物 UI 模块
基于 PyQt6 实现透明窗口、鼠标穿透、拖拽交互、动画状态机。
"""
from __future__ import annotations

import math
import sys
import time
from enum import Enum, auto
from typing import Any

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDrag,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from config import AppConfig, PetConfig, UIConfig
from plugin_manager import EventBus


# ─── 宠物状态枚举 ─────────────────────────────────────────

class PetState(Enum):
    """宠物动画状态"""
    IDLE = auto()       # 待机
    THINKING = auto()   # 思考中（AI 回复时）
    BUSY = auto()       # 忙碌（系统高负载）
    TIRED = auto()      # 疲惫（CPU/内存过高）
    HAPPY = auto()      # 开心（低负载/收到夸奖）
    WALKING = auto()    # 巡逻中
    DRAGGING = auto()   # 被拖拽中


# ─── 动画帧生成器 ─────────────────────────────────────────

class PetAnimator:
    """
    根据当前状态生成动画帧（用代码绘制宠物，无需外部图片资源）。
    每个状态有独特的外观表现。
    """

    def __init__(self, config: PetConfig, ui_config: UIConfig):
        self.config = config
        self.ui_config = ui_config
        self._frame_index = 0
        self._state = PetState.IDLE

    @property
    def state(self) -> PetState:
        return self._state

    @state.setter
    def state(self, new_state: PetState):
        if new_state != self._state:
            self._state = new_state
            self._frame_index = 0

    def next_frame(self) -> QPixmap:
        """生成下一帧动画"""
        self._frame_index += 1
        size = self.config.width
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = size // 2, size // 2
        body_r = size * 0.35

        # 根据状态选择颜色和动作
        if self._state == PetState.IDLE:
            self._draw_idle(painter, cx, cy, body_r)
        elif self._state == PetState.THINKING:
            self._draw_thinking(painter, cx, cy, body_r)
        elif self._state == PetState.BUSY:
            self._draw_busy(painter, cx, cy, body_r)
        elif self._state == PetState.TIRED:
            self._draw_tired(painter, cx, cy, body_r)
        elif self._state == PetState.HAPPY:
            self._draw_happy(painter, cx, cy, body_r)
        elif self._state == PetState.WALKING:
            self._draw_walking(painter, cx, cy, body_r)
        elif self._state == PetState.DRAGGING:
            self._draw_dragging(painter, cx, cy, body_r)

        painter.end()
        return pixmap

    def _draw_body(self, p: QPainter, cx: float, cy: float, r: float, color: str):
        """绘制圆形身体"""
        p.setBrush(QBrush(QColor(color)))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_eyes(self, p: QPainter, cx: float, cy: float, r: float,
                   blink: bool = False):
        """绘制眼睛"""
        eye_y = cy - r * 0.15
        eye_r = r * 0.12
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.PenStyle.NoPen)
        if blink:
            # 眯眼
            p.drawEllipse(QPointF(cx - r * 0.3, eye_y), eye_r * 1.5, eye_r * 0.3)
            p.drawEllipse(QPointF(cx + r * 0.3, eye_y), eye_r * 1.5, eye_r * 0.3)
        else:
            p.drawEllipse(QPointF(cx - r * 0.3, eye_y), eye_r, eye_r)
            p.drawEllipse(QPointF(cx + r * 0.3, eye_y), eye_r, eye_r)
            # 瞳孔
            p.setBrush(QBrush(QColor("#1a1a1a")))
            pupil_r = eye_r * 0.5
            p.drawEllipse(QPointF(cx - r * 0.3, eye_y), pupil_r, pupil_r)
            p.drawEllipse(QPointF(cx + r * 0.3, eye_y), pupil_r, pupil_r)

    def _draw_mouth(self, p: QPainter, cx: float, cy: float, r: float,
                    shape: str = "smile"):
        """绘制嘴巴"""
        mouth_y = cy + r * 0.25
        pen = QPen(QColor("#1a1a1a"), 2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        if shape == "smile":
            path.moveTo(cx - r * 0.2, mouth_y)
            path.quadTo(QPointF(cx, mouth_y + r * 0.15), QPointF(cx + r * 0.2, mouth_y))
        elif shape == "open":
            p.setBrush(QBrush(QColor("#1a1a1a")))
            p.drawEllipse(QPointF(cx, mouth_y), r * 0.12, r * 0.1)
        elif shape == "tired":
            path.moveTo(cx - r * 0.15, mouth_y + r * 0.05)
            path.quadTo(QPointF(cx, mouth_y - r * 0.05), QPointF(cx + r * 0.15, mouth_y + r * 0.05))
        p.drawPath(path)

    def _draw_idle(self, p, cx, cy, r):
        # 呼吸动画：轻微缩放
        breathe = math.sin(self._frame_index * 0.3) * 2
        self._draw_body(p, cx, cy, r + breathe, "#4ecdc4")
        blink = (self._frame_index % 12) == 0
        self._draw_eyes(p, cx, cy, r, blink=blink)
        self._draw_mouth(p, cx, cy, r, "smile")

    def _draw_thinking(self, p, cx, cy, r):
        self._draw_body(p, cx, cy, r, "#ffe66d")
        self._draw_eyes(p, cx, cy, r, blink=False)
        # 思考泡泡
        bobble_y = cy - r - 10 - (self._frame_index % 3) * 5
        p.setBrush(QBrush(QColor("#ffe66d")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx + r * 0.5, bobble_y), 6, 6)
        p.drawEllipse(QPointF(cx + r * 0.7, bobble_y - 10), 4, 4)
        self._draw_mouth(p, cx, cy, r, "open")

    def _draw_busy(self, p, cx, cy, r):
        # 忙碌：快速晃动
        shake = math.sin(self._frame_index * 1.5) * 3
        self._draw_body(p, cx + shake, cy, r, "#ff9f43")
        self._draw_eyes(p, cx + shake, cy, r, blink=False)
        self._draw_mouth(p, cx + shake, cy, r, "open")

    def _draw_tired(self, p, cx, cy, r):
        # 疲惫：下垂 + 汗滴
        self._draw_body(p, cx, cy + 3, r, "#ff6b6b")
        # 半闭眼
        self._draw_eyes(p, cx, cy + 3, r, blink=True)
        self._draw_mouth(p, cx, cy + 3, r, "tired")
        # 汗滴
        p.setBrush(QBrush(QColor("#4ecdc4")))
        p.setPen(Qt.PenStyle.NoPen)
        sweat_y = cy - r + 5 + (self._frame_index % 4) * 3
        p.drawEllipse(QPointF(cx + r * 0.6, sweat_y), 3, 5)

    def _draw_happy(self, p, cx, cy, r):
        # 开心：弹跳 + 大笑
        bounce = abs(math.sin(self._frame_index * 0.5)) * 5
        self._draw_body(p, cx, cy - bounce, r, "#00d4aa")
        self._draw_eyes(p, cx, cy - bounce, r, blink=True)
        self._draw_mouth(p, cx, cy - bounce, r, "smile")
        # 爱心
        p.setBrush(QBrush(QColor("#ff6b6b")))
        p.setPen(Qt.PenStyle.NoPen)
        heart_y = cy - r - 15
        p.drawEllipse(QPointF(cx - 3, heart_y), 4, 4)
        p.drawEllipse(QPointF(cx + 3, heart_y), 4, 4)

    def _draw_walking(self, p, cx, cy, r):
        self._draw_body(p, cx, cy, r, "#4ecdc4")
        self._draw_eyes(p, cx, cy, r, blink=False)
        self._draw_mouth(p, cx, cy, r, "smile")
        # 脚步动画
        foot_y = cy + r * 0.8
        offset = math.sin(self._frame_index * 0.8) * 5
        p.setBrush(QBrush(QColor("#2d8a7a")))
        p.drawEllipse(QPointF(cx - r * 0.25, foot_y + offset), 8, 4)
        p.drawEllipse(QPointF(cx + r * 0.25, foot_y - offset), 8, 4)

    def _draw_dragging(self, p, cx, cy, r):
        # 被拖拽：惊吓表情
        self._draw_body(p, cx, cy, r * 1.05, "#4ecdc4")
        # 大眼睛
        eye_y = cy - r * 0.15
        eye_r = r * 0.16
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx - r * 0.3, eye_y), eye_r, eye_r)
        p.drawEllipse(QPointF(cx + r * 0.3, eye_y), eye_r, eye_r)
        p.setBrush(QBrush(QColor("#1a1a1a")))
        p.drawEllipse(QPointF(cx - r * 0.3, eye_y), eye_r * 0.4, eye_r * 0.4)
        p.drawEllipse(QPointF(cx + r * 0.3, eye_y), eye_r * 0.4, eye_r * 0.4)
        self._draw_mouth(p, cx, cy, r, "open")


# ─── 对话气泡组件 ─────────────────────────────────────────

class ChatBubble(QWidget):
    """
    宠物头顶的对话气泡。
    支持自动换行、自动隐藏、渐入渐出。
    """

    def __init__(self, parent: QWidget, config: UIConfig):
        super().__init__(parent)
        self.config = config
        self._text = ""
        self._opacity = 0.0
        self._visible = False
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_step)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(config.bubble_max_width)

    def show_message(self, text: str, duration_ms: int = 5000):
        """显示气泡消息，duration_ms 后自动隐藏"""
        self._text = text
        self._opacity = 1.0
        self._visible = True
        self._duration = duration_ms
        self._fade_timer.start(50)
        self._adjust_size()
        self.update()
        # 自动隐藏定时器
        QTimer.singleShot(duration_ms, self._start_fade_out)

    def _adjust_size(self):
        from PyQt6.QtGui import QFont, QFontMetrics
        font = QFont(self.config.font_family, 10)
        metrics = QFontMetrics(font)
        rect = metrics.boundingRect(
            QRect(0, 0, self.config.bubble_max_width - 20, 1000),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        self.setFixedSize(rect.width() + 20, rect.height() + 16)

    def _start_fade_out(self):
        self._fading_out = True

    def _fade_step(self):
        if hasattr(self, "_fading_out") and self._fading_out:
            self._opacity -= 0.05
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

        # 气泡背景
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.fillPath(path, QColor(30, 30, 30, 220))

        # 文字
        painter.setPen(QColor(self.config.bubble_fg))
        from PyQt6.QtGui import QFont
        painter.setFont(QFont(self.config.font_family, 10))
        painter.drawText(
            self.rect().adjusted(10, 8, -10, -8),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        painter.end()


# ─── 桌面宠物主窗口 ────────────────────────────────────────

class DesktopPet(QWidget):
    """
    桌面宠物主窗口。

    核心特性：
    1. 透明背景 —— Qt.FramelessWindowHint + WA_TranslucentBackground
    2. 鼠标穿透 —— 窗口置顶但空白区域不拦截鼠标事件
    3. 拖拽交互 —— 点击宠物本体可拖拽移动
    4. 巡逻动画 —— 宠物在屏幕边缘自主巡逻
    5. 右键菜单 —— 知识库导入、设置等快捷操作
    6. 状态联动 —— 根据系统负载自动切换动画状态

    发射的事件：
    - "pet.clicked"      — 左键单击宠物
    - "pet.double_clicked" — 左键双击
    - "pet.right_click"  — 右键菜单
    - "pet.drag_start"   — 开始拖拽
    - "pet.drag_end"     — 结束拖拽
    - "pet.patrol_turn"  — 巡逻转向
    """

    def __init__(self, config: AppConfig, bus: EventBus):
        super().__init__()
        self.app_config = config
        self.pet_config = config.pet
        self.ui_config = config.ui
        self.bus = bus

        # 动画器
        self.animator = PetAnimator(self.pet_config, self.ui_config)

        # 巡逻状态
        self._patrol_direction = 1  # 1=右, -1=左
        self._patrolling = True

        # 拖拽状态
        self._dragging = False
        self._drag_offset = QPoint()

        # 初始化窗口
        self._init_window()

        # 对话气泡
        self.bubble = ChatBubble(self, self.ui_config)
        self._position_bubble()

        # 动画定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        self._anim_timer.start(self.pet_config.anim_frame_ms)

        # 巡逻定时器
        self._patrol_timer = QTimer(self)
        self._patrol_timer.timeout.connect(self._patrol_step)
        self._patrol_timer.start(self.pet_config.patrol_interval_ms)

        # 注册事件监听
        self._register_events()

    # ── 窗口初始化 ────────────────────────────────

    def _init_window(self):
        """
        核心：实现透明背景 + 鼠标穿透。

        原理（Windows 平台）：
        1. Qt.FramelessWindowHint    — 无边框
        2. Qt.WindowStaysOnTopHint   — 置顶
        3. Qt.Tool                    — 不在任务栏显示
        4. WA_TranslucentBackground   — 窗口背景透明
        5. setMask()                  — 将非绘制区域设为"洞"，鼠标事件穿透

        关键：通过 QRegion + setMask() 定义可交互区域，
        未被 mask 覆盖的区域鼠标事件会穿透到下层窗口。
        """
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.pet_config.width, self.pet_config.height)

        # 初始位置：屏幕右下角
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.pet_config.width - 100
        y = screen.height() - self.pet_config.height - 100
        self.move(x, y)

    def _update_mask(self):
        """
        更新鼠标穿透区域。
        将宠物身体的圆形区域设为可交互，其余区域穿透。
        """
        from PyQt6.QtGui import QRegion
        cx = self.pet_config.width // 2
        cy = self.pet_config.height // 2
        r = int(self.pet_config.width * 0.4)
        # 创建圆形 mask：圆形区域内可接收鼠标事件
        region = QRegion(cx - r, cy - r, r * 2, r * 2,
                         QRegion.RegionType.Ellipse)
        # 气泡区域也需要可交互
        if self.bubble._visible:
            bubble_region = QRegion(self.bubble.geometry())
            region = region.united(bubble_region)
        self.setMask(region)

    # ── 动画更新 ──────────────────────────────────

    def _update_animation(self):
        """定时刷新动画帧"""
        pixmap = self.animator.next_frame()
        # 如果有 QLabel 用于显示，可在此更新
        self.update()  # 触发 paintEvent
        self._update_mask()

    def paintEvent(self, event):
        """绘制宠物本体"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制当前动画帧
        pixmap = self.animator.next_frame()
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

    # ── 鼠标事件 ──────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.pos()
            self.animator.state = PetState.DRAGGING
            self.bus.emit("pet.drag_start", {"pos": (self.x(), self.y())})
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.animator.state = PetState.IDLE
            self.bus.emit("pet.drag_end", {"pos": (self.x(), self.y())})
            # 拖拽结束视为单击
            self.bus.emit("pet.clicked", {})

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.bus.emit("pet.double_clicked", {})

    # ── 右键菜单 ──────────────────────────────────

    def _show_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2d2d2d; color: #e0e0e0; border: 1px solid #444; }
            QMenu::item:selected { background: #4ecdc4; color: #1a1a1a; }
        """)

        action_chat = menu.addAction("💬 打开对话")
        action_import = menu.addAction("📄 导入知识文件")
        action_commands = menu.addAction("📋 查看命令列表")
        menu.addSeparator()
        action_patrol = menu.addAction("🚶 巡逻" if not self._patrolling else "🛑 停止巡逻")
        action_quit = menu.addAction("❌ 退出")

        action = menu.exec(pos)

        if action == action_chat:
            self.bus.emit("pet.double_clicked", {})
        elif action == action_import:
            self.bus.emit("pet.right_click", {"action": "import"})
        elif action == action_commands:
            self.bus.emit("pet.right_click", {"action": "commands"})
        elif action == action_patrol:
            self._patrolling = not self._patrolling
        elif action == action_quit:
            QApplication.quit()

    # ── 巡逻逻辑 ──────────────────────────────────

    def _patrol_step(self):
        """宠物在屏幕边缘自主巡逻"""
        if not self._patrolling or self._dragging:
            return

        self.animator.state = PetState.WALKING
        speed = self.pet_config.patrol_speed
        dx = int(speed * self._patrol_direction)
        new_x = self.x() + dx

        # 获取屏幕边界
        screen = QApplication.primaryScreen().geometry()
        margin = self.pet_config.screen_margin

        if new_x + self.width() > screen.width() - margin:
            self._patrol_direction = -1
            self.bus.emit("pet.patrol_turn", {"direction": "left"})
        elif new_x < screen.x() + margin:
            self._patrol_direction = 1
            self.bus.emit("pet.patrol_turn", {"direction": "right"})

        self.move(new_x, self.y())

    # ── 气泡定位 ──────────────────────────────────

    def _position_bubble(self):
        """将气泡定位在宠物头顶"""
        bx = (self.width() - self.bubble.width()) // 2
        by = -self.bubble.height() - 5
        self.bubble.move(bx, by)

    # ── 事件总线监听 ──────────────────────────────

    def _register_events(self):
        """注册对系统事件的响应"""
        self.bus.on("monitor.load_change", self._on_load_change)
        self.bus.on("llm.stream_start", lambda e: self._set_state(PetState.THINKING))
        self.bus.on("llm.stream_end", self._on_stream_end)

    def _on_load_change(self, event):
        """系统负载变化时切换宠物状态"""
        level = event.data.get("new_level", "normal")
        state_map = {
            "normal": PetState.HAPPY,
            "warning": PetState.TIRED,
            "critical": PetState.BUSY,
        }
        self._set_state(state_map.get(level, PetState.IDLE))
        if level in ("warning", "critical"):
            self.show_bubble(f"系统负载较高哦！等级: {level}", 3000)

    def _on_stream_end(self, event):
        """AI 回复完成后短暂显示开心状态"""
        self._set_state(PetState.HAPPY)
        QTimer.singleShot(3000, lambda: self._set_state(PetState.IDLE))

    def _set_state(self, state: PetState):
        if self.animator.state != state:
            self.animator.state = state

    # ── 公共接口 ──────────────────────────────────

    def show_bubble(self, text: str, duration_ms: int = 5000):
        """显示对话气泡"""
        self._position_bubble()
        self.bubble.show_message(text, duration_ms)
        self._update_mask()
