"""
设置对话框模块（现代化重写）
提供 API 配置、城市设置等界面。
支持多 AI 模型切换：DeepSeek、OpenAI、豆包、通义千问、Kimi

交互方式：
- 左键单击 → 查询天气
- 左键双击 → 打开设置对话框
- 右键菜单 → 更多选项
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QTabWidget, QWidget,
    QLineEdit, QPushButton, QLabel, QMessageBox, QVBoxLayout,
    QComboBox, QRadioButton, QButtonGroup, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect,
)

from db_manager import DBManager


# ─── AI 模型配置 ─────────────────────────────────────────────

AI_MODELS = {
    "本地对话 (免费)": {
        "key_label": "",
        "default_url": "",
        "placeholder": "",
        "help_url": "",
        "help_text": "免费本地对话，无需 API Key，支持基本问答",
        "is_free": True,
    },
    "DeepSeek": {
        "key_label": "DeepSeek API Key",
        "default_url": "https://api.deepseek.com/v1/chat/completions",
        "placeholder": "输入 DeepSeek API Key（免费注册）",
        "help_url": "platform.deepseek.com",
        "help_text": "免费注册后在 API Keys 页面获取密钥",
        "is_free": False,
    },
    "OpenAI": {
        "key_label": "OpenAI API Key",
        "default_url": "https://api.openai.com/v1/chat/completions",
        "placeholder": "输入 OpenAI API Key",
        "help_url": "platform.openai.com",
        "help_text": "需要绑定支付方式，按使用量计费",
        "is_free": False,
    },
    "豆包 (Doubao)": {
        "key_label": "豆包 API Key",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "placeholder": "输入豆包 API Key",
        "help_url": "console.volcengine.com/ark",
        "help_text": "在火山引擎控制台获取 API Key",
        "is_free": False,
    },
    "通义千问 (Qwen)": {
        "key_label": "通义千问 API Key",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "placeholder": "输入通义千问 API Key",
        "help_url": "dashscope.aliyun.com",
        "help_text": "在阿里云 DashScope 控制台获取 API Key",
        "is_free": False,
    },
    "Kimi": {
        "key_label": "Kimi API Key",
        "default_url": "https://api.moonshot.cn/v1/chat/completions",
        "placeholder": "输入 Kimi API Key",
        "help_url": "platform.moonshot.cn",
        "help_text": "在 Moonshot 平台获取 API Key",
        "is_free": False,
    },
}


# ─── 样式常量 ─────────────────────────────────────────────────

# 主色调
PRIMARY_COLOR = "#007AFF"
PRIMARY_HOVER = "#0056CC"
PRIMARY_PRESSED = "#004099"

# 背景色
BG_COLOR = "#F5F6F7"
CARD_BG = "#FFFFFF"
INPUT_BG = "#FFFFFF"

# 文字色
TEXT_PRIMARY = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
TEXT_PLACEHOLDER = "#AEAEB2"

# 边框色
BORDER_COLOR = "#D1D1D6"
BORDER_FOCUS = PRIMARY_COLOR

# 成功/错误色
SUCCESS_COLOR = "#34C759"
ERROR_COLOR = "#FF3B30"

# 圆角
RADIUS_SMALL = 6
RADIUS_MEDIUM = 10
RADIUS_LARGE = 14

# 全局样式表
GLOBAL_STYLE = f"""
QDialog {{
    background-color: {BG_COLOR};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
}}

QTabWidget::pane {{
    border: none;
    background-color: {CARD_BG};
    border-radius: {RADIUS_MEDIUM}px;
    margin-top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 12px 24px;
    margin-right: 4px;
    font-size: 14px;
    font-weight: 500;
    border-bottom: 3px solid transparent;
    border-top-left-radius: {RADIUS_SMALL}px;
    border-top-right-radius: {RADIUS_SMALL}px;
}}

QTabBar::tab:selected {{
    color: {PRIMARY_COLOR};
    font-weight: 600;
    border-bottom: 3px solid {PRIMARY_COLOR};
    background-color: {CARD_BG};
}}

QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
    background-color: rgba(0, 122, 255, 0.05);
}}

QLabel {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}

QLineEdit {{
    background-color: {INPUT_BG};
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS_SMALL}px;
    padding: 8px 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 35px;
    selection-background-color: {PRIMARY_COLOR};
}}

QLineEdit:focus {{
    border-color: {BORDER_FOCUS};
    background-color: #FFFFFF;
}}

QLineEdit:hover:!focus {{
    border-color: #B0B0B5;
}}

QComboBox {{
    background-color: {INPUT_BG};
    border: 2px solid {BORDER_COLOR};
    border-radius: {RADIUS_SMALL}px;
    padding: 8px 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 35px;
}}

QComboBox:focus {{
    border-color: {BORDER_FOCUS};
}}

QComboBox:hover:!focus {{
    border-color: #B0B0B5;
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER_COLOR};
    border-radius: {RADIUS_SMALL}px;
    padding: 4px;
    selection-background-color: rgba(0, 122, 255, 0.1);
    selection-color: {PRIMARY_COLOR};
}}

