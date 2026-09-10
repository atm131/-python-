"""
系统监控模块
后台线程采集 CPU / 内存 / 网络 / 磁盘数据，
通过事件总线将状态变化通知给 UI 和 AI 模块。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psutil

from config import MonitorConfig
from plugin_manager import EventBus


# ─── 系统快照数据结构 ─────────────────────────────────────

@dataclass
class SystemSnapshot:
    """某一时刻的系统状态快照"""
    timestamp: str
    cpu_percent: float
    mem_percent: float
    mem_used_gb: float
    mem_total_gb: float
    net_sent_mb: float       # 瞬时上传速率 (MB/s)
    net_recv_mb: float       # 瞬时下载速率 (MB/s)
    disk_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cpu": self.cpu_percent,
            "mem": self.mem_percent,
            "mem_used_gb": round(self.mem_used_gb, 2),
            "mem_total_gb": round(self.mem_total_gb, 2),
            "net_sent_mb": round(self.net_sent_mb, 3),
            "net_recv_mb": round(self.net_recv_mb, 3),
            "disk": self.disk_percent,
        }

    @property
    def load_level(self) -> str:
        """
        综合负载等级：normal / warning / critical
        供宠物 UI 决定动画状态
        """
        if self.cpu_percent > 90 or self.mem_percent > 95:
            return "critical"
        if self.cpu_percent > 75 or self.mem_percent > 85:
            return "warning"
        return "normal"


# ─── 系统监控器 ───────────────────────────────────────────

class SystemMonitor:
    """
    后台守护线程，定时采集系统指标。

    设计要点：
    - 线程安全：采集结果存入 deque，UI 线程可随时读取
    - 事件驱动：状态变化时通过 EventBus 发射事件
    - 阈值去抖：避免频繁触发阈值事件，设置冷却时间

    发射的事件：
    - "monitor.snapshot"    — 每次采集完成
    - "monitor.cpu_high"    — CPU 超过阈值
    - "monitor.mem_high"    — 内存超过阈值
    - "monitor.load_change" — 综合负载等级变化
    """

    def __init__(self, config: MonitorConfig, bus: EventBus):
        self.config = config
        self.bus = bus
        self.history: deque[SystemSnapshot] = deque(maxlen=config.history_maxlen)
        self.latest: SystemSnapshot | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._prev_net = psutil.net_io_counters()
        self._prev_net_time = time.time()
        self._last_load_level = "normal"
        # 阈值事件冷却（秒）
        self._cooldown_sec = 10.0
        self._last_cpu_high_time = 0.0
        self._last_mem_high_time = 0.0

    # ── 生命周期 ──────────────────────────────────

    def start(self):
        """启动后台采集线程"""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="SysMonitor"
        )
        self._thread.start()
        print("[Monitor] 后台监控已启动")

    def stop(self):
        """停止采集"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[Monitor] 已停止")

    # ── 采集循环 ──────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                snapshot = self._collect()
                self.latest = snapshot
                self.history.append(snapshot)

                # 发射采集事件
                self.bus.emit("monitor.snapshot", snapshot.to_dict())

                # 阈值检测与去抖
                now = time.time()
                if snapshot.cpu_percent > self.config.cpu_high_threshold:
                    if now - self._last_cpu_high_time > self._cooldown_sec:
                        self._last_cpu_high_time = now
                        self.bus.emit("monitor.cpu_high", {
                            "cpu": snapshot.cpu_percent,
                            "threshold": self.config.cpu_high_threshold,
                        })

                if snapshot.mem_percent > self.config.mem_high_threshold:
                    if now - self._last_mem_high_time > self._cooldown_sec:
                        self._last_mem_high_time = now
                        self.bus.emit("monitor.mem_high", {
                            "mem": snapshot.mem_percent,
                            "threshold": self.config.mem_high_threshold,
                        })

                # 综合负载等级变化
                level = snapshot.load_level
                if level != self._last_load_level:
                    self.bus.emit("monitor.load_change", {
                        "old_level": self._last_load_level,
                        "new_level": level,
                        "snapshot": snapshot.to_dict(),
                    })
                    self._last_load_level = level

            except Exception as e:
                print(f"[Monitor] 采集异常: {e}")

            time.sleep(self.config.interval_sec)

    # ── 数据采集 ──────────────────────────────────

    def _collect(self) -> SystemSnapshot:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        net = psutil.net_io_counters()
        now = time.time()
        elapsed = max(now - self._prev_net_time, 0.1)
        sent_mb = (net.bytes_sent - self._prev_net.bytes_sent) / 1048576 / elapsed
        recv_mb = (net.bytes_recv - self._prev_net.bytes_recv) / 1048576 / elapsed
        self._prev_net = net
        self._prev_net_time = now

        return SystemSnapshot(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            cpu_percent=round(cpu, 1),
            mem_percent=round(mem.percent, 1),
            mem_used_gb=mem.used / (1024 ** 3),
            mem_total_gb=mem.total / (1024 ** 3),
            net_sent_mb=max(round(sent_mb, 3), 0),
            net_recv_mb=max(round(recv_mb, 3), 0),
            disk_percent=round(disk.percent, 1),
        )

    # ── 公共查询接口 ──────────────────────────────

    def get_summary(self) -> str:
        """返回当前系统状态的文字摘要，供 LLM 使用"""
        s = self.latest
        if not s:
            return "系统监控数据暂未就绪。"
        return (
            f"【系统状态】\n"
            f"  CPU: {s.cpu_percent}% | "
            f"内存: {s.mem_percent}% ({s.mem_used_gb:.1f}/{s.mem_total_gb:.1f} GB)\n"
            f"  网络↑: {s.net_sent_mb:.3f} MB/s | ↓: {s.net_recv_mb:.3f} MB/s\n"
            f"  磁盘: {s.disk_percent}% | 负载等级: {s.load_level}"
        )

    def get_history_list(self, limit: int = 100) -> list[dict]:
        """返回最近 N 条历史记录"""
        items = list(self.history)[-limit:]
        return [s.to_dict() for s in items]
