"""
设置对话框模块（现代化重写）
提供 API 配置、城市设置、课程表等界面。
支持多 AI 模型切换：DeepSeek、OpenAI、豆包、通义千问、Kimi

调用方式：
    由主窗口 PetWindow 的右键菜单「⚙️ 设置」打开：SettingsDialog(db).exec()
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QHBoxLayout,
    QHeaderView, QTabWidget, QTableWidget, QTableWidgetItem, QWidget,
    QLineEdit, QPushButton, QLabel, QMessageBox, QVBoxLayout,
    QComboBox, QRadioButton, QButtonGroup, QFrame,
)

from course_service import CourseService
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


# ─── 课程表列定义 ─────────────────────────────────────────────

# 列顺序即保存时的字段顺序，改列名时记得同步 CourseService 的字段约定
COURSE_COLUMNS = ["课程名", "星期", "开始", "结束", "教室", "提前(分钟)", "启用"]
COL_NAME, COL_WEEKDAY, COL_START, COL_END, COL_ROOM, COL_REMIND, COL_ENABLED = range(7)

# 星期用下拉框选择，避免用户填错数字（索引 +1 即 ISO 星期）
WEEKDAY_ITEMS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


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

# 卡片容器样式：城市设置 / API 配置 / 课程表三个页签共用同一套外观
CARD_FRAME_STYLE = f"""
    QFrame {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER_COLOR};
        border-radius: {RADIUS_MEDIUM}px;
        padding: 16px;
    }}