QRadioButton {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid {BORDER_COLOR};
    background-color: {INPUT_BG};
}}

QRadioButton::indicator:checked {{
    border-color: {PRIMARY_COLOR};
    background-color: {PRIMARY_COLOR};
}}

QRadioButton::indicator:hover {{
    border-color: {PRIMARY_COLOR};
}}
"""


# ─── 自定义组件 ─────────────────────────────────────────────

class IconButton(QPushButton):
    """带图标的按钮（用于眼睛图标切换密码可见性）"""

    def __init__(self, text: str = "👁", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: {RADIUS_SMALL}px;
                font-size: 16px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.05);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.1);
            }}
        """)


class HelpFrame(QFrame):
    """帮助提示框"""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #E8F4FD;
                border: 1px solid #B8D4E8;
                border-radius: {RADIUS_SMALL}px;
                padding: 12px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px; border: none;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon_label)

        text_label = QLabel(text)
        text_label.setStyleSheet(f"""
            color: #2C5282;
            font-size: 12px;
            line-height: 1.5;
            border: none;
        """)
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)


class PrimaryButton(QPushButton):
    """主色调按钮（保存）"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {PRIMARY_COLOR};
                color: white;
                border: none;
                border-radius: {RADIUS_SMALL}px;
                font-size: 14px;
                font-weight: 600;
                padding: 10px 24px;
            }}
            QPushButton:hover {{
                background-color: {PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {PRIMARY_PRESSED};
            }}
        """)


class SecondaryButton(QPushButton):
    """次要按钮（取消）"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_SMALL}px;
                font-size: 14px;
                font-weight: 500;
                padding: 10px 24px;
            }}
            QPushButton:hover {{
                background-color: #F0F0F0;
                border-color: #B0B0B5;
            }}
            QPushButton:pressed {{
                background-color: #E5E5EA;
            }}
        """)


# ─── 设置对话框 ─────────────────────────────────────────────

