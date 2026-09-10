"""
插件管理器与事件总线
提供松耦合的事件驱动机制，允许插件注册命令、监听系统事件。
"""
from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable


# ─── 事件数据结构 ────────────────────────────────────────

@dataclass
class Event:
    """事件对象，通过事件总线传递"""
    name: str                         # 事件名称，如 "system.cpu_high"
    data: dict[str, Any] = field(default_factory=dict)
    _stopped: bool = False            # 是否停止传播

    def stop(self):
        """阻止后续处理器继续接收此事件"""
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped


# ─── 事件总线 ─────────────────────────────────────────────

class EventBus:
    """
    全局事件总线，实现 发布-订阅 模式。

    设计要点：
    - 支持通配符监听 "*"（接收所有事件）
    - 支持命名空间，用 "." 分隔，如 "system.cpu_high"
    - 处理器按注册顺序执行，可通过 event.stop() 中断传播
    - 支持一次性监听（listen_once）

    用法示例：
        bus = EventBus()
        bus.on("user.chat", lambda e: print(e.data["text"]))
        bus.emit("user.chat", {"text": "你好"})
    """

    def __init__(self):
        # {event_name: [handler, ...]}
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}
        # 一次性处理器集合，用于 listen_once
        self._once_handlers: set[Callable] = set()

    def on(self, event_name: str, handler: Callable[[Event], None]):
        """注册事件监听器。event_name 支持具体名称或 "*" 通配符。"""
        self._handlers.setdefault(event_name, []).append(handler)

    def once(self, event_name: str, handler: Callable[[Event], None]):
        """注册一次性监听器，触发后自动移除。"""
        self._once_handlers.add(handler)
        self.on(event_name, handler)

    def off(self, event_name: str, handler: Callable[[Event], None] | None = None):
        """移除监听器。handler=None 则移除该事件的所有监听器。"""
        if handler is None:
            self._handlers.pop(event_name, None)
        elif event_name in self._handlers:
            self._handlers[event_name] = [
                h for h in self._handlers[event_name] if h != handler
            ]

    def emit(self, event_name: str, data: dict[str, Any] | None = None) -> Event:
        """
        发射事件。按注册顺序依次调用处理器。
        返回 Event 对象，可通过 event.is_stopped 判断是否被中断。
        """
        event = Event(name=event_name, data=data or {})

        # 收集所有匹配的处理器：精确匹配 + 通配符
        handlers = list(self._handlers.get(event_name, []))
        handlers.extend(self._handlers.get("*", []))

        for handler in handlers:
            if event.is_stopped:
                break
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] 处理器异常 ({event_name}): {e}")
            finally:
                # 一次性处理器触发后移除
                if handler in self._once_handlers:
                    self._once_handlers.discard(handler)
                    if event_name in self._handlers:
                        self._handlers[event_name] = [
                            h for h in self._handlers[event_name] if h != handler
                        ]

        return event

    def list_events(self) -> list[str]:
        """返回所有已注册监听的事件名列表"""
        return list(self._handlers.keys())


# ─── 插件基类 ─────────────────────────────────────────────

class PluginBase:
    """
    插件基类，所有插件必须继承此类。

    生命周期：
    1. __init__  — 实例化
    2. setup()   — 注册事件监听、初始化资源
    3. teardown()— 清理资源（程序退出时调用）

    属性：
    - name:     插件名称
    - version:  版本号
    - commands: 该插件注册的命令列表 [{"name": ..., "desc": ..., "handler": ...}]
    """

    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.commands: list[dict[str, Any]] = []

    def setup(self):
        """初始化阶段：注册事件监听、注册命令等"""
        pass

    def teardown(self):
        """清理阶段：释放资源"""
        pass

    def register_command(self, name: str, description: str,
                         handler: Callable[[dict], Any]):
        """快捷方法：注册一个用户命令"""
        self.commands.append({
            "name": name,
            "desc": description,
            "handler": handler,
        })
        # 同时发射事件，让其他模块知晓
        self.bus.emit("plugin.command_registered", {
            "plugin": self.name,
            "command": name,
            "desc": description,
        })


# ─── 插件管理器 ───────────────────────────────────────────

class PluginManager:
    """
    插件加载器与生命周期管理器。

    职责：
    - 扫描插件目录，动态加载 .py 文件
    - 实例化所有 PluginBase 子类并调用 setup()
    - 程序退出时调用 teardown()
    - 提供命令路由：根据用户输入查找匹配的插件命令

    目录约定：
        plugins/
        ├── weather_plugin.py    # 单文件插件
        ├── schedule_plugin.py
        └── ...
    """

    def __init__(self, bus: EventBus, plugins_dir: str = "plugins"):
        self.bus = bus
        self.plugins_dir = plugins_dir
        self.plugins: list[PluginBase] = []
        self._commands: dict[str, tuple[PluginBase, Callable]] = {}

    def load_plugins(self):
        """扫描插件目录并加载所有插件"""
        if not os.path.isdir(self.plugins_dir):
            print(f"[PluginManager] 插件目录不存在: {self.plugins_dir}")
            return

        # 将插件目录加入 sys.path 以便 import
        abs_dir = os.path.abspath(self.plugins_dir)
        if abs_dir not in sys.path:
            sys.path.insert(0, abs_dir)

        for filename in sorted(os.listdir(abs_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            module_name = filename[:-3]
            try:
                module = importlib.import_module(module_name)
                self._register_module(module)
                print(f"[PluginManager] 已加载插件: {filename}")
            except Exception as e:
                print(f"[PluginManager] 加载失败 {filename}: {e}")

    def _register_module(self, module):
        """扫描模块中的 PluginBase 子类并实例化"""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase):
                plugin = attr(self.bus)
                plugin.setup()
                self.plugins.append(plugin)
                # 注册该插件的所有命令
                for cmd in plugin.commands:
                    cmd_name = cmd["name"].lower()
                    self._commands[cmd_name] = (plugin, cmd["handler"])

    def dispatch_command(self, user_input: str) -> str | None:
        """
        尝试将用户输入分发给插件命令。
        匹配规则：用户输入以 "/命令名" 开头。
        返回插件响应文本，无匹配返回 None。
        """
        text = user_input.strip()
        if not text.startswith("/"):
            return None
        parts = text.split(maxsplit=1)
        cmd_name = parts[0][1:].lower()  # 去掉 "/" 前缀
        args_text = parts[1] if len(parts) > 1 else ""

        if cmd_name in self._commands:
            plugin, handler = self._commands[cmd_name]
            try:
                result = handler({"args": args_text, "raw": text})
                return str(result) if result is not None else f"✅ /{cmd_name} 执行完成"
            except Exception as e:
                return f"❌ /{cmd_name} 执行失败: {e}"
        return None

    def list_commands(self) -> list[dict]:
        """返回所有已注册的插件命令"""
        result = []
        for plugin in self.plugins:
            for cmd in plugin.commands:
                result.append({
                    "plugin": plugin.name,
                    "command": cmd["name"],
                    "desc": cmd["desc"],
                })
        return result

    def teardown_all(self):
        """程序退出时调用，清理所有插件"""
        for plugin in reversed(self.plugins):
            try:
                plugin.teardown()
            except Exception as e:
                print(f"[PluginManager] 清理异常 ({plugin.name}): {e}")
        print(f"[PluginManager] 已清理 {len(self.plugins)} 个插件")
