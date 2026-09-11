"""
AI 对话窗口模块
单击宠物时弹出的对话界面
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QFrame, QSizePolicy, QApplication,
)

from db_manager import DBManager
from ai_service import AIService


# ─── 样式常量 ─────────────────────────────────────────────

PRIMARY_COLOR = "#007AFF"
PRIMARY_HOVER = "#0056CC"
BG_COLOR = "#F5F6F7"
CARD_BG = "#FFFFFF"
TEXT_PRIMARY = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
BORDER_COLOR = "#D1D1D6"
RADIUS_SMALL = 6
RADIUS_MEDIUM = 10

# 全局样式表
CHAT_STYLE = f"""
QDialog {{
    background-color: {BG_COLOR};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
}}

QTextEdit {{
    background-color: {CARD_BG};
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS_MEDIUM}px;
    padding: 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    selection-background-color: {PRIMARY_COLOR};
}}

QLineEdit {{
    background-color: {CARD_BG};
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS_SMALL}px;
    padding: 10px 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 40px;
}}

QLineEdit:focus {{
    border-color: {PRIMARY_COLOR};
}}

QPushButton {{
    background-color: {PRIMARY_COLOR};
    color: white;
    border: none;
    border-radius: {RADIUS_SMALL}px;
    font-size: 13px;
    font-weight: 600;
    padding: 10px 20px;
    min-height: 40px;
}}

QPushButton:hover {{
    background-color: {PRIMARY_HOVER};
}}

QPushButton:pressed {{
    background-color: #004099;
}}