"""

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

QCheckBox {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    spacing: 8px;
}}

QTableWidget {{
    background-color: {CARD_BG};
    alternate-background-color: {BG_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: {RADIUS_SMALL}px;
    gridline-color: #EDEDF0;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

QTableWidget::item {{
    padding: 4px 6px;
}}

QTableWidget::item:selected {{
    background-color: rgba(0, 122, 255, 0.12);
    color: {TEXT_PRIMARY};
}}

QHeaderView::section {{
    background-color: {BG_COLOR};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER_COLOR};
    padding: 8px 6px;
    font-size: 12px;
    font-weight: 600;
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
        self.text_label = text_label  # 供外部直接更新文案


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
    3. 课程表   — 录入课程，交给 CourseReminder 定时提醒
    """

    def __init__(self, db: DBManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.course_service = CourseService(db)
        self.setWindowTitle("⚙️ 设置")
        # 课程表页签需要放下一张 8 行左右的表格，但窗口不能超出屏幕（小屏笔记本会顶到屏幕外）
        self.setMinimumSize(*self._preferred_size())
        self._password_visible = False
        self._init_ui()
        self._load_settings()

    @staticmethod
    def _preferred_size() -> tuple[int, int]:
        """按屏幕大小收敛窗口最小尺寸：够放课程表，又不超出屏幕"""
        width, height = 580, 660
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, max(420, available.width() - 100))
            height = min(height, max(420, available.height() - 80))
        return width, height

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
        self.tabs.addTab(self._create_course_tab(), "📅 课程表")
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
        mode_frame.setStyleSheet(CARD_FRAME_STYLE)
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
        city_frame.setStyleSheet(CARD_FRAME_STYLE)
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
        model_frame.setStyleSheet(CARD_FRAME_STYLE)
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
        api_frame.setStyleSheet(CARD_FRAME_STYLE)
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
        if is_free or not config["help_url"]:
            self.help_frame.text_label.setText(f"💡 {config['help_text']}")
        else:
            self.help_frame.text_label.setText(
                f"📌 注册地址：{config['help_url']}\n{config['help_text']}"
            )

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

    # ── 课程表标签页 ────────────────────────────────

    @staticmethod
    def make_default_course() -> dict:
        """新增行的默认课程（值都能通过 CourseService 校验）"""
        return {
            "name": "新课程",
            "weekday": 1,
            "start": "08:00",
            "end": "09:40",
            "room": "",
            "remind_before": 10,
            "enabled": True,
        }

    def _create_course_tab(self) -> QWidget:
        """创建课程表标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        help_frame = HelpFrame(
            "📅",
            "在这里录入每周的课程，程序每分钟检查一次：在「提前(分钟)」设定的时间点，\n"
            "宠物会举手并弹出气泡提醒你上课。\n"
            "星期用下拉框选择；时间写成 HH:MM（如 08:00），保存时会自动补零；\n"
            "关掉「启用课程提醒」后不再提醒，但下面的课程数据会保留。",
        )
        layout.addWidget(help_frame)

        # 总开关：对应 course_reminder_enabled
        self.course_enabled_check = QCheckBox("启用课程提醒")
        self.course_enabled_check.setToolTip("关闭后所有课程都不再提醒（数据保留）")
        layout.addWidget(self.course_enabled_check)

        # 表格卡片
        card = QFrame()
        card.setStyleSheet(CARD_FRAME_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(10)

        self.course_table = QTableWidget(0, len(COURSE_COLUMNS))
        self.course_table.setHorizontalHeaderLabels(COURSE_COLUMNS)
        self.course_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.course_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.course_table.setAlternatingRowColors(True)
        # 表格内嵌的下拉框沿用全局样式，但把高度压小，避免每行被撑到 40px 以上
        self.course_table.setStyleSheet(
            "QComboBox { min-height: 22px; padding: 2px 6px; border-width: 1px; }"
        )
        self.course_table.verticalHeader().setDefaultSectionSize(34)
        self.course_table.verticalHeader().setVisible(False)
        # 至少显示 8 行，超出滚动；小屏笔记本上降低高度，优先保证整窗不超出屏幕
        table_height = 300
        screen = QApplication.primaryScreen()
        if screen is not None and screen.availableGeometry().height() < 900:
            table_height = 210
        self.course_table.setMinimumHeight(table_height)

        header = self.course_table.horizontalHeader()
        for col in range(len(COURSE_COLUMNS)):
            mode = (QHeaderView.ResizeMode.Stretch
                    if col in (COL_NAME, COL_ROOM)
                    else QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(col, mode)
        card_layout.addWidget(self.course_table)
        layout.addWidget(card, 1)

        # 增删按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.btn_add_course = SecondaryButton("➕ 添加课程")
        self.btn_add_course.clicked.connect(lambda: self.add_course_row())
        self.btn_del_course = SecondaryButton("➖ 删除选中")
        self.btn_del_course.clicked.connect(self.remove_selected_courses)
        btn_layout.addWidget(self.btn_add_course)
        btn_layout.addWidget(self.btn_del_course)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def add_course_row(self, course: dict | None = None) -> int:
        """
        在表格末尾追加一行课程，返回行号。

        缺省字段用 make_default_course() 补齐，因此传入半截数据也不会出现空单元格；
        测试也直接调用它来构造数据，保证"测试路径"和"用户点按钮"完全一致。
        """
        data = dict(self.make_default_course())
        if course:
            for key in data:
                value = course.get(key)
                if value is not None and value != "":
                    data[key] = value

        row = self.course_table.rowCount()
        self.course_table.insertRow(row)

        self._set_text_cell(row, COL_NAME, data["name"])
        self.course_table.setCellWidget(row, COL_WEEKDAY, self._make_weekday_combo(data["weekday"]))
        self._set_text_cell(row, COL_START, data["start"], "格式 HH:MM，例如 08:00")
        self._set_text_cell(row, COL_END, data["end"], "格式 HH:MM，例如 09:40")
        self._set_text_cell(row, COL_ROOM, data["room"], "留空表示不显示教室")
        self._set_text_cell(row, COL_REMIND, data["remind_before"], "提前多少分钟提醒（0~120）")
        self.course_table.setCellWidget(row, COL_ENABLED, self._make_enabled_widget(data["enabled"]))
        return row

    def remove_selected_courses(self) -> None:
        """删除所有选中行（从后往前删，避免删一行后行号错位）"""
        rows = sorted({index.row() for index in self.course_table.selectedIndexes()},
                      reverse=True)
        for row in rows:
            self.course_table.removeRow(row)

    def _set_text_cell(self, row: int, col: int, value, tooltip: str = "") -> None:
        """写入文本单元格（统一带提示，时间列提示格式）"""
        item = QTableWidgetItem("" if value is None else str(value))
        if tooltip:
            item.setToolTip(tooltip)
        self.course_table.setItem(row, col, item)

    @staticmethod
    def _make_weekday_combo(weekday) -> QComboBox:
        """星期下拉框：索引 +1 就是 ISO 星期，用户不可能填错数字"""
        combo = QComboBox()
        combo.addItems(WEEKDAY_ITEMS)
        try:
            index = int(weekday) - 1
        except (TypeError, ValueError):
            index = 0
        combo.setCurrentIndex(index if 0 <= index < len(WEEKDAY_ITEMS) else 0)
        return combo

    @staticmethod
    def _make_enabled_widget(checked) -> QWidget:
        """「启用」列的复选框（居中摆放，并把复选框挂在容器上方便回读）"""
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box = QCheckBox()
        box.setChecked(bool(checked))
        layout.addWidget(box)
        holder.checkbox = box  # 回读时直接用 cellWidget(row, col).checkbox
        return holder

    def _cell_text(self, row: int, col: int) -> str:
        """读取文本单元格（空单元格返回空串）"""
        item = self.course_table.item(row, col)
        return item.text().strip() if item is not None else ""

    def _row_to_course(self, row: int) -> dict:
        """把表格一行还原成课程原始数据（尚未校验）"""
        combo = self.course_table.cellWidget(row, COL_WEEKDAY)
        holder = self.course_table.cellWidget(row, COL_ENABLED)
        box = getattr(holder, "checkbox", None)   # 取不到控件时按"启用"处理，避免误判成禁用
        return {
            "name": self._cell_text(row, COL_NAME),
            "weekday": combo.currentIndex() + 1 if isinstance(combo, QComboBox) else 1,
            "start": self._cell_text(row, COL_START),
            "end": self._cell_text(row, COL_END),
            "room": self._cell_text(row, COL_ROOM),
            "remind_before": self._cell_text(row, COL_REMIND),
            "enabled": box.isChecked() if box is not None else True,
        }

    def _collect_courses(self) -> tuple[list[dict] | None, str]:
        """
        校验并收集表格里的全部课程。

        返回 (课程列表, "") 或 (None, "第 N 行：错误原因")。
        校验交给 CourseService，保证设置页和存储层的规则只有一份实现。
        """
        courses: list[dict] = []
        for row in range(self.course_table.rowCount()):
            course, msg = CourseService.normalize_course(self._row_to_course(row))
            if course is None:
                return None, f"第 {row + 1} 行：{msg}"
            courses.append(course)
        return courses, ""

    def _fill_course_table(self, courses: list[dict]) -> None:
        """用课程表数据填充表格"""
        self.course_table.setRowCount(0)
        for course in courses:
            self.add_course_row(course)

    # ── 加载设置 ────────────────────────────────────

    def _load_settings(self):
        """从数据库加载设置"""
        # 城市设置
        current_city = self.db.get("city", "")
        self.city_input.setText(current_city)

        # AI 模型：恢复上次保存的选择（否则保存时会把模型静默重置为第一项）
        saved_model = self.db.get("current_ai_model", "本地对话 (免费)")
        if saved_model in AI_MODELS:
            self.model_combo.setCurrentText(saved_model)  # 触发 _on_model_changed
        else:
            self._on_model_changed(self.model_combo.currentText())

        # 课程表：总开关 + 逐行回填
        self.course_enabled_check.setChecked(self.course_service.is_enabled())
        self._fill_course_table(self.course_service.load_courses())

    # ── 保存 ────────────────────────────────────────

    def _save(self):
        """保存设置到数据库"""
        # 先整体校验课程表：任何一行非法就中止保存（含城市、API 设置），
        # 否则用户改坏一行时间就会连带把已经填好的其它设置一起写进去，
        # 而且数据库里原有的课程数据会被半截数据覆盖。
        courses, error = self._collect_courses()
        if courses is None:
            QMessageBox.warning(
                self,
                "课程表有误",
                f"{error}\n\n请修正后再保存（本次未写入任何设置，原数据保持不变）。",
            )
            return

        # 保存城市设置
        if self.radio_manual.isChecked():
            city = self.city_input.text().strip()
            self.db.set("city", city)
        else:
            self.db.set("city", "")

        # 保存 API 设置
        current_model = self.model_combo.currentText()
        model_key = current_model.split(" ")[0].lower()

        if AI_MODELS[current_model]["is_free"]:
            # 免费模型无需 API 配置，顺手清掉历史遗留的空键
            self.db.delete(f"{model_key}_api_key")
            self.db.delete(f"{model_key}_api_url")
        else:
            api_key = self.api_key_input.text().strip()
            api_url = self.api_url_input.text().strip()
            self.db.set(f"{model_key}_api_key", api_key)
            if api_url:
                self.db.set(f"{model_key}_api_url", api_url)
            else:
                # URL 留空 = 恢复默认端点，删掉旧值避免残留失效地址
                self.db.delete(f"{model_key}_api_url")

        # 保存当前选中的模型
        self.db.set("current_ai_model", current_model)

        # 保存课程表（校验已在上方通过）与总开关
        self.course_service.save_courses(courses)
        self.course_service.set_enabled(self.course_enabled_check.isChecked())

        QMessageBox.information(
            self,
            "保存成功",
            "设置已保存成功！\n部分设置可能需要重启应用后生效。",
        )
        self.accept()
