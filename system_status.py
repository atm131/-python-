"""
系统状态监控模块
用于获取电脑使用状态（CPU、内存、磁盘等）
"""
from __future__ import annotations

import psutil
import platform
from datetime import datetime
from typing import Dict, Any

# 预热 CPU 采样：cpu_percent(interval=None) 返回「自上次调用以来」的平均占用率，
# 首次调用固定返回 0.0。在模块导入时先触发一次，之后查询即可立刻拿到有效值，
# 避免用 interval=1 阻塞 UI 线程整整一秒。
psutil.cpu_percent(interval=None)


class SystemStatus:
    """
    系统状态监控
    获取 CPU、内存、磁盘、网络等信息
    """

    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """获取 CPU 信息"""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)  # 非阻塞，立即返回
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            return {
                "percent": cpu_percent,
                "count": cpu_count,
                "freq_current": cpu_freq.current if cpu_freq else 0,
                "freq_max": cpu_freq.max if cpu_freq else 0,
            }
        except Exception as e:
            return {"percent": 0, "count": 0, "freq_current": 0, "freq_max": 0, "error": str(e)}

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """获取内存信息"""
        try:
            memory = psutil.virtual_memory()
            return {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
            }
        except Exception as e:
            return {"total": 0, "available": 0, "used": 0, "percent": 0, "error": str(e)}

    @staticmethod
    def get_disk_info() -> Dict[str, Any]:
        """获取磁盘信息"""
        try:
            disk = psutil.disk_usage('/')
            return {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            }
        except Exception as e:
            return {"total": 0, "used": 0, "free": 0, "percent": 0, "error": str(e)}

    @staticmethod
    def get_network_info() -> Dict[str, Any]:
        """获取网络信息"""
        try:
            net_io = psutil.net_io_counters()
            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }
        except Exception as e:
            return {"bytes_sent": 0, "bytes_recv": 0, "packets_sent": 0, "packets_recv": 0, "error": str(e)}

    @staticmethod
    def get_battery_info() -> Dict[str, Any]:
        """获取电池信息（笔记本电脑）"""
        try:
            battery = psutil.sensors_battery()
            if battery:
                return {
                    "percent": battery.percent,
                    "power_plugged": battery.power_plugged,
                    "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
                }
            return {"percent": -1, "power_plugged": False, "seconds_left": -1}
        except Exception:
            return {"percent": -1, "power_plugged": False, "seconds_left": -1}

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """获取系统基本信息"""
        try:
            return {
                "system": platform.system(),
                "node": platform.node(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            }
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    def get_all_status(cls) -> Dict[str, Any]:
        """获取所有系统状态信息"""
        return {
            "cpu": cls.get_cpu_info(),
            "memory": cls.get_memory_info(),
            "disk": cls.get_disk_info(),
            "network": cls.get_network_info(),
            "battery": cls.get_battery_info(),
            "system": cls.get_system_info(),
            "timestamp": datetime.now().isoformat(),
        }

    @classmethod
    def format_status_text(cls) -> str:
        """格式化系统状态为可读文本"""
        status = cls.get_all_status()

        lines = []
        lines.append("📊 系统状态报告")
        lines.append("=" * 30)

        # CPU 信息
        cpu = status["cpu"]
        lines.append(f"\n🔲 CPU 使用率: {cpu['percent']}%")
        lines.append(f"   核心数: {cpu['count']}")
        if cpu.get("freq_current"):
            lines.append(f"   频率: {cpu['freq_current']:.0f} MHz")

        # 内存信息
        mem = status["memory"]
        mem_total_gb = mem["total"] / (1024**3)
        mem_used_gb = mem["used"] / (1024**3)
        lines.append(f"\n💾 内存使用: {mem['percent']}%")
        lines.append(f"   已用: {mem_used_gb:.1f} GB / {mem_total_gb:.1f} GB")

        # 磁盘信息
        disk = status["disk"]
        disk_total_gb = disk["total"] / (1024**3)
        disk_used_gb = disk["used"] / (1024**3)
        lines.append(f"\n💿 磁盘使用: {disk['percent']}%")
        lines.append(f"   已用: {disk_used_gb:.1f} GB / {disk_total_gb:.1f} GB")

        # 网络信息
        net = status["network"]
        net_sent_mb = net["bytes_sent"] / (1024**2)
        net_recv_mb = net["bytes_recv"] / (1024**2)
        lines.append(f"\n🌐 网络流量:")
        lines.append(f"   发送: {net_sent_mb:.1f} MB")
        lines.append(f"   接收: {net_recv_mb:.1f} MB")

        # 电池信息
        battery = status["battery"]
        if battery["percent"] >= 0:
            power_status = "充电中" if battery["power_plugged"] else "放电中"
            lines.append(f"\n🔋 电池: {battery['percent']}% ({power_status})")

        # 系统信息
        sys_info = status["system"]
        lines.append(f"\n💻 系统: {sys_info.get('system', '未知')}")
        lines.append(f"   主机名: {sys_info.get('node', '未知')}")

        lines.append(f"\n⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    @classmethod
    def get_status_summary(cls) -> str:
        """获取简短的状态摘要（用于气泡显示）"""
        status = cls.get_all_status()

        cpu = status["cpu"]["percent"]
        mem = status["memory"]["percent"]
        disk = status["disk"]["percent"]

        # 状态评估
        if cpu > 90 or mem > 90:
            emoji = "\U0001f534"  # 红色圆
            advice = "系统负载较高，建议关闭一些程序"
        elif cpu > 70 or mem > 70:
            emoji = "\U0001f7e1"  # 黄色圆
            advice = "系统运行正常，负载适中"
        else:
            emoji = "\U0001f7e2"  # 绿色圆
            advice = "系统运行良好，状态健康"

        summary = f"{emoji} 系统状态摘要\n"
        summary += f"CPU: {cpu}% | 内存: {mem}% | 磁盘: {disk}%\n"
        summary += f"{advice}"

        return summary


# ─── 测试代码 ─────────────────────────────────────────────

if __name__ == "__main__":
    print(SystemStatus.format_status_text())
    print("\n" + "=" * 30)
    print(SystemStatus.get_status_summary())
