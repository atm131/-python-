"""
天气服务模块
使用 wttr.in 免费开源天气 API，无需 API Key。
https://github.com/chubin/wttr.in
"""
from __future__ import annotations

import json
import re
import requests

from db_manager import DBManager


class WeatherService:
    """
    天气查询服务。

    使用 wttr.in 免费 API（无需 API Key）：
    https://wttr.in/{city}?format=j1

    也支持通过 ip-api.com 自动定位城市。
    """

    # wttr.in JSON API（完全免费，无需注册）
    _WTTR_API = "https://wttr.in/{city}?format=j1&lang=zh"
    # 请求头：部分接口会拒绝默认的 python-requests UA
    _HEADERS = {"User-Agent": "SmartDesktopPet/3.0", "Accept-Language": "zh-CN"}
    # IP 地理定位 API 列表
    # 顺序按实测可靠性排列：ipinfo.io 最稳定；
    # ip-api.com 走 HTTP 80 端口、ipapi.co 有限流、ip.seeip.org 连接不稳定，
    # 均作为兜底候选，任何一个成功即返回。
    _GEO_APIS = [
        {"url": "https://ipinfo.io/json", "timeout": 3},
        {"url": "http://ip-api.com/json/?lang=zh-CN&fields=status,country,city", "timeout": 3},
        {"url": "https://ip.seeip.org/jsonip?", "timeout": 3},
        {"url": "https://ipapi.co/json/", "timeout": 3},
    ]

    def __init__(self, db: DBManager):
        self.db = db
        self._auto_city: dict | None = None  # {"cn": "成都", "en": "Chengdu"}

    @property
    def city(self) -> str:
        """从数据库读取城市设置（英文，用于 API 查询）"""
        return self.db.get("city", "")

    # 中文城市名映射（ip-api 返回中文，wttr.in 需要英文）
    _CITY_CN_TO_EN = {
        "成都": "Chengdu", "北京": "Beijing", "上海": "Shanghai",
        "广州": "Guangzhou", "深圳": "Shenzhen", "杭州": "Hangzhou",
        "武汉": "Wuhan", "南京": "Nanjing", "重庆": "Chongqing",
        "西安": "Xian", "天津": "Tianjin", "苏州": "Suzhou",
        "郑州": "Zhengzhou", "长沙": "Changsha", "东莞": "Dongguan",
        "沈阳": "Shenyang", "青岛": "Qingdao", "合肥": "Hefei",
        "佛山": "Foshan", "宁波": "Ningbo", "昆明": "Kunming",
        "大连": "Dalian", "福州": "Fuzhou", "厦门": "Xiamen",
        "哈尔滨": "Harbin", "济南": "Jinan", "温州": "Wenzhou",
        "南宁": "Nanning", "长春": "Changchun", "泉州": "Quanzhou",
        "石家庄": "Shijiazhuang", "贵阳": "Guiyang", "南昌": "Nanchang",
        "太原": "Taiyuan", "烟台": "Yantai", "嘉兴": "Jiaxing",
        "珠海": "Zhuhai", "惠州": "Huizhou", "徐州": "Xuzhou",
        "海口": "Haikou", "乌鲁木齐": "Urumqi", "中山": "Zhongshan",
        "兰州": "Lanzhou", "台州": "Taizhou", "桂林": "Guilin",
    }

    @staticmethod
    def detect_city() -> dict:
        """
        通过 IP 自动定位当前城市。
        依次尝试多个 API，返回 {"cn": "成都", "en": "Chengdu"}
        """
        for i, api in enumerate(WeatherService._GEO_APIS):
            try:
                resp = requests.get(api["url"], timeout=api["timeout"],
                                    headers=WeatherService._HEADERS)
                resp.raise_for_status()
                data = resp.json()

                # ip-api.com 格式（返回中文城市名）
                if data.get("status") == "success":
                    city_cn = data.get("city", "")
                    if city_cn:
                        print(f"[Weather] IP 定位成功（API{i+1}）: {city_cn}")
                        city_en = WeatherService._CITY_CN_TO_EN.get(city_cn, city_cn)
                        return {"cn": city_cn, "en": city_en}

                # ipinfo.io / ipapi.co 格式
                city_en = data.get("city", "")
                if city_en:
                    # 反查中文名
                    city_cn = city_en
                    for cn, en in WeatherService._CITY_CN_TO_EN.items():
                        if en.lower() == city_en.lower():
                            city_cn = cn
                            break
                    print(f"[Weather] IP 定位成功（API{i+1}）: {city_cn}")
                    return {"cn": city_cn, "en": city_en}

            except Exception as e:
                print(f"[Weather] API{i+1} 定位失败: {e}")
                continue

        return {"cn": "", "en": ""}

    def _resolve_city(self) -> dict:
        """
        获取城市信息：优先数据库设置，否则自动定位。
        返回 {"cn": "成都", "en": "Chengdu"}
        """
        if self.city:
            # 反查：用户可能手动输入中文或英文城市名
            for cn, en in self._CITY_CN_TO_EN.items():
                if en.lower() == self.city.lower() or cn == self.city:
                    return {"cn": cn, "en": en}
            return {"cn": self.city, "en": self.city}

        if self._auto_city is None:
            self._auto_city = self.detect_city()

        if self._auto_city and self._auto_city.get("en"):
            return self._auto_city
        return {"cn": "北京", "en": "Beijing"}

    def fetch(self) -> dict:
        """
        请求 wttr.in 天气 API，返回解析后的结果字典。

        返回结构：
        {
            "city":       str,   # 中文城市名
            "temp":       float,
            "feels_like": float,
            "humidity":   int,
            "description": str,  # 中文天气描述
            "advice":     str,
            "error":      str | None
        }
        """
        city_info = self._resolve_city()
        city_en = city_info["en"]
        city_cn = city_info["cn"]

        if not city_en:
            return self._fallback("无法获取城市信息，请检查网络或手动配置城市。")

        try:
            url = self._WTTR_API.format(city=city_en)
            resp = requests.get(url, timeout=10, headers=self._HEADERS)
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current_condition", [{}])[0]
            temp = float(current.get("temp_C", 0))
            feels_like = float(current.get("FeelsLikeC", 0))
            humidity = int(current.get("humidity", 0))

            # 获取天气描述并翻译为中文
            raw_desc = ""
            # 尝试 lang_zh
            desc_zh = current.get("lang_zh", [])
            if isinstance(desc_zh, list) and desc_zh:
                raw_desc = desc_zh[0].get("value", "").strip()
            # 如果 lang_zh 为空，用 weatherDesc
            if not raw_desc:
                desc_en = current.get("weatherDesc", [{}])
                if isinstance(desc_en, list) and desc_en:
                    raw_desc = desc_en[0].get("value", "").strip()
            # 翻译为中文（wttr.in 的 lang_zh 经常返回英文）
            description = self._translate_weather_desc(raw_desc) if raw_desc else "未知"

            advice = self._generate_advice(temp, description, humidity)

            return {
                "city": city_cn,
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

    @staticmethod
    def _translate_weather_desc(en_desc: str) -> str:
        """简单英译中天气描述（长匹配优先）"""
        desc = en_desc.strip()
        # 按长度降序排列，确保更具体的描述优先匹配
        mapping = [
            ("Torrential rain shower", "暴雨"),
            ("Moderate or heavy rain shower", "大阵雨"),
            ("Thundery outbreaks possible", "可能有雷阵雨"),
            ("Patchy rain possible", "可能有零星小雨"),
            ("Patchy rain nearby", "附近有零星小雨"),
            ("Light rain shower", "阵雨"),
            ("Heavy rain", "大雨"),
            ("Moderate rain", "中雨"),
            ("Light drizzle", "毛毛雨"),
            ("Light rain", "小雨"),
            ("Heavy snow", "大雪"),
            ("Moderate snow", "中雪"),
            ("Light snow", "小雪"),
            ("Partly cloudy", "多云"),
            ("Thunderstorm", "雷暴"),
            ("Blizzard", "暴风雪"),
            ("Overcast", "阴天"),
            ("Cloudy", "多云"),
            ("Sunny", "晴天"),
            ("Clear", "晴朗"),
            ("Mist", "薄雾"),
            ("Fog", "雾"),
            ("Haze", "霾"),
        ]
        for en, zh in mapping:
            if en.lower() in desc.lower():
                return zh
        return desc

    # ── 出行建议生成 ──────────────────────────────

    @staticmethod
    def _generate_advice(temp: float, desc: str, humidity: int) -> str:
        """根据天气状况生成出行建议"""
        desc_lower = desc.lower()

        if any(k in desc_lower for k in ("雨", "rain", "shower", "drizzle")):
            return "今天有雨，记得带伞哦！☂️"
        if any(k in desc_lower for k in ("雪", "snow", "sleet")):
            return "下雪了，路面湿滑，注意保暖！🧣"
        if any(k in desc_lower for k in ("雷", "thunder", "storm")):
            return "雷暴天气，尽量待在室内！⚡"
        if temp >= 38:
            return "高温预警！注意防暑降温！🥵"
        if temp >= 33:
            return "天气炎热，多喝水，注意防晒！🧴"
        if temp <= 0:
            return "气温在冰点以下，注意保暖！❄️"
        if temp <= 5:
            return "天气较冷，记得添衣保暖！🧥"
        if any(k in desc_lower for k in ("雾", "fog", "mist", "haze", "霾")):
            return "能见度低，注意安全，建议戴口罩。😷"
        if any(k in desc_lower for k in ("晴", "clear", "sunny")):
            return "天气晴好，适合外出活动！☀️" if temp > 25 else "天气不错！🌤️"
        if any(k in desc_lower for k in ("云", "cloud", "overcast", "阴")):
            return "多云天气，适合散步。🙂"
        if humidity >= 85:
            return "湿度较高，注意防潮。💧"
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
            "advice": "无法获取天气信息，请检查网络。",
            "error": error_msg,
        }
