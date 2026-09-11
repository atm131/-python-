"""
全局配置模块

集中定义各模块的固定参数，避免散落在业务代码里。
用户可调参数（城市、API Key、宠物位置等）存放在本地数据库（db_manager.py）。

配置类一览：
- UIConfig      : 界面视觉参数（气泡、字体、状态色）
- PetConfig     : 宠物主体参数（尺寸、动画、巡逻）
- MonitorConfig : 系统监控参数（采集间隔、阈值、历史长度）
- RAGConfig     : 知识库参数（分块、检索、向量库路径）
- LLMConfig     : 大模型调用参数（地址、模型、采样）
- AppConfig     : 聚合配置，供 UI 模块一次性传入
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UIConfig:
    """界面视觉参数（固定值，不随用户设置变化）"""

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
class PetConfig:
    """宠物主体参数（尺寸、动画帧率、巡逻速度）"""

    width: int = 200
    height: int = 200
    anim_frame_ms: int = 120          # 动画帧间隔
    patrol_interval_ms: int = 60      # 巡逻步进间隔
    patrol_speed: float = 1.5         # 每步移动像素
    screen_margin: int = 20           # 巡逻时距屏幕边缘的留白


@dataclass(frozen=True)
class MonitorConfig:
    """系统监控参数"""

    interval_sec: float = 3.0         # 采集间隔（秒）
    history_maxlen: int = 120         # 历史快照保留条数
    cpu_high_threshold: float = 85.0  # CPU 高负载阈值（%）
    mem_high_threshold: float = 90.0  # 内存高负载阈值（%）


@dataclass(frozen=True)
class RAGConfig:
    """本地知识库 / 向量检索参数"""

    db_path: str = "knowledge_db"                       # 向量库存储目录
    embedding_model: str = "shibing624/text2vec-base-chinese"
    chunk_size: int = 300             # 文本分块长度（字符）
    chunk_overlap: int = 50           # 相邻块重叠长度
    top_k: int = 3                    # 检索返回条数
    score_threshold: float = 0.5      # 相似度阈值，低于此值不注入上下文


@dataclass(frozen=True)
class LLMConfig:
    """大语言模型调用参数（OpenAI 兼容接口）"""

    api_url: str = "https://api.deepseek.com/v1/chat/completions"
    api_key: str = ""
    model: str = "deepseek-chat"
    system_prompt: str = (
        "你是桌面宠物助手，一个运行在用户电脑上的贴心小助手。"
        "回答要简洁、友好，优先使用中文。"
    )
    max_tokens: int = 1024
    temperature: float = 0.7


@dataclass(frozen=True)
class AppConfig:
    """
    聚合配置：供 DesktopPet 等模块一次性传入。

    用法：
        config = AppConfig()
        pet = DesktopPet(config, bus)
    """

    pet: PetConfig = field(default_factory=PetConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