class SettingsDialog(QDialog):
    """
    设置对话框，包含多个标签页：
    1. 城市设置 — 手动/自动定位
    2. API 配置 — 多 AI 模型切换
    """

    def __init__(self, db: DBManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("⚙️ 设置")
        self.setMinimumSize(520, 480)
        self._password_visible = False
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """初始化界面"""
        self.setStyleSheet(GLOBAL_STYLE)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 标题
        title_label = QLabel("设置")
        title_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            margin-bottom: 8px;
        """)
        main_layout.addWidget(title_label)

        # 标签页
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_city_tab(), "📍 城市设置")
        self.tabs.addTab(self._create_api_tab(), "🔑 API 配置")
        main_layout.addWidget(self.tabs)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_save = PrimaryButton("💾 保存设置")
        self.btn_save.clicked.connect(self._save)

        self.btn_cancel = SecondaryButton("取消")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        main_layout.addLayout(btn_layout)

    # ── 城市设置标签页 ──────────────────────────────

    def _create_city_tab(self) -> QWidget:
        """创建城市设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 当前模式
        mode_frame = QFrame()
        mode_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MEDIUM}px;
                padding: 16px;
            }}
        """)
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.setSpacing(12)

        mode_title = QLabel("定位模式")
        mode_title.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        """)
        mode_layout.addWidget(mode_title)

        # 单选按钮组
        self.mode_group = QButtonGroup(self)
        self.radio_auto = QRadioButton("自动定位（通过 IP 地址）")
        self.radio_manual = QRadioButton("手动设置城市")
        self.mode_group.addButton(self.radio_auto)
        self.mode_group.addButton(self.radio_manual)

        current_city = self.db.get("city", "")
        if current_city:
            self.radio_manual.setChecked(True)
        else:
            self.radio_auto.setChecked(True)

        # 单选按钮样式调整
        radio_style = f"""
            QRadioButton {{
                padding: 8px 0;
                font-size: 13px;
            }}
        """
        self.radio_auto.setStyleSheet(radio_style)
        self.radio_manual.setStyleSheet(radio_style)

        mode_layout.addWidget(self.radio_auto)
        mode_layout.addWidget(self.radio_manual)
        layout.addWidget(mode_frame)

        # 手动输入城市
        city_frame = QFrame()
        city_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MEDIUM}px;
                padding: 16px;
            }}
        """)
        city_layout = QVBoxLayout(city_frame)
        city_layout.setSpacing(12)

        city_label = QLabel("城市名称")
        city_label.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        """)
        city_layout.addWidget(city_label)

        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("例如：Shanghai、北京、Guangzhou")
        city_layout.addWidget(self.city_input)

        # 帮助提示
        help_text = (
            "💡 留空 = 自动定位（通过 IP 地址）\n"
            "填写 = 手动指定城市（支持中英文）"
        )
        help_frame = HelpFrame("ℹ️", help_text)
        city_layout.addWidget(help_frame)

        layout.addWidget(city_frame)
        layout.addStretch()

        # 连接信号
        self.radio_auto.toggled.connect(self._on_mode_changed)
        self._on_mode_changed()

        return tab

    def _on_mode_changed(self):
        """模式切换时更新输入框状态"""
        is_manual = self.radio_manual.isChecked()
        self.city_input.setEnabled(is_manual)
        if not is_manual:
            self.city_input.clear()

    # ── API 配置标签页 ──────────────────────────────

    def _create_api_tab(self) -> QWidget:
        """创建 API 配置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # AI 模型选择器
        model_frame = QFrame()
        model_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MEDIUM}px;
                padding: 16px;
            }}
        """)
        model_layout = QVBoxLayout(model_frame)
        model_layout.setSpacing(12)

        model_label = QLabel("选择 AI 模型")
        model_label.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        """)
        model_layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems(AI_MODELS.keys())
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_layout.addWidget(self.model_combo)

        layout.addWidget(model_frame)

        # API Key 配置
        api_frame = QFrame()
        api_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MEDIUM}px;
                padding: 16px;
            }}
        """)
        api_layout = QVBoxLayout(api_frame)
        api_layout.setSpacing(16)

        # API Key
        key_label_text = QLabel("API Key")
        key_label_text.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        """)
        api_layout.addWidget(key_label_text)

        # API Key 输入框 + 眼睛按钮
        key_input_layout = QHBoxLayout()
        key_input_layout.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_input_layout.addWidget(self.api_key_input)

        self.btn_toggle_password = IconButton("👁")
        self.btn_toggle_password.setToolTip("显示/隐藏密码")
        self.btn_toggle_password.clicked.connect(self._toggle_password_visibility)
        key_input_layout.addWidget(self.btn_toggle_password)

        api_layout.addLayout(key_input_layout)

        # API URL
        url_label = QLabel("API URL")
        url_label.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
            margin-top: 8px;
        """)
        api_layout.addWidget(url_label)

        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("API 端点地址")
        api_layout.addWidget(self.api_url_input)

        layout.addWidget(api_frame)

        # 帮助提示
        self.help_frame = HelpFrame("💡", "")
        layout.addWidget(self.help_frame)

        layout.addStretch()

        # 初始化显示
        self._on_model_changed(self.model_combo.currentText())

        return tab

    def _on_model_changed(self, model_name: str):
        """AI 模型切换时更新界面"""
        if model_name not in AI_MODELS:
            return

        config = AI_MODELS[model_name]
        is_free = config.get("is_free", False)

        # 更新占位符
        self.api_key_input.setPlaceholderText(config["placeholder"])
        self.api_url_input.setPlaceholderText(config["default_url"])

        # 更新帮助文本
        help_text = (
            f"📌 注册地址：{config['help_url']}\n"
            f"{config['help_text']}"
        )
        # 更新帮助框内容
        for child in self.help_frame.findChildren(QLabel):
            if child.text() and not child.text().startswith("📌"):
                child.setText(help_text)
                break

        # 免费模型禁用输入框
        self.api_key_input.setEnabled(not is_free)
        self.api_url_input.setEnabled(not is_free)
        self.btn_toggle_password.setEnabled(not is_free)

        if is_free:
            self.api_key_input.clear()
            self.api_url_input.clear()
        else:
            # 加载对应模型的保存值
            model_key = model_name.split(" ")[0].lower()  # 提取模型名作为 key 前缀
            saved_key = self.db.get(f"{model_key}_api_key", "")
            saved_url = self.db.get(f"{model_key}_api_url", config["default_url"])

            self.api_key_input.setText(saved_key)
            self.api_url_input.setText(saved_url)

    def _toggle_password_visibility(self):
        """切换密码可见性"""
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_password.setText("🙈")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_password.setText("👁")

    # ── 加载设置 ────────────────────────────────────

    def _load_settings(self):
        """从数据库加载设置"""
        # 城市设置
        current_city = self.db.get("city", "")
        self.city_input.setText(current_city)

        # API 设置 - 加载当前选中模型的配置
        current_model = self.model_combo.currentText()
        self._on_model_changed(current_model)

    # ── 保存 ────────────────────────────────────────

    def _save(self):
        """保存设置到数据库"""
        # 保存城市设置
        if self.radio_manual.isChecked():
            city = self.city_input.text().strip()
            self.db.set("city", city)
        else:
            self.db.set("city", "")

        # 保存 API 设置
        current_model = self.model_combo.currentText()
        model_key = current_model.split(" ")[0].lower()

        api_key = self.api_key_input.text().strip()
        api_url = self.api_url_input.text().strip()

        self.db.set(f"{model_key}_api_key", api_key)
        if api_url:
            self.db.set(f"{model_key}_api_url", api_url)

        # 保存当前选中的模型
        self.db.set("current_ai_model", current_model)

        QMessageBox.information(
            self,
            "保存成功",
            "设置已保存成功！\n部分设置可能需要重启应用后生效。",
        )
        self.accept()
