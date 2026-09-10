"""
╔══════════════════════════════════════════════════════════════════╗
║          🐾 Windows 智能桌面宠物助手  —  应用入口              ║
║                                                                  ║
║  职责：                                                          ║
║  1. 实例化全局配置                                               ║
║  2. 初始化天气服务                                               ║
║  3. 启动桌面宠物 UI                                              ║
║  4. 处理全局异常与优雅退出                                       ║
╚══════════════════════════════════════════════════════════════════╝

安装依赖：
    pip install PyQt6 requests

运行：
    python main.py
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QMessageBox

from config import AppConfig
from pet_window import PetWindow
from weather_service import WeatherService


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


# ─── 主应用 ────────────────────────────────────────────────

class Application:
    """
    应用主类，负责组装所有模块并管理生命周期。

    启动顺序：
    1. AppConfig      → 配置实例化
    2. WeatherService → 天气查询服务
    3. QApplication   → Qt 应用
    4. PetWindow      → 桌面宠物 UI
    5. 进入 Qt 事件循环
    """

    def __init__(self):
        # 1. 配置
        self.config = AppConfig()

        # 2. 天气服务
        self.weather_service = WeatherService(
            api_key=self.config.weather.api_key,
            city=self.config.weather.city,
            lang=self.config.weather.lang,
        )

        # 3. Qt 应用
        self.qt_app = QApplication(sys.argv)

        # 4. 桌面宠物 UI
        self.pet = PetWindow(self.config, self.weather_service)

    def run(self) -> int:
        """启动应用，进入事件循环"""
        print("[App] 正在启动...")

        # 显示宠物
        self.pet.show()
        self.pet.show_bubble(
            f"你好！我是{self.config.pet.name}～\n点击我查看天气！",
            5000,
        )

        print("[App] 启动完成，进入事件循环")
        exit_code = self.qt_app.exec()

        print("[App] 已退出")
        return exit_code


# ─── 入口 ──────────────────────────────────────────────────

def main():
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║          🐾  Windows 智能桌面宠物助手  v2.0                  ║
║      自定义形象 · 天气查询 · 拖拽交互 · 气泡提示             ║
╚══════════════════════════════════════════════════════════════╝
    """
    )
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
