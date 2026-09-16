"""
╔══════════════════════════════════════════════════════════════════╗
║          🐾 Windows 智能桌面宠物助手  —  应用入口              ║
║                                                                  ║
║  职责：                                                          ║
║  1. 初始化本地数据库                                             ║
║  2. 初始化天气服务（免费 API，无需 Key）                         ║
║  3. 启动桌面宠物 UI                                              ║
║  4. 处理全局异常与优雅退出                                       ║
║  5. 启动课程提醒（每分钟检查课程表）                             ║
╚══════════════════════════════════════════════════════════════════╝

安装依赖：
    pip install PyQt6 requests

运行：
    python main.py
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from config import MonitorConfig, UIConfig
from course_service import CourseReminder
from db_manager import DBManager
from pet_window import PetWindow
from plugin_manager import EventBus, PluginManager
from system_monitor import SystemMonitor
from weather_service import WeatherService


# ─── 跨线程告警桥 ─────────────────────────────────────────

class AlertBridge(QObject):
    """
    把后台监控线程的事件安全地转发到 GUI 线程。

    SystemMonitor 是纯 threading.Thread（没有 Qt 事件循环），在那里
    调用 QTimer.singleShot 永远不会触发（Qt 定时器只能用于 QThread
    启动且有事件循环的线程）。而 pyqtSignal 发射时 Qt 会自动按队列连接
    把槽函数调度到接收者所在的 GUI 线程，跨线程安全可靠。
    """
    show_bubble = pyqtSignal(str, int)   # 气泡文本, 显示时长 ms
    set_state = pyqtSignal(str, int)     # 宠物状态, 自动回退 ms


# ─── 全局异常处理 ──────────────────────────────────────────

def excepthook(exc_type, exc_value, exc_tb):
    """捕获未处理异常，写入日志并弹窗提示"""
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"\n{'='*60}\n[FATAL] 未处理异常:\n{tb}\n{'='*60}")
    with open("crash.log", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now().isoformat()}]\n{tb}\n")
    try:
        QMessageBox.critical(None, "错误", f"发生未处理异常:\n{exc_value}")
    except Exception:
        pass


sys.excepthook = excepthook

# 锚定到脚本所在目录：无论从哪个工作目录启动（快捷方式 / 开机自启），
# 数据库、插件、资源、crash.log 都落在项目目录，不会在别处生成副本
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)

# 应用图标（宠物形象，相对项目路径，随项目一起拷贝）
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "pet.ico")
if not os.path.exists(ICON_PATH):
    ICON_PATH = os.path.join(ASSETS_DIR, "pet.png")


# ─── 主应用 ────────────────────────────────────────────────

class Application:
    """
    应用主类，负责组装所有模块并管理生命周期。

    启动顺序：
    1. DBManager       → 本地数据库
    2. WeatherService  → 天气查询服务（免费 API）
    3. EventBus + PluginManager → 事件总线与插件系统
    4. QApplication    → Qt 应用
    5. PetWindow       → 桌面宠物 UI
    6. SystemMonitor   → 后台系统监控线程（事件驱动 UI 气泡）
    7. CourseReminder  → 课程提醒调度（QTimer，必须在 QApplication 之后创建）
    8. 进入 Qt 事件循环
    """

    def __init__(self):
        # 1. 本地数据库
        self.db = DBManager("pet_settings.db")

        # 2. UI 配置
        self.ui_config = UIConfig()

        # 3. 天气服务（免费 wttr.in API，无需 Key）
        self.weather_service = WeatherService(db=self.db)

        # 4. 事件总线 + 插件系统（扫描 plugins/ 目录，注册 /天气 /课程 等命令）
        #    传入 db：插件（如课程表插件）可直接读设置，不必自己新建数据库连接
        self.bus = EventBus()
        self.plugin_manager = PluginManager(self.bus, plugins_dir="plugins", db=self.db)
        self.plugin_manager.load_plugins()

        # 5. Qt 应用（设置应用级图标，对话框标题栏 / Alt+Tab 均使用宠物形象）
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setWindowIcon(QIcon(ICON_PATH))

        # 6. 桌面宠物 UI
        self.pet = PetWindow(self.db, self.weather_service, self.ui_config,
                             plugin_manager=self.plugin_manager)

        # 7. 后台系统监控线程（采集 CPU/内存/磁盘/网络，超阈值时弹气泡）
        self.monitor = SystemMonitor(MonitorConfig(), self.bus)
        # 监控线程 → GUI 线程的信号桥（在 GUI 线程创建并连接）
        self._bridge = AlertBridge()
        self._bridge.show_bubble.connect(self.pet.show_bubble)
        self._bridge.set_state.connect(self.pet.set_state)
        self.bus.on("monitor.cpu_high", self._on_cpu_high)
        self.bus.on("monitor.mem_high", self._on_mem_high)
        # 插件请求气泡（如天气插件的 CPU 过热提醒）
        self.bus.on("pet.show_bubble", self._on_plugin_bubble)

        # 8. 课程提醒调度：QTimer 每 60 秒检查一次课程表，到点前经事件总线弹气泡。
        #    放在这里（QApplication 与 PetWindow 之后）实例化 —— 插件在 QApplication
        #    之前加载，在那里创建 QTimer 是不安全的；全部逻辑都在 GUI 线程内，无需线程。
        self.course_reminder = CourseReminder(self.db, self.bus)
        self.course_reminder.start()

    # ── 系统监控事件回调（运行在监控线程，只做信号转发）─────

    def _on_cpu_high(self, event):
        """CPU 持续高负载时提醒（监控线程有 10 秒冷却去抖）"""
        cpu = event.data.get("cpu", 0)
        self._bridge.set_state.emit("alert", 10000)   # 晕乎乎表情
        self._bridge.show_bubble.emit(
            f"⚠️ CPU 占用较高（{cpu}%）\n要不要关掉一些程序？", 6000)

    def _on_mem_high(self, event):
        """内存持续高负载时提醒"""
        mem = event.data.get("mem", 0)
        self._bridge.set_state.emit("alert", 10000)
        self._bridge.show_bubble.emit(
            f"⚠️ 内存占用较高（{mem}%）\n注意及时释放内存哦", 6000)

    def _on_plugin_bubble(self, event):
        """插件通过 pet.show_bubble 事件请求显示气泡"""
        text = event.data.get("text", "")
        duration = int(event.data.get("duration", 5000))
        if text:
            self._bridge.show_bubble.emit(text, duration)

    def run(self) -> int:
        """启动应用，进入事件循环"""
        print("[App] 正在启动...")

        self.pet.show()
        self.monitor.start()

        pet_name = self.db.get("pet_name", "小d")
        self.pet.set_state("greet", 10000)   # 举手打招呼
        self.pet.show_bubble(
            f"你好！我是{pet_name}～\n"
            f"🖱️ 单击：AI 对话\n"
            f"🖱️ 双击：天气\n"
            f"🖱️ 右键：菜单\n"
            f"⌨️ 对话中可用 /天气 北京、/课程 等命令",
            10000,
        )

        print("[App] 启动完成，进入事件循环")
        exit_code = self.qt_app.exec()

        # 退出清理
        self.course_reminder.stop()
        self.monitor.stop()
        self.plugin_manager.teardown_all()
        print("[App] 已退出")
        return exit_code


# ─── 入口 ──────────────────────────────────────────────────

def main():
    print(
        """
+============================================================+
|          Windows 智能桌面宠物助手  v3.0                      |
|   免费天气API / 本地数据库 / 右键菜单 / 设置对话框            |
+============================================================+
    """
    )
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
