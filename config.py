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
    # 巡逻参数
    patrol_speed: float = 1.5          # 像素/帧
    patrol_interval_ms: int = 30       # 帧间隔(ms)
    screen_margin: int = 20            # 距屏幕边缘最小距离
    # 动画帧间隔
    anim_frame_ms: int = 500           # 状态动画切换间隔


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
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # 插件目录
    plugins_dir: str = "plugins"
    # 数据库
    db_path: str = "assistant.db"
    # 日志级别
    log_level: str = "INFO"
