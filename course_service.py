"""
课程表服务模块
职责：
1. CourseService —— 课程表的持久化（序列化成 JSON 存进 DBManager 的 settings 表）、
   字段校验与规范化、以及「当前时刻该提醒哪些课」的判断。
2. CourseReminder —— GUI 线程内的定时调度器（QTimer 每分钟检查一次），
   到点通过事件总线让桌宠弹气泡。

为什么这样分层：
课程表的所有业务判断（时间窗、跨零点、去重）都做成不依赖 Qt 的纯逻辑，
只有「隔多久检查一次」这一件事交给 QTimer。这样 test_logic.py 可以用固定的
datetime 直接单测全部规则，不必启动 GUI，也不会因为系统时间而时好时坏。

数据格式（key = course_schedule，值为 JSON 字符串）：
[
  {
    "name": "高等数学",        # 课程名，不能为空
    "weekday": 1,              # 1=周一 … 7=周日（ISO 标准，对应 date.isoweekday()）
    "start": "08:00",          # 24 小时制 HH:MM
    "end": "09:40",
    "room": "教三-201",        # 可为空
    "remind_before": 10,       # 提前提醒分钟数，0~120
    "enabled": true            # 该门课是否参与提醒
  }
]
另有 key = course_reminder_enabled（"1"/"0"）作为总开关，默认开启。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from PyQt6.QtCore import QObject, QTimer

from db_manager import DBManager
from plugin_manager import EventBus


# ─── 数据库 key ────────────────────────────────────────────

KEY_SCHEDULE = "course_schedule"           # 课程表 JSON
KEY_ENABLED = "course_reminder_enabled"    # 总开关，"1" 开 / "0" 关

# ─── 规则常量 ──────────────────────────────────────────────

DEFAULT_REMIND_BEFORE = 10   # 默认提前 10 分钟
MAX_REMIND_BEFORE = 120      # 提前量上限，避免误填出「提前 8 小时提醒」这种数据
BUBBLE_DURATION_MS = 15000   # 提醒气泡显示时长

WEEKDAY_NAMES: dict[int, str] = {
    1: "周一", 2: "周二", 3: "周三", 4: "周四",
    5: "周五", 6: "周六", 7: "周日",
}

# 中文星期 → 数字（含"星期一"写法），用于容忍手工编辑数据库的情况
_WEEKDAY_ALIASES: dict[str, int] = {}
for _num, _name in WEEKDAY_NAMES.items():
    _WEEKDAY_ALIASES[_name] = _num                  # 周一
    _WEEKDAY_ALIASES[_name.replace("周", "星期")] = _num   # 星期一
    _WEEKDAY_ALIASES[str(_num)] = _num              # "1"

# 全角字符 → 半角：用户很可能用中文输入法敲出「8：00」，直接报错体验很差
_FULLWIDTH_TABLE = str.maketrans({
    "：": ":", "．": ".", "　": " ",
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
})

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})$")


# ─── 课程服务 ──────────────────────────────────────────────

class CourseService:
    """
    课程表的读写与业务判断。

    完全不依赖 Qt，也不自己建数据库连接 —— 所有持久化都走传入的 DBManager，
    因此可以在非 GUI 环境（单元测试、脚本）里直接实例化使用。
    """

    def __init__(self, db: DBManager):
        self.db = db

    # ── 读写 ────────────────────────────────────────

    def load_courses(self) -> list[dict]:
        """
        从数据库读取并解析课程表。

        JSON 损坏、顶层不是数组、或存在字段非法的记录时统一返回空表并打印警告，
        绝不抛异常 —— 这个函数会被每分钟的定时检查和右键菜单调用，
        一旦抛异常就会变成周期性报错。数据被外部改坏时"当作没有课"比"提醒半个错课表"
        更可预期，用户改完设置页保存即会写回一份规范数据。
        """
        raw = self.db.get(KEY_SCHEDULE, "")
        if not raw or not raw.strip():
            return []

        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as e:
            print(f"[Course] ⚠️ 课程表 JSON 解析失败，按空课程表处理: {e}")
            return []

        if not isinstance(data, list):
            print(f"[Course] ⚠️ 课程表数据格式异常（应为数组，实际为 {type(data).__name__}），按空课程表处理")
            return []

        courses: list[dict] = []
        for index, item in enumerate(data):
            course, msg = self.normalize_course(item)
            if course is None:
                print(f"[Course] ⚠️ 课程表第 {index + 1} 条记录非法（{msg}），按空课程表处理")
                return []
            courses.append(course)
        return courses

    def save_courses(self, courses: list[dict]) -> None:
        """
        校验并规范化后写回数据库。

        非法记录直接跳过（设置页保存前已逐行校验并拦截，走到这里说明是代码调用），
        避免一条脏数据把整个课程表写坏。
        """
        normalized: list[dict] = []
        for index, raw in enumerate(courses or []):
            course, msg = self.normalize_course(raw)
            if course is None:
                print(f"[Course] ⚠️ 保存时跳过第 {index + 1} 条非法课程: {msg}")
                continue
            normalized.append(course)

        # ensure_ascii=False：中文课程名直接以 UTF-8 存储，数据库里可读、便于排查
        self.db.set(KEY_SCHEDULE, json.dumps(normalized, ensure_ascii=False))

    def is_enabled(self) -> bool:
        """总开关是否开启（键不存在时默认开启）"""
        text = self.db.get(KEY_ENABLED, "1").strip().lower()
        return text not in ("0", "false", "no", "off")

    def set_enabled(self, enabled: bool) -> None:
        """写入总开关（值只能是字符串 "1"/"0"）"""
        self.db.set(KEY_ENABLED, "1" if enabled else "0")

    # ── 校验与规范化 ────────────────────────────────

    @staticmethod
    def normalize_course(raw: dict) -> tuple[dict | None, str]:
        """
        规范化单条课程。

        返回 (规范化后的课程, "") 表示通过；返回 (None, 错误说明) 表示非法。
        设置页直接把这个错误说明展示给用户，所以文案要指出"错在哪"。
        """
        if not isinstance(raw, dict):
            return None, "课程记录格式不正确（应为字典）"

        name = str(raw.get("name", "") or "").strip()
        if not name:
            return None, "课程名不能为空"

        weekday = CourseService._normalize_weekday(raw.get("weekday"))
        if weekday is None:
            return None, f"星期必须是 1~7（或周一~周日），当前为「{raw.get('weekday')}」"

        start, msg = CourseService._normalize_time(raw.get("start"), "开始时间")
        if start is None:
            return None, msg
        end, msg = CourseService._normalize_time(raw.get("end"), "结束时间")
        if end is None:
            return None, msg

        # 字符串比较即可：两边都已是等宽补零的 "HH:MM"，字典序与时间先后一致
        if start >= end:
            return None, f"开始时间（{start}）必须早于结束时间（{end}）"

        remind_before = CourseService._normalize_remind(raw.get("remind_before"))
        if remind_before is None:
            return None, (f"提前提醒必须是 0~{MAX_REMIND_BEFORE} 的整数分钟，"
                          f"当前为「{raw.get('remind_before')}」")

        return {
            "name": name,
            "weekday": weekday,
            "start": start,
            "end": end,
            "room": str(raw.get("room", "") or "").strip(),
            "remind_before": remind_before,
            "enabled": CourseService._normalize_bool(raw.get("enabled", True), True),
        }, ""

    @staticmethod
    def _normalize_time(value, label: str) -> tuple[str | None, str]:
        """
        把各种写法的时间统一成 "HH:MM"。

        容错："8:00" / "8：00" / "08:00" 都能接受；"25:00"、"8:70"、"abc" 返回错误。
        """
        text = "" if value is None else str(value).strip().translate(_FULLWIDTH_TABLE)
        if not text:
            return None, f"{label}不能为空"

        match = _TIME_RE.match(text)
        if not match:
            return None, f"{label}格式不正确，应写成 HH:MM（如 08:00），当前为「{value}」"

        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None, f"{label}不是合法时间（小时 0~23、分钟 0~59），当前为「{value}」"
        return f"{hour:02d}:{minute:02d}", ""

    @staticmethod
    def _normalize_weekday(value) -> int | None:
        """星期容错解析：接受 1~7、周一~周日、星期一~星期日"""
        if isinstance(value, str):
            text = value.strip()
            if text in _WEEKDAY_ALIASES:
                return _WEEKDAY_ALIASES[text]
            try:
                value = int(text)
            except ValueError:
                return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if 1 <= number <= 7 else None

    @staticmethod
    def _normalize_remind(value) -> int | None:
        """提前提醒分钟数：缺省 10，必须是 0~120 的整数"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_REMIND_BEFORE
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        # 10.5 这类小数直接拒绝：提醒点会落在分钟之间，用户多半是填错了
        if number != int(number):
            return None
        number = int(number)
        return number if 0 <= number <= MAX_REMIND_BEFORE else None

    @staticmethod
    def _normalize_bool(value, default: bool) -> bool:
        """布尔容错解析：数据库里可能是 true / "1" / "是" 等写法"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on", "是", "开", "启用"):
            return True
        if text in ("0", "false", "no", "off", "否", "关", "禁用"):
            return False
        return default

    # ── 提醒判断（纯逻辑） ──────────────────────────

    def due_reminders(self, now: datetime, seen: set[str] | None = None) -> list[dict]:
        """
        返回 now 时刻需要提醒的课程列表（每项附带 minutes_left）。

        规则：该门课 enabled、总开关开启、0 < (开课时间 - now) <= remind_before 分钟。
        用完整 datetime 相减算差值，不能只比 hour/minute —— 否则凌晨的课
        （周三 00:05 在周二 23:55 就该提醒）会被判成"已过去"。

        seen：可选去重集合。传入时会剔除本次之前已提醒过的课，并把本次返回的
        提醒写入其中（同一门课同一天只提醒一次）。集合里的键带的是「上课那一天」
        的日期，跨天时旧键自动失效，因此程序在提醒窗口中途启动、或提醒跨零点
        都不会重复弹窗。
        """
        if not self.is_enabled():
            return []

        courses = self.load_courses()
        if not courses:
            return []

        if seen is not None:
            self._prune_seen(seen, now.date())

        result: list[dict] = []
        for course in courses:
            if not course["enabled"]:
                continue
            start_time = self._parse_time(course["start"])
            if start_time is None:
                continue

            # 跨零点：开课时刻可能落在"今天"也可能落在"明天"，
            # 两个候选日期都算一遍，谁的星期匹配就用谁
            for day_offset in (0, 1):
                class_date = now.date() + timedelta(days=day_offset)
                if class_date.isoweekday() != course["weekday"]:
                    continue

                start_dt = datetime.combine(class_date, start_time)
                minutes_left = (start_dt - now).total_seconds() / 60.0
                if not 0 < minutes_left <= course["remind_before"]:
                    continue

                key = self._dedup_key(class_date, course)
                if seen is not None:
                    if key in seen:
                        break
                    seen.add(key)

                item = dict(course)
                item["minutes_left"] = int(round(minutes_left))
                item["class_date"] = class_date.isoformat()
                result.append(item)
                break

        return result

    @staticmethod
    def _parse_time(text: str) -> time | None:
        """把 "HH:MM" 解析成 time 对象（数据已规范化，这里只做防御性兜底）"""
        match = _TIME_RE.match(str(text).strip())
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return time(hour, minute)

    @staticmethod
    def _dedup_key(class_date: date, course: dict) -> str:
        """去重键：日期 + 课程名 + 开始时间（同一门课同一天只提醒一次）"""
        return f"{class_date.isoformat()}-{course['name']}-{course['start']}"

    @staticmethod
    def _prune_seen(seen: set[str], today: date) -> None:
        """
        丢弃比今天更早的去重键。

        键里带的是上课日期，今天之前的课已经上完、不可能再提醒；保留明天的键
        是因为跨零点的课（今天 23:55 提醒明天的 00:05）会在今天写入明天的键。
        """
        for key in [k for k in seen if CourseService._key_date(k) < today]:
            seen.discard(key)

    @staticmethod
    def _key_date(key: str) -> date:
        """从去重键中取回上课日期（键以 ISO 日期开头，共 10 个字符）"""
        try:
            return date.fromisoformat(key[:10])
        except ValueError:
            return date.min   # 认不出的键当作很久以前，交给 _prune_seen 清掉

    # ── 文案 ────────────────────────────────────────

    @staticmethod
    def format_reminder(course: dict) -> str:
        """
        生成提醒气泡文案：

            📚 还有 10 分钟上课
            高等数学 · 08:00-09:40
            📍 教三-201
        """
        minutes_left = int(course.get("minutes_left", 0))
        head = "📚 该上课了" if minutes_left <= 0 else f"📚 还有 {minutes_left} 分钟上课"

        lines = [head, f"{course.get('name', '')} · {course.get('start', '')}-{course.get('end', '')}"]
        room = str(course.get("room", "") or "").strip()
        if room:
            lines.append(f"📍 {room}")
        return "\n".join(lines)

    def courses_of_day(self, day: date | None = None) -> list[dict]:
        """返回某一天（默认今天）的课程，按开始时间排序"""
        target = day or date.today()
        courses = [c for c in self.load_courses()
                   if c["weekday"] == target.isoweekday() and c["enabled"]]
        return sorted(courses, key=lambda c: c["start"])

    def day_text(self, day: date | None = None) -> str:
        """
        生成「今日课程」文本（右键菜单 / 插件共用）：

            有课：📅 今天有 3 节课
                  08:00 高等数学（教三-201）
            无课：📅 今天没有课，好好休息～
        """
        target = day or date.today()
        courses = self.courses_of_day(target)

        if not courses:
            return "📅 今天没有课，好好休息～"

        lines = [f"📅 今天有 {len(courses)} 节课"]
        for course in courses:
            room = course.get("room", "")
            suffix = f"（{room}）" if room else ""
            lines.append(f"{course['start']} {course['name']}{suffix}")
        return "\n".join(lines)


# ─── 提醒调度 ──────────────────────────────────────────────

class CourseReminder(QObject):
    """
    课程提醒调度器：每分钟检查一次课程表，到点前通过事件总线让宠物弹气泡。

    为什么用 QTimer 而不是线程：
    本功能没有网络请求，检查逻辑是纯计算，开销可忽略；QTimer 跑在 GUI 线程里，
    可以直接走事件总线让 UI 显示气泡。反过来，若放在纯 threading.Thread 里，
    Qt 定时器根本不会触发（本项目已踩过这个坑）。

    必须由 main.py 在 QApplication 创建之后实例化 —— 插件加载早于 QApplication，
    在那里创建 QTimer 是不安全的。
    """

    CHECK_INTERVAL_MS = 60 * 1000   # 每分钟检查一次

    def __init__(self, db: DBManager, bus: EventBus, parent=None):
        super().__init__(parent)
        self.db = db
        self.bus = bus
        self.service = CourseService(db)

        # 已提醒过的课（去重），跨天自动清理，见 CourseService.due_reminders
        self._seen: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self.check_now)

    def start(self) -> None:
        """启动定时检查，并立刻检查一遍（程序可能正好在提醒窗口内启动）"""
        self._timer.start()
        self.check_now()
        print(f"[Course] 课程提醒已启动（每 {self.CHECK_INTERVAL_MS // 1000} 秒检查一次）")

    def stop(self) -> None:
        """停止定时检查"""
        self._timer.stop()

    @property
    def running(self) -> bool:
        """是否正在定时检查"""
        return self._timer.isActive()

    def check_now(self, now: datetime | None = None) -> list[dict]:
        """
        执行一次检查，返回本次触发的课程（便于测试直接驱动）。

        每次 tick 都重新从数据库读课程表，用户在设置页改完保存后，
        下一次 tick（≤60 秒）即生效，无需重启程序。
        """
        now = now or datetime.now()
        try:
            due = self.service.due_reminders(now, self._seen)
        except Exception as e:
            # 定时任务抛异常会一路冒到 Qt 事件循环，这里兜住，避免打断提醒服务
            print(f"[Course] ⚠️ 课程检查失败: {e}")
            return []

        for course in due:
            self.bus.emit("pet.show_bubble", {
                "text": CourseService.format_reminder(course),
                "duration": BUBBLE_DURATION_MS,
            })
            # 用 greet（举手打招呼）而不是 alert：提醒上课是友好提示，不是告警
            self.bus.emit("pet.state", {"state": "greet", "revert_after_ms": 8000})
            print(f"[Course] 📚 提醒: {course['name']} {course['start']}（还有 {course['minutes_left']} 分钟）")
        return due
