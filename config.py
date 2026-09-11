"""
全局配置模块
UI 等固定参数在此定义，用户可调参数已迁移至本地数据库（db_manager.py）。
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
