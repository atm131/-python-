"""
天气服务模块
调用 OpenWeatherMap API 获取实时天气，并生成出行建议。
"""
from __future__ import annotations

import requests


class WeatherService:
    """
    天气查询服务。

    使用 OpenWeatherMap 免费 API：
    https://api.openweathermap.org/data/2.5/weather

    参数：
        api_key: OpenWeatherMap API Key
        city:    查询城市名（中文或英文均可，如 "Beijing" 或 "上海"）
                 留空则自动通过 IP 定位获取当前城市
        lang:    返回语言，默认 zh_cn（简体中文）
        units:   温度单位，metric=摄氏度
    """

    # 免费 IP 地理定位服务（无需 API Key）
    _GEO_API = "http://ip-api.com/json/?lang=zh-CN&fields=status,country,city"

    def __init__(self, api_key: str, city: str = "", lang: str = "zh_cn"):
        self.api_key = api_key
        self.city = city
        self.lang = lang
        self._auto_city: str | None = None  # 缓存自动定位的城市

    @staticmethod
    def detect_city() -> str:
        """
        通过 IP 地理定位自动获取当前城市。
        使用 ip-api.com 免费服务，无需 API Key。
        """
        try:
            resp = requests.get(
                WeatherService._GEO_API,
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "success":
                city = data.get("city", "")
                if city:
                    print(f"[Weather] IP 定位成功: {city}")
                    return city
            print("[Weather] IP 定位返回失败状态")
            return ""
        except requests.RequestException as e:
            print(f"[Weather] IP 定位失败: {e}")
            return ""

    def _resolve_city(self) -> str:
        """获取要查询的城市名：优先使用配置值，否则自动定位"""
        if self.city:
            return self.city
        # 首次自动定位，结果缓存
        if self._auto_city is None:
            self._auto_city = self.detect_city()
        return self._auto_city or "Beijing"

    def fetch(self) -> dict:
        """
        请求天气 API，返回解析后的结果字典。

        返回结构：
        {
            "city":       str,   # 城市名
            "temp":       float, # 当前温度（℃）
            "feels_like": float, # 体感温度（℃）
            "humidity":   int,   # 湿度 %
            "description": str,  # 天气描述，如"多云"
            "advice":     str,   # 出行建议
            "error":      str | None
        }
        """
        if not self.api_key:
            return self._fallback("未配置 API Key，请在 config.py 中填写。")

        city = self._resolve_city()
        if not city:
            return self._fallback("无法获取城市信息，请检查网络或手动配置城市。")

        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": city,
                    "appid": self.api_key,
                    "units": "metric",
                    "lang": self.lang,
                },
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()

            weather = data.get("weather", [{}])[0]
            main = data.get("main", {})

            temp = round(main.get("temp", 0), 1)
            feels_like = round(main.get("feels_like", 0), 1)
            humidity = main.get("humidity", 0)
            description = weather.get("description", "未知")
            weather_main = weather.get("main", "")

            advice = self._generate_advice(temp, description, weather_main, humidity)

            return {
                "city": data.get("name", city),
                "temp": temp,
                "feels_like": feels_like,
                "humidity": humidity,
                "description": description,
                "advice": advice,
                "error": None,
            }

        except requests.RequestException as e:
            return self._fallback(f"网络请求失败: {e}")
        except (KeyError, IndexError, ValueError) as e:
            return self._fallback(f"数据解析失败: {e}")

    # ── 出行建议生成 ──────────────────────────────

    @staticmethod
    def _generate_advice(temp: float, desc: str, weather_main: str, humidity: int) -> str:
        """根据天气状况生成一句出行建议"""
        desc_lower = desc.lower()
        main_lower = weather_main.lower()

        # 降水类
        if any(k in desc_lower for k in ("雨", "rain", "shower", "drizzle")):
            return "今天有雨，记得带伞哦！☂️"
        if any(k in desc_lower for k in ("雪", "snow", "sleet")):
            return "下雪了，路面湿滑，注意保暖和出行安全！🧣"
        if any(k in desc_lower for k in ("雷", "thunder", "storm")):
            return "雷暴天气，尽量待在室内，远离空旷地带！⚡"

        # 极端温度
        if temp >= 38:
            return "高温预警！尽量避免外出，注意防暑降温！🥵"
        if temp >= 33:
            return "天气炎热，多喝水，外出注意防晒！🧴"
        if temp <= 0:
            return "气温在冰点以下，注意保暖，外出穿厚外套！❄️"
        if temp <= 5:
            return "天气较冷，记得添衣保暖！🧥"

        # 能见度
        if any(k in desc_lower for k in ("雾", "fog", "mist", "haze", "霾")):
            return "能见度低，开车注意安全，建议戴口罩出行。😷"

        # 晴天紫外线
        if any(k in desc_lower for k in ("晴", "clear", "sunny")):
            if temp > 25:
                return "天气晴好，紫外线可能较强，注意防晒！☀️"
            return "天气不错，适合外出活动！🌤️"

        # 多云
        if any(k in desc_lower for k in ("云", "cloud", "overcast", "阴")):
            return "多云天气，适合散步，不会太晒也不会太冷。🙂"

        # 湿度
        if humidity >= 85:
            return "湿度较高，注意防潮，衣物可能不容易干。💧"

        # 默认
        return "出门看看今天的风景吧！🌈"

    # ── 降级结果 ──────────────────────────────────

    @staticmethod
    def _fallback(error_msg: str) -> dict:
        return {
            "city": "未知",
            "temp": 0,
            "feels_like": 0,
            "humidity": 0,
            "description": "获取失败",
            "advice": "无法获取天气信息，请检查网络和 API Key。",
            "error": error_msg,
        }