QPushButton:disabled {{
    background-color: #B0B0B5;
}}
"""


# ─── AI 回复线程 ──────────────────────────────────────────

class ChatWorker(QThread):
    """后台线程处理 AI 对话，避免阻塞 UI"""
    finished = pyqtSignal(str)

    def __init__(self, ai_service: AIService, message: str):
        super().__init__()
        self.ai_service = ai_service
        self.message = message

    def run(self):
        response = self.ai_service.chat(self.message)
        self.finished.emit(response)


# ─── 对话窗口 ─────────────────────────────────────────────

class ChatDialog(QDialog):
    """
    AI 对话窗口
    单击宠物时弹出，可以与 AI 进行对话
    """

    def __init__(self, db: DBManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.ai_service = AIService(db)
        self._chat_worker = None
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        self.setStyleSheet(CHAT_STYLE)
        self.setWindowTitle("💬 AI 对话")
        self.setMinimumSize(450, 500)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("💬 AI 对话助手")
        title_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 700;
            color: {TEXT_PRIMARY};
        """)
        title_layout.addWidget(title_label)

        # 当前模型标签
        model_text = f"当前模型: {self.ai_service.current_model}"
        if self.ai_service.is_free_model():
            model_text += " (免费)"
        self.model_label = QLabel(model_text)
        self.model_label.setStyleSheet(f"""
            font-size: 12px;
            color: {TEXT_SECONDARY};
            background-color: rgba(0, 122, 255, 0.1);
            padding: 4px 10px;
            border-radius: 10px;
        """)
        title_layout.addWidget(self.model_label)
        title_layout.addStretch()

        main_layout.addLayout(title_layout)

        # 对话历史显示区域
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setPlaceholderText("对话历史将在这里显示...")
        main_layout.addWidget(self.chat_history)

        # 输入区域
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MEDIUM}px;
                padding: 12px;
            }}
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(12)

        # 提示标签
        hint_label = QLabel("💡 输入你的问题，按 Enter 或点击发送按钮")
        hint_label.setStyleSheet(f"""
            font-size: 12px;
            color: {TEXT_SECONDARY};
        """)
        input_layout.addWidget(hint_label)

        # 输入框和发送按钮
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入你的问题...")
        self.input_field.returnPressed.connect(self._send_message)
        input_row.addWidget(self.input_field)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedWidth(80)
        self.btn_send.clicked.connect(self._send_message)
        input_row.addWidget(self.btn_send)

        input_layout.addLayout(input_row)
        main_layout.addWidget(input_frame)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_clear = QPushButton("清空对话")
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 2px solid {BORDER_COLOR};
                padding: 8px 16px;
                min-height: 35px;
            }}
            QPushButton:hover {{
                background-color: #F0F0F0;
            }}
        """)
        self.btn_clear.clicked.connect(self._clear_history)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 2px solid {BORDER_COLOR};
                padding: 8px 16px;
                min-height: 35px;
            }}
            QPushButton:hover {{
                background-color: #F0F0F0;
            }}
        """)
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

        # 添加欢迎消息
        if self.ai_service.is_free_model():
            welcome_msg = "你好！我是你的 AI 助手（免费本地对话模式）。\n\n你可以问我任何问题，我会尽力回答你！\n\n💡 提示：在设置中可以切换到其他 AI 模型获得更智能的回复。"
        else:
            welcome_msg = "你好！我是你的 AI 助手，有什么可以帮你的吗？"
        self._add_message("🤖 AI 助手", welcome_msg, is_user=False)

    def _send_message(self):
        """发送消息"""
        message = self.input_field.text().strip()
        if not message:
            return

        # 检查是否需要 API Key（免费模型不需要）
        if not self.ai_service.is_free_model() and not self.ai_service.get_api_key():
            self._add_message("⚠️ 系统", "请先在设置中配置 API Key，或切换到免费的本地对话模式！", is_user=False)
            return

        # 显示用户消息
        self._add_message("👤 你", message, is_user=True)
        self.input_field.clear()

        # 禁用输入
        self.input_field.setEnabled(False)
        self.btn_send.setEnabled(False)
        self.btn_send.setText("思考中...")

        # 添加等待提示
        self._add_message("🤖 AI 助手", "正在思考中...", is_user=False)

        # 启动 AI 回复线程
        self._chat_worker = ChatWorker(self.ai_service, message)
        self._chat_worker.finished.connect(self._on_ai_response)
        self._chat_worker.start()

    def _on_ai_response(self, response: str):
        """AI 回复完成"""
        # 移除"思考中"的消息
        self._remove_last_message()

        # 显示 AI 回复
        self._add_message("🤖 AI 助手", response, is_user=False)

        # 恢复输入
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setText("发送")
        self.input_field.setFocus()

    def _add_message(self, sender: str, message: str, is_user: bool):
        """添加消息到对话历史"""
        # 设置消息样式
        if is_user:
            align = "right"
            bg_color = "#DCF8C6"
            text_color = TEXT_PRIMARY
        else:
            align = "left"
            bg_color = CARD_BG
            text_color = TEXT_PRIMARY

        # 构建 HTML 消息
        html = f"""
        <div style="text-align: {align}; margin: 8px 0;">
            <div style="display: inline-block; background-color: {bg_color};
                        padding: 10px 14px; border-radius: 12px;
                        max-width: 80%; text-align: left;
                        box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                <div style="font-size: 12px; color: {TEXT_SECONDARY};
                            margin-bottom: 4px; font-weight: 600;">
                    {sender}
                </div>
                <div style="font-size: 13px; color: {text_color};
                            line-height: 1.5; word-wrap: break-word;">
                    {message}
                </div>
            </div>
        </div>
        """

        self.chat_history.append(html)

        # 滚动到底部
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _remove_last_message(self):
        """移除最后一条消息（用于移除"思考中"的提示）"""
        # 获取当前文本
        text = self.chat_history.toHtml()

        # 找到最后一个消息块的起始位置
        last_div_end = text.rfind("</div>")
        if last_div_end == -1:
            return

        # 找到对应的开始位置
        last_div_start = text.rfind("<div", 0, last_div_end)
        if last_div_start == -1:
            return

        # 移除最后一个消息块
        new_text = text[:last_div_start]
        self.chat_history.setHtml(new_text)

    def _clear_history(self):
        """清空对话历史"""
        self.chat_history.clear()
        self._add_message("🤖 AI 助手", "对话已清空，有什么可以帮你的吗？", is_user=False)


# ─── 测试代码 ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    db = DBManager("test_chat.db")
    dialog = ChatDialog(db)
    dialog.show()
    sys.exit(app.exec())
