"""
示例插件：天气查询
演示如何使用插件系统注册命令和监听事件。

用法：
    /天气 北京
    /weather Shanghai
"""
from __future__ import annotations

import requests

from plugin_manager import EventBus, PluginBase


class WeatherPlugin(PluginBase):
    """天气查询插件"""

    name = "天气查询"
    version = "1.0.0"
    description = "查询城市天气信息，支持中英文城市名"

    # 免费天气 API（无需 API Key）
    API_URL = "https://wttr.in/{city}?format=j1"

    def __init__(self, bus: EventBus):
        super().__init__(bus)

    def setup(self):
        """注册命令和事件监听"""
        self.register_command(
            name="天气",
            description="查询天气，用法: /天气 城市名",
            handler=self.handle_weather,
        )
        self.register_command(
            name="weather",
            description="Query weather, usage: /weather city",
            handler=self.handle_weather,
        )

        # 监听系统高负载事件，自动提醒注意散热
        self.bus.on("monitor.cpu_high", self._on_cpu_high)

    def handle_weather(self, args: dict) -> str:
        """处理天气查询命令"""
        city = args.get("args", "").strip()
        if not city:
            return "请指定城市名，例如: /天气 北京"

        try:
            resp = requests.get(
                self.API_URL.format(city=city),
                headers={"Accept-Language": "zh-CN"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current_condition", [{}])[0]
            temp = current.get("temp_C", "?")
            feels_like = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            desc_list = current.get("lang_zh", current.get("weatherDesc", [{}]))
            desc = desc_list[0].get("value", "未知") if desc_list else "未知"
            wind_speed = current.get("windspeedKmph", "?")

            return (
                f"🌤 {city} 天气:\n"
                f"  温度: {temp}°C (体感 {feels_like}°C)\n"
                f"  天气: {desc}\n"
                f"  湿度: {humidity}%\n"
                f"  风速: {wind_speed} km/h"
            )
        except requests.RequestException as e:
            return f"⚠️ 天气查询失败: {e}"
        except (KeyError, IndexError) as e:
            return f"⚠️ 天气数据解析失败: {e}"

    def _on_cpu_high(self, event):
        """CPU 过高时提醒用户注意散热"""
        # 这里可以发射气泡事件，但不直接操作 UI
        # 而是通过事件总线通知
        cpu = event.data.get("cpu", 0)
        if cpu > 90:
            self.bus.emit("pet.show_bubble", {
                "text": f"CPU {cpu}%！注意散热，要不要开窗通风？",
                "duration": 5000,
            })

    def teardown(self):
        """清理资源"""
        pass
