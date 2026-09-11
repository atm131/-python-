"""
AI 对话窗口模块
单击宠物时弹出的对话界面
"""
from __future__ import annotations

from html import escape as html_escape

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QFrame,
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

    def __init__(self, ai_service: AIService, message: str, handler=None):
        super().__init__()
        self.ai_service = ai_service
        self.message = message
        # handler 用于插件命令等自定义处理逻辑（同样在后台线程执行）
        self.handler = handler

    def run(self):
        if self.handler is not None:
            response = self.handler(self.message)
        else:
            response = self.ai_service.chat(self.message)
        self.finished.emit(response)


# ─── 对话窗口 ─────────────────────────────────────────────

class ChatDialog(QDialog):
    """
    AI 对话窗口
    单击宠物时弹出，可以与 AI 进行对话
    """

    def __init__(self, db: DBManager, parent=None, plugin_manager=None):
        super().__init__(parent)
        self.db = db
        self.ai_service = AIService(db)
        self.plugin_manager = plugin_manager  # 支持 /天气 等插件命令
        self._chat_worker = None
        self._thinking_pos = None  # "思考中"占位消息的文档位置
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
        model_name = self.ai_service.current_model
        model_text = f"当前模型: {model_name}"
        if self.ai_service.is_free_model() and "免费" not in model_name:
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
        hint_label = QLabel("💡 输入问题按 Enter 发送；也支持 /天气 北京 等插件命令")
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

        # 记录位置后插入等待提示，回复到达时按位置回滚
        self._thinking_pos = self.chat_history.document().characterCount() - 1
        self._add_message("🤖 AI 助手", "正在思考中...", is_user=False)

        # 以 "/" 开头优先走插件命令（如 /天气 北京），未匹配则回退到 AI
        handler = None
        if self.plugin_manager is not None and message.startswith("/"):
            handler = self._dispatch_or_chat

        # 启动 AI 回复线程
        self._chat_worker = ChatWorker(self.ai_service, message, handler=handler)
        self._chat_worker.finished.connect(self._on_ai_response)
        self._chat_worker.start()

    def _dispatch_or_chat(self, message: str) -> str:
        """先尝试插件命令，无匹配命令再交给 AI（在后台线程中执行）"""
        result = self.plugin_manager.dispatch_command(message)
        if result is not None:
            return result
        return self.ai_service.chat(message)

    def _on_ai_response(self, response: str):
        """AI 回复完成"""
        # 移除"思考中"的占位消息
        if self._thinking_pos is not None:
            self._remove_last_message(self._thinking_pos)
            self._thinking_pos = None

        # 显示 AI 回复
        self._add_message("🤖 AI 助手", response, is_user=False)

        # 通知事件总线，宠物可以据此切换表情（桌宠收到回复 → 开心）
        if self.plugin_manager is not None:
            self.plugin_manager.bus.emit("chat.reply", {"response": response})

        # 恢复输入
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_send.setText("发送")
        self.input_field.setFocus()

    def _add_message(self, sender: str, message: str, is_user: bool) -> int:
        """
        添加消息到对话历史。

        返回插入前的文档位置，调用方可在需要时回滚到该位置。
        消息内容做 HTML 转义，避免用户输入 <、> 等字符破坏气泡排版。
        """
        # 设置消息样式
        if is_user:
            align = "right"
            bg_color = "#DCF8C6"
            text_color = TEXT_PRIMARY
        else:
            align = "left"
            bg_color = CARD_BG
            text_color = TEXT_PRIMARY

        # 记录插入位置（供回滚使用）
        insert_pos = max(self.chat_history.document().characterCount() - 1, 0)

        safe_sender = html_escape(sender)
        safe_message = html_escape(message).replace("\n", "<br>")

        # 构建 HTML 消息
        html = f"""
        <div style="text-align: {align}; margin: 8px 0;">
            <div style="display: inline-block; background-color: {bg_color};
                        padding: 10px 14px; border-radius: 12px;
                        max-width: 80%; text-align: left;
                        box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                <div style="font-size: 12px; color: {TEXT_SECONDARY};
                            margin-bottom: 4px; font-weight: 600;">
                    {safe_sender}
                </div>
                <div style="font-size: 13px; color: {text_color};
                            line-height: 1.5; word-wrap: break-word;">
                    {safe_message}
                </div>
            </div>
        </div>
        """

        self.chat_history.append(html)

        # 滚动到底部
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        return insert_pos

    def _remove_last_message(self, from_pos: int):
        """
        删除从 from_pos 到文档末尾的内容（用于移除"思考中"的占位消息）。

        直接对 toHtml() 做字符串裁剪不可靠（Qt 会重写 HTML 结构），
        这里用 QTextCursor 按文档位置删除，并清掉可能残留的空段落。
        """
        if from_pos < 0:
            return
        cursor = self.chat_history.textCursor()
        cursor.setPosition(from_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        # removeSelectedText 可能留下一个空段落，一并清理
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        if not cursor.selectedText().strip():
            cursor.removeSelectedText()

    def closeEvent(self, event):
        """关闭前等待后台线程结束，避免线程回调已销毁的窗口"""
        if self._chat_worker and self._chat_worker.isRunning():
            self._chat_worker.wait(3000)
        super().closeEvent(event)

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
