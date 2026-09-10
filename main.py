"""
╔══════════════════════════════════════════════════════════════════╗
║          🐾 Windows 智能桌面宠物助手  —  应用入口              ║
║                                                                  ║
║  职责：                                                          ║
║  1. 实例化全局配置                                               ║
║  2. 初始化事件总线                                               ║
║  3. 启动各子系统（监控 / RAG / 插件）                            ║
║  4. 启动桌面宠物 UI                                              ║
║  5. 处理全局异常与优雅退出                                       ║
╚══════════════════════════════════════════════════════════════════╝

安装依赖：
    pip install PyQt6 psutil numpy requests sentence-transformers chromadb

运行：
    python main.py
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from config import AppConfig
from pet_ui import DesktopPet, PetState
from plugin_manager import EventBus, PluginManager
from rag_engine import LLMClient, VectorStore
from system_monitor import SystemMonitor


# ─── 全局异常处理 ──────────────────────────────────────────

def excepthook(exc_type, exc_value, exc_tb):
    """捕获未处理异常，写入日志并弹窗提示"""
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"\n{'='*60}\n[FATAL] 未处理异常:\n{tb}\n{'='*60}")
    # 写入日志文件
    with open("crash.log", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now().isoformat()}]\n{tb}\n")
    # 尝试弹窗
    try:
        QMessageBox.critical(None, "错误", f"发生未处理异常:\n{exc_value}")
    except Exception:
        pass


sys.excepthook = excepthook


# ─── 对话输入窗口 ──────────────────────────────────────────

class ChatDialog:
    """
    简易对话输入窗口。
    由宠物双击或插件触发，输入文字后交给 LLM 处理。
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._open = False

    def show(self):
        if self._open:
            return
        self._open = True
        text, ok = QInputDialog.getText(
            None, "💬 和小智对话", "输入你的问题:",
            QLineEdit.EchoMode.Normal,
        )
        self._open = False
        if ok and text.strip():
            self.bus.emit("user.chat", {"text": text.strip()})


# ─── 主应用组装 ────────────────────────────────────────────

