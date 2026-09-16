"""
示例插件：今日课程查询
演示插件如何复用主程序的数据库与业务服务，输出课程表信息。

用法：
    /课程
    /course

设计说明：
插件在 QApplication 之前被加载，因此 setup() 里只注册命令、不建连接、
不创建 QTimer；课程数据在命令真正执行时才通过共享的 DBManager 读取
（DBManager 每次操作自建连接，所以插件与主程序共用同一份数据库文件即可）。
"""
from __future__ import annotations

from plugin_manager import EventBus, PluginBase


class CoursePlugin(PluginBase):
    """今日课程查询插件"""

    name = "课程表"
    version = "1.0.0"
    description = "查看今日课程（数据来自设置页「📅 课程表」）"

    def __init__(self, bus: EventBus):
        super().__init__(bus)

    def setup(self):
        """注册命令（此时 QApplication 可能还没创建，不要碰 Qt 对象）"""
        self.register_command(
            name="课程",
            description="查看今日课程，用法: /课程",
            handler=self.handle_courses,
        )
        self.register_command(
            name="course",
            description="Show today's courses, usage: /course",
            handler=self.handle_courses,
        )

    def handle_courses(self, args: dict) -> str:
        """处理 /课程 命令"""
        # 延迟导入：避免插件加载阶段就依赖服务层模块
        from course_service import CourseService

        if getattr(self, "db", None) is None:
            return "⚠️ 课程表暂时不可用（插件未拿到数据库）"

        service = CourseService(self.db)
        text = service.day_text()
        if not service.is_enabled():
            text += "\n\n（提醒总开关已关闭，可在设置页重新开启）"
        return text

    def teardown(self):
        """清理资源（本插件没有需要释放的资源）"""
        pass
