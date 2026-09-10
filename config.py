"""
全局配置模块
集中管理所有可调参数，单一数据源，其他模块通过 AppConfig 访问。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PetConfig:
    """宠物行为与外观参数"""

    name: str = "小智"
    # 窗口尺寸
    width: int = 200
    height: int = 200
    # 宠物图片路径（相对于项目根目录，或绝对路径）
    image_path: str = r"E:\毕业设计\shuchaiku\nv.png"


@dataclass(frozen=True)
class WeatherConfig:
    """天气查询参数"""

    # ───────────────────────────────────────────────────
    # 请在此处填写你的 OpenWeatherMap API Key
    # 免费注册：https://openweathermap.org/api
    # ───────────────────────────────────────────────────
    api_key: str = os.getenv("OWM_API_KEY", "")
    city: str = ""                # 留空则自动通过 IP 定位获取城市
    lang: str = "zh_cn"           # 返回语言


@dataclass(frozen=True)
class MonitorConfig:
    """系统监控参数"""

    interval_sec: float = 2.0          # 采集间隔(秒)
    cpu_high_threshold: float = 80.0   # CPU 高负载阈值
    mem_high_threshold: float = 85.0   # 内存高负载阈值
    history_maxlen: int = 300          # 历史记录最大条数


@dataclass(frozen=True)
class RAGConfig:
    """本地 RAG 知识库参数"""

    db_path: str = "knowledge_db"
    embedding_model: str = "all-MiniLM-L6-v2"   # sentence-transformers 模型名
    chunk_size: int = 500
    chunk_overlap: int = 80
    top_k: int = 5
    score_threshold: float = 0.3


@dataclass(frozen=True)
class LLMConfig:
    """大语言模型 API 参数"""

    api_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = "Qwen/Qwen3-8B"
    max_tokens: int = 2048
    temperature: float = 0.7
    system_prompt: str = (
        "你是一个可爱的 Windows 桌面宠物助手，名字叫小智。"
        "回答简洁、友好、有趣。当系统负载高时，请关心用户并给出优化建议。"
    )


@dataclass(frozen=True)
class UIConfig:
    """界面视觉参数"""

    font_family: str = "Microsoft YaHei UI"
    # 对话气泡
    bubble_bg: str = "rgba(30, 30, 30, 220)"
    bubble_fg: str = "#e0e0e0"
    bubble_radius: int = 12
    bubble_max_width: int = 320
    bubble_margin: int = 10
    # 状态指示器
    status_colors: dict = field(default_factory=lambda: {
        "idle":     "#00d4aa",
        "thinking": "#ffe66d",
        "busy":     "#ff6b6b",
        "tired":    "#ff9f43",
        "happy":    "#4ecdc4",
    })


@dataclass(frozen=True)
class AppConfig:
    """顶层配置容器，聚合所有子配置"""

    pet: PetConfig = field(default_factory=PetConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # 窗口初始位置（可选，None 则自动定位到屏幕右下角）
    window: dict = field(default_factory=lambda: {"init_x": None, "init_y": None})

    # 插件目录
    plugins_dir: str = "plugins"
    # 数据库
    db_path: str = "assistant.db"
    # 日志级别
    log_level: str = "INFO"