class Application:
    """
    应用主类，负责组装所有模块并管理生命周期。

    启动顺序：
    1. AppConfig    → 配置实例化
    2. EventBus     → 事件总线
    3. PluginManager→ 加载插件
    4. VectorStore  → 知识库初始化
    5. LLMClient    → AI 引擎
    6. SystemMonitor→ 系统监控
    7. DesktopPet   → 桌面宠物 UI
    8. 注册事件联动
    9. 进入 Qt 事件循环
    """

    def __init__(self):
        # 1. 配置
        self.config = AppConfig()

        # 2. 事件总线（全局唯一）
        self.bus = EventBus()

        # 3. 插件管理器
        self.plugin_mgr = PluginManager(self.bus, self.config.plugins_dir)
        self.plugin_mgr.load_plugins()

        # 4. 知识库
        self.vector_store = VectorStore(self.config.rag)

        # 5. AI 引擎
        self.llm = LLMClient(self.config.llm, self.bus, self.vector_store)

        # 6. 系统监控
        self.monitor = SystemMonitor(self.config.monitor, self.bus)

        # 7. Qt 应用
        self.qt_app = QApplication(sys.argv)

        # 8. 桌面宠物 UI
        self.pet = DesktopPet(self.config, self.bus)

        # 9. 对话窗口
        self.chat_dialog = ChatDialog(self.bus)

        # 注册事件联动
        self._wire_events()

    def _wire_events(self):
        """连接各模块之间的事件"""
        # 宠物双击 → 打开对话
        self.bus.on("pet.double_clicked", lambda e: self.chat_dialog.show())

        # 用户发送消息 → 调用 LLM
        self.bus.on("user.chat", self._on_user_chat)

        # LLM 流式输出 → 气泡显示
        self.bus.on("llm.stream_token", self._on_stream_token)
        self.bus.on("llm.stream_end", self._on_stream_end)

        # 系统高负载 → 气泡提醒
        self.bus.on("monitor.cpu_high", lambda e: self.pet.show_bubble(
            f"CPU 使用率 {e.data['cpu']:.1f}%，有点高哦！", 4000
        ))
        self.bus.on("monitor.mem_high", lambda e: self.pet.show_bubble(
            f"内存使用率 {e.data['mem']:.1f}%，考虑清理一下？", 4000
        ))

        # 宠物右键导入
        self.bus.on("pet.right_click", self._on_pet_right_click)

        # 通配符监听（调试用，可注释掉）
        # self.bus.on("*", lambda e: print(f"[Event] {e.name}: {e.data}"))

    # ── 事件处理器 ────────────────────────────────

    def _on_user_chat(self, event):
        """处理用户输入，调用 LLM"""
        text = event.data.get("text", "")
        if not text:
            return

        # 先检查插件命令
        result = self.plugin_mgr.dispatch_command(text)
        if result is not None:
            self.pet.show_bubble(result, 8000)
            return

        # 组装系统上下文
        context = self.monitor.get_summary()
        self.pet.show_bubble("正在思考...", 30000)
        self.llm.chat_async(text, context=context)

    _stream_buffer: list[str] = []

    def _on_stream_token(self, event):
        """收集流式 token（不逐个显示，避免气泡闪烁）"""
        token = event.data.get("token", "")
        self._stream_buffer.append(token)

    def _on_stream_end(self, event):
        """流式结束，显示完整回复"""
        full_text = event.data.get("full_text", "")
        if not full_text:
            full_text = "".join(self._stream_buffer)
        self._stream_buffer.clear()
        # 截断过长文本
        if len(full_text) > 200:
            display = full_text[:200] + "..."
        else:
            display = full_text
        self.pet.show_bubble(display, 10000)

    def _on_pet_right_click(self, event):
        """处理右键菜单动作"""
        action = event.data.get("action", "")
        if action == "import":
            self._import_knowledge_file()
        elif action == "commands":
            self._show_command_list()

    def _import_knowledge_file(self):
        """弹出文件选择对话框导入知识"""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            None, "选择知识文件", "",
            "文本文件 (*.txt *.md *.csv);;所有文件 (*.*)"
        )
        if file_path:
            try:
                count = self.vector_store.add_file(file_path)
                self.pet.show_bubble(f"已导入 {count} 个知识块！", 5000)
            except Exception as e:
                self.pet.show_bubble(f"导入失败: {e}", 5000)

    def _show_command_list(self):
        """显示已注册的插件命令"""
        commands = self.plugin_mgr.list_commands()
        if not commands:
            self.pet.show_bubble("暂无已注册的插件命令", 3000)
            return
        lines = [f"/{c['command']} - {c['desc']}" for c in commands]
        self.pet.show_bubble("可用命令:\n" + "\n".join(lines), 8000)

    # ── 启动 / 退出 ──────────────────────────────

    def run(self) -> int:
        """启动应用，进入事件循环"""
        print("[App] 正在启动...")

        # 启动系统监控
        self.monitor.start()

        # 显示宠物
        self.pet.show()
        self.pet.show_bubble(f"你好！我是{self.config.pet.name}，很高兴见到你！", 5000)

        print("[App] 启动完成，进入事件循环")
        exit_code = self.qt_app.exec()

        # 清理
        self._cleanup()
        return exit_code

    def _cleanup(self):
        """优雅退出：清理所有资源"""
        print("[App] 正在清理资源...")
        self.monitor.stop()
        self.plugin_mgr.teardown_all()
        print("[App] 已退出")


# ─── 入口 ──────────────────────────────────────────────────

def main():
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║          🐾  Windows 智能桌面宠物助手  v1.0                  ║
║  桌面宠物 · 系统监控 · RAG知识库 · LLM对话 · 插件扩展       ║
╚══════════════════════════════════════════════════════════════╝
    """
    )
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
