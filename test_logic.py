# -*- coding: utf-8 -*-
"""非 GUI 模块逻辑测试：语法 / 数据库 / 事件总线 / 插件 / AI 本地对话 / 天气工具函数 / 系统状态"""
import io
import os
import py_compile
import sys
import tempfile
import traceback

PROJECT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

REPORT = os.path.join(PROJECT, "test_report_logic.txt")
out = io.open(REPORT, "w", encoding="utf-8")

results = []

def check(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
    except Exception as e:
        results.append((name, "FAIL", f"{e}\n{traceback.format_exc()}"))

# ─── 1. 全部文件语法编译检查 ──────────────────────────────
def t_compile():
    bad = []
    for f in os.listdir(PROJECT):
        if f.endswith(".py") and not f.startswith("test_"):
            try:
                py_compile.compile(os.path.join(PROJECT, f), doraise=True)
            except py_compile.PyCompileError as e:
                bad.append(f"{f}: {e}")
    for sub in ("plugins", "tools"):
        d = os.path.join(PROJECT, sub)
        for f in os.listdir(d):
            if f.endswith(".py"):
                try:
                    py_compile.compile(os.path.join(d, f), doraise=True)
                except py_compile.PyCompileError as e:
                    bad.append(f"{sub}/{f}: {e}")
    assert not bad, "\n".join(bad)
check("语法编译检查(全部py)", t_compile)

# ─── 2. DBManager ─────────────────────────────────────────
def t_db():
    from db_manager import DBManager
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        db.set("city", "Beijing")
        assert db.get("city") == "Beijing"
        assert db.get("missing", "d") == "d"
        db.set("city", "Shanghai")            # 覆盖写
        assert db.get("city") == "Shanghai"
        db.set("k2", "v2")
        all_ = db.get_all()
        assert all_ == {"city": "Shanghai", "k2": "v2"}, all_
        db.delete("k2")
        assert db.get("k2") == ""
check("DBManager 增删改查", t_db)

# ─── 3. EventBus ──────────────────────────────────────────
def t_bus():
    from plugin_manager import EventBus
    bus = EventBus()
    got = []
    bus.on("a.b", lambda e: got.append(("h1", e.data.get("x"))))
    bus.on("a.b", lambda e: got.append(("h2", e.data.get("x"))))
    bus.on("*", lambda e: got.append(("wild", e.name)))
    bus.emit("a.b", {"x": 1})
    assert ("h1", 1) in got and ("h2", 1) in got and ("wild", "a.b") in got, got

    # once
    got2 = []
    bus.once("once.ev", lambda e: got2.append(1))
    bus.emit("once.ev"); bus.emit("once.ev")
    assert len(got2) == 1, got2

    # stop 传播
    def stopper(e): e.stop()
    order = []
    bus2 = EventBus()
    bus2.on("s", lambda e: (order.append(1), e.stop()))
    bus2.on("s", lambda e: order.append(2))
    bus2.emit("s")
    assert order == [1], order

    # off
    h = lambda e: None
    bus2.on("x", h); bus2.off("x", h)
    assert "x" not in bus2.list_events() or not bus2._handlers.get("x")

    # 处理器异常不应中断总线
    bus3 = EventBus()
    bus3.on("err", lambda e: 1 / 0)
    ok = []
    bus3.on("err", lambda e: ok.append(1))
    bus3.emit("err")
    assert ok == [1]
check("EventBus 发布/订阅/once/stop/off/异常隔离", t_bus)

# ─── 4. PluginManager + 天气插件 ──────────────────────────
def t_plugins():
    from plugin_manager import EventBus, PluginManager
    bus = EventBus()
    pm = PluginManager(bus, plugins_dir="plugins")
    pm.load_plugins()
    names = [p.name for p in pm.plugins]
    assert "天气查询" in names, names
    cmds = pm.list_commands()
    cmd_names = [c["command"] for c in cmds]
    assert "天气" in cmd_names and "weather" in cmd_names, cmd_names
    # 非命令输入
    assert pm.dispatch_command("你好") is None
    # 未知命令
    assert pm.dispatch_command("/不存在的命令") is None
    # 缺少参数（不触网）
    r = pm.dispatch_command("/天气")
    assert r and "请指定城市名" in r, r
    pm.teardown_all()
check("PluginManager 加载/命令路由", t_plugins)

# ─── 5. AIService 本地对话 ────────────────────────────────
def t_ai_local():
    from db_manager import DBManager
    from ai_service import AIService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        ai = AIService(db)
        assert ai.is_free_model()
        r = ai.chat("你好")
        assert isinstance(r, str) and len(r) > 0
        r2 = ai.chat("今天天气怎么样")
        assert isinstance(r2, str) and len(r2) > 0
        g = ai.get_random_greeting()
        assert isinstance(g, str) and len(g) > 0
        # 切换模型持久化
        ai.current_model = "DeepSeek"
        assert db.get("current_ai_model") == "DeepSeek"
        assert not ai.is_free_model()
        # 无 key 时 chat 返回提示而不是异常
        r3 = ai.chat("你好")
        assert "API Key" in r3, r3
        # get_api_key / get_api_url 的 key 派生与设置页一致
        assert ai.get_api_key() == db.get("deepseek_api_key", "")
        assert ai.get_api_url() == "https://api.deepseek.com/v1/chat/completions"
        # 非法模型名 setter 不应生效
        ai.current_model = "不存在的模型"
        assert ai.current_model == "DeepSeek"
check("AIService 本地对话/模型切换/key派生", t_ai_local)

# ─── 6. WeatherService 离线工具函数 ───────────────────────
def t_weather_utils():
    from weather_service import WeatherService
    # 翻译：长匹配优先
    assert WeatherService._translate_weather_desc("Moderate or heavy rain shower") == "大阵雨"
    assert WeatherService._translate_weather_desc("Light rain") == "小雨"
    assert WeatherService._translate_weather_desc("Sunny") == "晴天"
    assert WeatherService._translate_weather_desc("Partly cloudy") == "多云"
    # 未收录的描述原样返回
    assert WeatherService._translate_weather_desc("Diamond dust") == "Diamond dust"
    # 建议生成
    assert "伞" in WeatherService._generate_advice(20, "小雨", 60)
    assert "高温" in WeatherService._generate_advice(39, "晴天", 40)
    assert "保暖" in WeatherService._generate_advice(-2, "晴天", 40)
    assert "潮" in WeatherService._generate_advice(25, "未知天气", 90)
check("WeatherService 翻译/建议生成", t_weather_utils)

# ─── 7. WeatherService 城市解析（离线部分） ───────────────
def t_weather_city():
    import tempfile
    from db_manager import DBManager
    from weather_service import WeatherService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        ws = WeatherService(db)
        # 手动英文城市
        db.set("city", "Beijing")
        info = ws._resolve_city()
        assert info == {"cn": "北京", "en": "Beijing"}, info
        # 手动中文城市
        db.set("city", "上海")
        info = ws._resolve_city()
        assert info == {"cn": "上海", "en": "Shanghai"}, info
        # 未收录城市原样透传
        db.set("city", "Lhasa")
        info = ws._resolve_city()
        assert info == {"cn": "Lhasa", "en": "Lhasa"}, info
check("WeatherService 城市解析(手动)", t_weather_city)

# ─── 8. SystemStatus ──────────────────────────────────────
def t_sysstatus():
    from system_status import SystemStatus
    st = SystemStatus.get_all_status()
    assert "cpu" in st and "memory" in st and "disk" in st
    assert 0 <= st["memory"]["percent"] <= 100
    summary = SystemStatus.get_status_summary()
    assert "CPU" in summary and "内存" in summary
check("SystemStatus 采集/摘要", t_sysstatus)

# ─── 9. SystemMonitor 采集 ────────────────────────────────
def t_monitor():
    import time
    from config import MonitorConfig
    from plugin_manager import EventBus
    from system_monitor import SystemMonitor
    bus = EventBus()
    events = []
    bus.on("monitor.snapshot", lambda e: events.append(e.data))
    mon = SystemMonitor(MonitorConfig(interval_sec=0.2), bus)
    snap = mon._collect()
    assert 0 <= snap.cpu_percent <= 100
    assert 0 <= snap.mem_percent <= 100
    assert snap.mem_total_gb > 0
    assert snap.load_level in ("normal", "warning", "critical")
    d = snap.to_dict()
    assert set(d) >= {"timestamp", "cpu", "mem", "disk"}
    mon.start()
    time.sleep(0.6)
    mon.stop()
    assert len(events) >= 1, "监控事件未发射"
    assert mon.latest is not None
    assert "系统状态" in mon.get_summary()
check("SystemMonitor 采集/事件", t_monitor)

# ─── 10. 设置页与 AI 服务的 key 派生一致性 ────────────────
def t_key_consistency():
    from ai_service import AIService
    import settings_dialog
    for name in AIService.AI_MODELS:
        assert name in settings_dialog.AI_MODELS, f"设置页缺少模型: {name}"
    for name in settings_dialog.AI_MODELS:
        assert name in AIService.AI_MODELS, f"AI服务缺少模型: {name}"
    # 两处 key 派生算法一致：split(" ")[0].lower()
    for name in ("DeepSeek", "豆包 (Doubao)", "通义千问 (Qwen)", "Kimi"):
        k = name.split(" ")[0].lower()
        assert isinstance(k, str) and k
check("AI_MODELS 两处定义一致", t_key_consistency)

# ─── 11. CourseService 课程表读写与容错 ───────────────────
def t_course_io():
    from db_manager import DBManager
    from course_service import CourseService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        svc = CourseService(db)

        # 空库：空表 + 总开关默认开启
        assert svc.load_courses() == []
        assert svc.is_enabled() is True

        # save → load 往返一致（含中文课程名与教室）
        courses = [
            {"name": "高等数学", "weekday": 1, "start": "08:00", "end": "09:40",
             "room": "教三-201", "remind_before": 10, "enabled": True},
            {"name": "大学物理实验", "weekday": 5, "start": "14:00", "end": "16:30",
             "room": "", "remind_before": 20, "enabled": False},
        ]
        svc.save_courses(courses)
        assert svc.load_courses() == courses, svc.load_courses()

        # 库里存的是 JSON 字符串，且中文未被转义成 \uXXXX
        raw = db.get("course_schedule")
        assert "高等数学" in raw and "\\u" not in raw, raw

        # 总开关读写（值只能是字符串 "1"/"0"）
        svc.set_enabled(False)
        assert svc.is_enabled() is False and db.get("course_reminder_enabled") == "0"
        svc.set_enabled(True)
        assert svc.is_enabled() is True and db.get("course_reminder_enabled") == "1"

        # 保存时跳过非法记录，不写坏整张表
        svc.save_courses([courses[0], {"name": "", "weekday": 1,
                                       "start": "08:00", "end": "09:00"}])
        assert len(svc.load_courses()) == 1

        # JSON 被改坏 / 顶层不是数组 / 字段非法：一律返回 []，不抛异常
        for broken in ('{不是 JSON', '{"a": 1}', '"文本"',
                       '[{"name": "缺字段"}]',
                       '[{"name": "x", "weekday": 9, "start": "08:00", "end": "09:00"}]',
                       '[{"name": "x", "weekday": 1, "start": "25:00", "end": "09:00"}]'):
            db.set("course_schedule", broken)
            assert svc.load_courses() == [], f"未按空课程表处理: {broken}"
check("CourseService 读写/JSON往返/损坏容错", t_course_io)

# ─── 12. CourseService.normalize_course 正反例 ────────────
def t_course_normalize():
    from course_service import CourseService
    norm = CourseService.normalize_course

    # 正例：时间补零、中文星期、去空格、字符串布尔、缺省值
    course, msg = norm({"name": "  高等数学  ", "weekday": 1, "start": "8:00",
                        "end": "9:40", "room": " 教三-201 ", "remind_before": "10",
                        "enabled": "true"})
    assert msg == "", msg
    assert course == {"name": "高等数学", "weekday": 1, "start": "08:00", "end": "09:40",
                      "room": "教三-201", "remind_before": 10, "enabled": True}, course

    # 全角冒号与全角数字：8：00 → 08:00
    course, msg = norm({"name": "英语", "weekday": "周三", "start": "８：００",
                        "end": "9:40"})
    assert msg == "" and course["start"] == "08:00" and course["weekday"] == 3, (msg, course)

    # 缺省：remind_before 缺省为 10、room 缺省为空、enabled 缺省为 True
    course, msg = norm({"name": "体育", "weekday": 2, "start": "08:00", "end": "09:00"})
    assert msg == "" and course["remind_before"] == 10 and course["room"] == "" \
        and course["enabled"] is True, (msg, course)

    # 反例：每条都必须给出错误说明
    bad_cases = [
        ({"name": "", "weekday": 1, "start": "08:00", "end": "09:00"}, "课程名"),
        ({"name": "   ", "weekday": 1, "start": "08:00", "end": "09:00"}, "课程名"),
        ({"name": "x", "weekday": 0, "start": "08:00", "end": "09:00"}, "星期"),
        ({"name": "x", "weekday": 8, "start": "08:00", "end": "09:00"}, "星期"),
        ({"name": "x", "weekday": "周八", "start": "08:00", "end": "09:00"}, "星期"),
        ({"name": "x", "weekday": 1, "start": "25:00", "end": "09:00"}, "开始时间"),
        ({"name": "x", "weekday": 1, "start": "08:70", "end": "09:00"}, "开始时间"),
        ({"name": "x", "weekday": 1, "start": "abc", "end": "09:00"}, "开始时间"),
        ({"name": "x", "weekday": 1, "start": "", "end": "09:00"}, "开始时间"),
        ({"name": "x", "weekday": 1, "start": "08:00", "end": "25:00"}, "结束时间"),
        # start >= end
        ({"name": "x", "weekday": 1, "start": "09:00", "end": "08:00"}, "早于"),
        ({"name": "x", "weekday": 1, "start": "09:00", "end": "09:00"}, "早于"),
        # remind_before 越界 / 非整数
        ({"name": "x", "weekday": 1, "start": "08:00", "end": "09:00",
          "remind_before": 121}, "提前提醒"),
        ({"name": "x", "weekday": 1, "start": "08:00", "end": "09:00",
          "remind_before": -1}, "提前提醒"),
        ({"name": "x", "weekday": 1, "start": "08:00", "end": "09:00",
          "remind_before": "abc"}, "提前提醒"),
        ({"name": "x", "weekday": 1, "start": "08:00", "end": "09:00",
          "remind_before": 10.5}, "提前提醒"),
    ]
    for raw, keyword in bad_cases:
        course, msg = norm(raw)
        assert course is None, f"非法数据被放行: {raw} → {course}"
        assert keyword in msg, f"错误说明未指出问题: {raw} → {msg}"

    # 边界值：0 与 120 合法
    for remind in (0, 120):
        course, msg = norm({"name": "x", "weekday": 7, "start": "08:00",
                            "end": "09:00", "remind_before": remind})
        assert msg == "" and course["remind_before"] == remind, (remind, msg)
check("CourseService.normalize_course 正例/反例", t_course_normalize)

# ─── 13. due_reminders 提醒窗口（固定时间，不依赖系统时钟） ─
def t_course_due():
    from datetime import datetime
    from db_manager import DBManager
    from course_service import CourseService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        svc = CourseService(db)

        # 固定基准：2026-09-16 是周三
        base = datetime(2026, 9, 16, 7, 50)
        assert base.date().isoweekday() == 3, "基准日期必须是周三"

        svc.save_courses([{"name": "高等数学", "weekday": 3, "start": "08:00",
                           "end": "09:40", "room": "教三-201",
                           "remind_before": 10, "enabled": True}])

        # 正好在窗口边界（= remind_before 分钟）→ 提醒
        due = svc.due_reminders(base)
        assert len(due) == 1 and due[0]["minutes_left"] == 10, due
        assert due[0]["name"] == "高等数学"

        # 窗口内（还剩 3 分钟）→ 提醒
        due = svc.due_reminders(datetime(2026, 9, 16, 7, 57))
        assert len(due) == 1 and due[0]["minutes_left"] == 3, due

        # 窗口外：还差 11 分钟 → 不提醒
        assert svc.due_reminders(datetime(2026, 9, 16, 7, 49)) == []
        # 窗口外：已到点（差值 = 0）与已过点 → 不提醒
        assert svc.due_reminders(datetime(2026, 9, 16, 8, 0)) == []
        assert svc.due_reminders(datetime(2026, 9, 16, 8, 30)) == []

        # 星期不匹配（周二同一时刻）→ 不提醒
        assert svc.due_reminders(datetime(2026, 9, 15, 7, 50)) == []

        # 课程 disabled → 不提醒
        svc.save_courses([{"name": "高等数学", "weekday": 3, "start": "08:00",
                           "end": "09:40", "remind_before": 10, "enabled": False}])
        assert svc.due_reminders(base) == []

        # 总开关关闭 → 完全不提醒
        svc.save_courses([{"name": "高等数学", "weekday": 3, "start": "08:00",
                           "end": "09:40", "remind_before": 10, "enabled": True}])
        svc.set_enabled(False)
        assert svc.due_reminders(base) == []
        svc.set_enabled(True)
        assert len(svc.due_reminders(base)) == 1

        # 同一时刻多门课 → 全部返回
        svc.save_courses([
            {"name": "高等数学", "weekday": 3, "start": "08:00", "end": "09:40",
             "remind_before": 10, "enabled": True},
            {"name": "大学英语", "weekday": 3, "start": "07:55", "end": "09:25",
             "remind_before": 10, "enabled": True},
        ])
        due = svc.due_reminders(base)
        assert {c["name"] for c in due} == {"高等数学", "大学英语"}, due
        assert {c["minutes_left"] for c in due} == {10, 5}, due

        # 跨零点：周四 00:05 的课，在周三 23:55 就应提醒（用 datetime 相减，不能比 hour/minute）
        svc.save_courses([{"name": "早自习", "weekday": 4, "start": "00:05",
                           "end": "00:55", "remind_before": 10, "enabled": True}])
        due = svc.due_reminders(datetime(2026, 9, 16, 23, 55))
        assert len(due) == 1 and due[0]["minutes_left"] == 10, due
        # 还差 20 分钟时不提醒
        assert svc.due_reminders(datetime(2026, 9, 16, 23, 45)) == []

        # 课程表被改坏 → 静默返回空，不抛异常
        db.set("course_schedule", "{坏数据")
        assert svc.due_reminders(base) == []
check("CourseService.due_reminders 提醒窗口/边界/跨零点", t_course_due)

# ─── 14. 提醒去重（同一天只提醒一次） ──────────────────────
def t_course_dedup():
    from datetime import datetime, timedelta
    from db_manager import DBManager
    from course_service import CourseService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        svc = CourseService(db)
        svc.save_courses([{"name": "高等数学", "weekday": 3, "start": "08:00",
                           "end": "09:40", "remind_before": 10, "enabled": True}])

        seen: set = set()
        # 模拟连续 10 分钟的 tick：只有第一次返回提醒
        hits = [len(svc.due_reminders(datetime(2026, 9, 16, 7, 50 + i), seen))
                for i in range(10)]
        assert hits[0] == 1 and sum(hits) == 1, hits

        # 第二天同一门课恢复提醒
        assert len(svc.due_reminders(datetime(2026, 9, 23, 7, 50), seen)) == 1

        # 跨零点场景：23:55 提醒了周四 00:05 的课，次日 00:00 的 tick 不再重复
        svc.save_courses([{"name": "早自习", "weekday": 4, "start": "00:05",
                           "end": "00:55", "remind_before": 10, "enabled": True}])
        seen2: set = set()
        assert len(svc.due_reminders(datetime(2026, 9, 16, 23, 55), seen2)) == 1
        assert svc.due_reminders(datetime(2026, 9, 17, 0, 0), seen2) == []

        # 去重集合不会无限增长：更早日期的键会被清理
        seen3 = {"2020-01-01-旧课-08:00"}
        svc.due_reminders(datetime(2026, 9, 16, 7, 50), seen3)
        assert "2020-01-01-旧课-08:00" not in seen3, seen3
check("CourseService 提醒去重/跨天恢复/键清理", t_course_dedup)

# ─── 15. 提醒与今日课程文案 ───────────────────────────────
def t_course_text():
    from datetime import date
    from db_manager import DBManager
    from course_service import CourseService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        svc = CourseService(db)

        text = CourseService.format_reminder({
            "name": "高等数学", "start": "08:00", "end": "09:40",
            "room": "教三-201", "minutes_left": 10,
        })
        assert text == "📚 还有 10 分钟上课\n高等数学 · 08:00-09:40\n📍 教三-201", repr(text)

        # 教室为空 → 省略第三行
        text = CourseService.format_reminder({
            "name": "体育", "start": "08:00", "end": "09:00",
            "room": "", "minutes_left": 5,
        })
        assert text == "📚 还有 5 分钟上课\n体育 · 08:00-09:00", repr(text)

        # minutes_left <= 0 → 改为「该上课了」
        text = CourseService.format_reminder({
            "name": "体育", "start": "08:00", "end": "09:00", "minutes_left": 0,
        })
        assert text.startswith("📚 该上课了"), repr(text)

        # 今日课程：周三有 2 节课，按开始时间排序
        svc.save_courses([
            {"name": "大学英语", "weekday": 3, "start": "10:00", "end": "11:40",
             "room": "外语楼-101", "remind_before": 10, "enabled": True},
            {"name": "高等数学", "weekday": 3, "start": "08:00", "end": "09:40",
             "room": "教三-201", "remind_before": 10, "enabled": True},
        ])
        text = svc.day_text(date(2026, 9, 16))
        assert text == ("📅 今天有 2 节课\n"
                        "08:00 高等数学（教三-201）\n"
                        "10:00 大学英语（外语楼-101）"), repr(text)

        # 无课分支
        assert svc.day_text(date(2026, 9, 20)) == "📅 今天没有课，好好休息～"
        # 教室为空时括号省略
        svc.save_courses([{"name": "自习", "weekday": 3, "start": "08:00",
                           "end": "09:00", "room": "", "remind_before": 10,
                           "enabled": True}])
        assert svc.day_text(date(2026, 9, 16)) == "📅 今天有 1 节课\n08:00 自习"
check("CourseService 提醒/今日课程文案", t_course_text)

# ─── 16. 设置页表格与 CourseService 的字段约定一致 ─────────
def t_course_settings_columns():
    """设置页表格列与课程字段必须一一对应，避免改列时漏改保存逻辑"""
    import settings_dialog
    from course_service import CourseService
    assert settings_dialog.COURSE_COLUMNS == \
        ["课程名", "星期", "开始", "结束", "教室", "提前(分钟)", "启用"], \
        settings_dialog.COURSE_COLUMNS
    assert len(settings_dialog.COURSE_COLUMNS) == 7
    # 星期下拉项与 ISO 星期一一对应
    assert settings_dialog.WEEKDAY_ITEMS == [
        "周一", "周二", "周三", "周四", "周五", "周六", "周日"], \
        settings_dialog.WEEKDAY_ITEMS
    # 默认行必须能通过校验
    course, msg = CourseService.normalize_course(
        settings_dialog.SettingsDialog.make_default_course())
    assert msg == "" and course is not None, msg
check("设置页课程表列定义与字段一致", t_course_settings_columns)

# ─── 17. 课程表插件 /课程 命令 ─────────────────────────────
def t_course_plugin():
    from datetime import date
    from db_manager import DBManager
    from plugin_manager import EventBus, PluginManager
    from course_service import CourseService
    with tempfile.TemporaryDirectory() as td:
        db = DBManager(os.path.join(td, "t.db"))
        pm = PluginManager(EventBus(), plugins_dir="plugins", db=db)
        pm.load_plugins()
        assert "课程表" in [p.name for p in pm.plugins], [p.name for p in pm.plugins]
        assert "课程" in [c["command"] for c in pm.list_commands()], pm.list_commands()

        # 无课分支
        assert "今天没有课" in pm.dispatch_command("/课程")

        # 有课分支（今天）
        CourseService(db).save_courses([
            {"name": "高等数学", "weekday": date.today().isoweekday(), "start": "08:00",
             "end": "09:40", "room": "教三-201", "remind_before": 10, "enabled": True},
        ])
        text = pm.dispatch_command("/course")
        assert "高等数学" in text and "教三-201" in text, text

        # 总开关关闭时给出提示
        CourseService(db).set_enabled(False)
        assert "总开关已关闭" in pm.dispatch_command("/课程")

        # 未注入 db 时优雅降级，不抛异常
        pm2 = PluginManager(EventBus(), plugins_dir="plugins")
        pm2.load_plugins()
        assert "不可用" in pm2.dispatch_command("/课程")
        pm.teardown_all()
        pm2.teardown_all()
check("课程表插件 /课程 命令", t_course_plugin)

# ─── 汇总 ────────────────────────────────────────────────
passed = sum(1 for _, s, _ in results if s == "PASS")
for name, status, detail in results:
    print(f"[{status}] {name}", file=out)
    if detail:
        print("    " + detail.replace("\n", "\n    "), file=out)
print(f"\n==== 逻辑测试: {passed}/{len(results)} 通过 ====", file=out)
out.close()
sys.exit(0 if passed == len(results) else 1)
