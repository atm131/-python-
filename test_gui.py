# -*- coding: utf-8 -*-
"""GUI 测试（QT_QPA_PLATFORM=offscreen）：窗口组装、状态机、对话流程、疑点 bug 复现"""
import io
import os
import sys
import tempfile
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

REPORT = os.path.join(PROJECT, "test_report_gui.txt")
out = io.open(REPORT, "w", encoding="utf-8")
results = []

def check(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
    except Exception as e:
        results.append((name, "FAIL", f"{e}\n{traceback.format_exc()}"))
    # 立即落盘，崩溃也能看到进度
    print(f"[{results[-1][1]}] {results[-1][0]}", file=out)
    if results[-1][2]:
        print("    " + results[-1][2].replace("\n", "\n    "), file=out)
    out.flush()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

app = QApplication([])

from db_manager import DBManager
from config import UIConfig
from weather_service import WeatherService
from plugin_manager import EventBus, PluginManager

TMP = tempfile.mkdtemp()
db = DBManager(os.path.join(TMP, "t.db"))
ws = WeatherService(db)
bus = EventBus()
pm = PluginManager(bus, plugins_dir="plugins")
pm.load_plugins()

def pump(ms):
    """让事件循环运行 ms 毫秒"""
    from PyQt6.QtCore import QEventLoop
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

# ─── 1. PetWindow 组装与状态机 ────────────────────────────
def t_petwindow():
    from pet_window import PetWindow, PET_STATES
    pet = PetWindow(db, ws, UIConfig(), plugin_manager=pm)
    # 7 个状态立绘全部加载
    assert len(pet._pet_pixmaps) == len(PET_STATES), \
        f"立绘缺失: {set(PET_STATES) - set(pet._pet_pixmaps)}"
    # 状态切换
    pet.set_state("greet")
    assert pet.state == "greet"
    pet.set_state("happy", 200)
    assert pet.state == "happy"
    pump(400)  # 到期应回退 idle
    assert pet.state == "idle", pet.state
    # 非法状态不变
    pet.set_state("不存在")
    assert pet.state == "idle"
    # 气泡显示/隐藏（200ms 后开始淡出, 50ms/步 * 25 步 + 事件循环开销 ≈ 1.8s）
    pet.show_bubble("测试气泡", 200)
    assert pet.bubble._visible
    pump(2600)
    assert not pet.bubble._visible, "气泡未自动隐藏"
    # pet.state 事件驱动
    bus.emit("pet.state", {"state": "alert", "revert_after_ms": 100})
    assert pet.state == "alert"
    pump(300)
    assert pet.state == "idle"
    pet.close()
check("PetWindow 组装/状态机/气泡", t_petwindow)

# ─── 2. ChatDialog 对话流程（本地免费模型） ───────────────
def t_chatdialog():
    from chat_dialog import ChatDialog
    dlg = ChatDialog(db, None, plugin_manager=pm)
    dlg.show()
    doc_len_before = dlg.chat_history.document().characterCount()
    assert doc_len_before > 10  # 欢迎语已插入
    # 发送消息（本地模型即时回复，但走线程）
    dlg.input_field.setText("你好")
    dlg._send_message()
    assert not dlg.input_field.isEnabled()  # 发送后禁用
    for _ in range(50):
        pump(50)
        if dlg.input_field.isEnabled():
            break
    assert dlg.input_field.isEnabled(), "回复后输入未恢复"
    text = dlg.chat_history.toPlainText()
    assert "正在思考中" not in text, "思考中占位未移除"
    assert "你好" in text
    dlg.close()
check("ChatDialog 发送/回复/占位回滚", t_chatdialog)

# ─── 3. 疑点复现：清空对话后回复到达，_thinking_pos 过期 ──
def t_stale_thinking_pos():
    from chat_dialog import ChatDialog
    dlg = ChatDialog(db, None, plugin_manager=pm)
    dlg.show()
    dlg.input_field.setText("你好")
    dlg._send_message()
    pump(30)
    # 在回复到达前清空对话（_thinking_pos 未重置 → 过期位置）
    dlg._clear_history()
    mark = "清空后的新消息"
    dlg._add_message("🤖 AI 助手", mark, is_user=False)
    for _ in range(50):
        pump(50)
        if dlg.input_field.isEnabled():
            break
    text = dlg.chat_history.toPlainText()
    # 过期位置删除不应把清空后的新内容误删
    assert mark in text, f"清空后的消息被误删！当前内容: {text[:200]}"
    dlg.close()
check("疑点: _thinking_pos 过期误删内容", t_stale_thinking_pos)

# ─── 4. 回归：纯 Python 线程 → GUI 线程的告警桥 ───────────
def t_alert_bridge():
    """main.py 修复方案回归测试：
    SystemMonitor 是纯 threading.Thread（无 Qt 事件循环），
    QTimer.singleShot 在其中永不触发 —— 修复后改用 pyqtSignal 桥接，
    这里验证桥接模式在纯 Python 线程发射时槽函数能正常执行。"""
    import threading
    from PyQt6.QtCore import QObject, pyqtSignal

    class _B(QObject):
        sig = pyqtSignal(str)

    got = []
    b = _B()
    b.sig.connect(got.append)
    t = threading.Thread(target=lambda: b.sig.emit("hello"), daemon=True)
    t.start(); t.join()
    pump(400)
    assert got == ["hello"], f"信号桥未生效: {got}"
check("回归: 监控线程信号桥(告警修复)", t_alert_bridge)

# ─── 4b. 回归：对话框关闭后后台线程安全收尾 ───────────────
def t_worker_lifecycle():
    """对话框 WA_DeleteOnClose + 线程注册表：
    关闭对话框时后台 AI 请求仍在进行，线程须由注册表保管到结束并自动清理，
    不崩溃、不泄漏。"""
    import gc
    import time as _time
    from PyQt6 import sip
    from chat_dialog import ChatDialog

    dlg = ChatDialog(db, None, plugin_manager=pm)
    dlg.show()
    dlg.ai_service.chat = lambda m: (_time.sleep(0.5), "回复")[1]  # 模拟慢速 AI
    dlg.input_field.setText("你好")
    dlg._send_message()
    assert len(ChatDialog._active_workers) == 1
    t0 = _time.time()
    dlg.close()   # 应立即返回，不再 wait(3000) 卡 UI
    assert _time.time() - t0 < 1.0, "close 仍在阻塞等待后台线程"
    pump(100)     # WA_DeleteOnClose 的 DeferredDelete 需事件循环处理
    assert sip.isdeleted(dlg), "对话框未随关闭销毁（WA_DeleteOnClose 失效）"
    del dlg
    gc.collect()
    for _ in range(40):
        pump(50)
        if not ChatDialog._active_workers:
            break
    assert not ChatDialog._active_workers, "后台线程结束后未从注册表清理"
check("回归: 对话框关闭后线程安全收尾", t_worker_lifecycle)

# ─── 5. 插件命令经对话窗口分发（不触网的分支） ────────────
def t_plugin_via_chat():
    from chat_dialog import ChatDialog
    dlg = ChatDialog(db, None, plugin_manager=pm)
    dlg.show()
    dlg.input_field.setText("/天气")   # 缺参数, 不触网
    dlg._send_message()
    for _ in range(50):
        pump(50)
        if dlg.input_field.isEnabled():
            break
    text = dlg.chat_history.toPlainText()
    assert "请指定城市名" in text, text[:300]
    dlg.close()
check("插件命令经对话窗口分发", t_plugin_via_chat)

# ─── 6. SettingsDialog 加载与保存 ─────────────────────────
def t_settings():
    from settings_dialog import SettingsDialog
    from PyQt6.QtWidgets import QMessageBox
    # offscreen 下模态 QMessageBox 会阻塞事件循环，打补丁跳过
    orig = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        dlg = SettingsDialog(db)
        dlg.city_input.setText("Beijing")
        dlg.radio_manual.setChecked(True)
        dlg.model_combo.setCurrentText("DeepSeek")
        dlg.api_key_input.setText("sk-test-123")
        dlg._save()
        assert db.get("city") == "Beijing"
        assert db.get("current_ai_model") == "DeepSeek"
        assert db.get("deepseek_api_key") == "sk-test-123"
        # 重新打开应回填
        dlg2 = SettingsDialog(db)
        assert dlg2.model_combo.currentText() == "DeepSeek"
        assert dlg2.api_key_input.text() == "sk-test-123"
        assert dlg2.city_input.text() == "Beijing"
        dlg2.close(); dlg.close()
    finally:
        QMessageBox.information = orig
check("SettingsDialog 保存/回填", t_settings)

# ─── 7. main.Application 组装 + 告警端到端 ─────────────────
def t_application():
    """验证 Application 完整组装，且监控线程的 cpu_high 事件
    能经信号桥真正驱动宠物状态与气泡（修复回归）"""
    import subprocess
    code = r'''
import os, sys, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"E:\毕业设计\smart_desktop_pet")
os.chdir(r"E:\毕业设计\smart_desktop_pet")
import shutil, tempfile
tmp = tempfile.mkdtemp()
if os.path.exists("pet_settings.db"):
    shutil.copy("pet_settings.db", os.path.join(tmp, "pet_settings.db"))
os.chdir(tmp)
sys.path.insert(0, r"E:\毕业设计\smart_desktop_pet")
import main
app = main.Application()
app.pet.show()

# 在纯 Python 线程中发射监控事件（与 SystemMonitor 的真实场景一致）
def fire():
    time.sleep(0.2)
    app.bus.emit("monitor.cpu_high", {"cpu": 99.9})
    app.bus.emit("pet.show_bubble", {"text": "插件气泡", "duration": 3000})
threading.Thread(target=fire, daemon=True).start()

from PyQt6.QtCore import QTimer
result = {}
def check():
    result["state"] = app.pet.state
    result["bubble_visible"] = app.pet.bubble._visible
    result["bubble_text"] = app.pet.bubble._text
    result["course_running"] = app.course_reminder.running
    app.qt_app.quit()
QTimer.singleShot(1500, check)
app.qt_app.exec()
app.monitor.stop()
app.course_reminder.stop()
assert result["state"] == "alert", f"宠物未切换 alert 状态: {result}"
assert result["bubble_visible"], f"告警气泡未显示: {result}"
assert result["course_running"], "课程提醒调度未随 Application 启动"
print("ASSEMBLY_OK")
print("ALERT_OK", result["state"], repr(result["bubble_text"][:20]))
print("COURSE_OK", result["course_running"])
'''
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert "ASSEMBLY_OK" in r.stdout, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "ALERT_OK" in r.stdout, f"监控告警未到达 UI:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "COURSE_OK" in r.stdout, f"课程提醒未启动:\nstdout={r.stdout}\nstderr={r.stderr}"
check("main.Application 组装+告警端到端", t_application)

# ─── 8. 设置页「📅 课程表」页签：添加/保存/回填 ─────────────
def t_settings_course_tab():
    import tempfile as _tempfile
    from PyQt6.QtWidgets import QMessageBox
    from course_service import CourseService
    from settings_dialog import SettingsDialog

    tmp = _tempfile.mkdtemp()
    cdb = DBManager(os.path.join(tmp, "course.db"))
    orig_info, orig_warning = QMessageBox.information, QMessageBox.warning
    warnings = []
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a))
    try:
        dlg = SettingsDialog(cdb)
        # 第三个页签存在且标题正确
        assert dlg.tabs.count() == 3, dlg.tabs.count()
        assert dlg.tabs.tabText(2) == "📅 课程表", dlg.tabs.tabText(2)
        assert dlg.course_table.rowCount() == 0

        # 添加一行并填写（时间故意写 "8:00"，验证保存时补零）
        row = dlg.add_course_row()
        dlg.course_table.item(row, 0).setText("高等数学")
        dlg.course_table.cellWidget(row, 1).setCurrentIndex(0)   # 周一
        dlg.course_table.item(row, 2).setText("8:00")
        dlg.course_table.item(row, 3).setText("9:40")
        dlg.course_table.item(row, 4).setText("教三-201")
        dlg.course_table.item(row, 5).setText("10")
        # 第二行：周五、禁用（走 add_course_row 传值，与用户点按钮同一条路径）
        dlg.add_course_row({"name": "大学物理", "weekday": 5, "enabled": False})
        dlg.course_enabled_check.setChecked(True)
        dlg._save()
        assert not warnings, warnings

        stored = CourseService(cdb).load_courses()
        assert len(stored) == 2, stored
        assert stored[0] == {"name": "高等数学", "weekday": 1, "start": "08:00",
                             "end": "09:40", "room": "教三-201",
                             "remind_before": 10, "enabled": True}, stored[0]
        assert stored[1]["name"] == "大学物理" and stored[1]["weekday"] == 5 \
            and stored[1]["enabled"] is False, stored[1]

        # 重新构造对话框 → 数据回填正确
        dlg2 = SettingsDialog(cdb)
        assert dlg2.course_table.rowCount() == 2
        assert dlg2.course_table.item(0, 0).text() == "高等数学"
        assert dlg2.course_table.item(0, 2).text() == "08:00"
        assert dlg2.course_table.item(0, 5).text() == "10"
        assert dlg2.course_table.cellWidget(0, 1).currentIndex() == 0
        assert dlg2.course_table.cellWidget(0, 6).checkbox.isChecked()
        assert dlg2.course_table.item(1, 0).text() == "大学物理"
        assert dlg2.course_table.cellWidget(1, 1).currentIndex() == 4
        assert not dlg2.course_table.cellWidget(1, 6).checkbox.isChecked()
        assert dlg2.course_enabled_check.isChecked()

        # 删除选中行 → 保存后库里只剩一行
        dlg2.course_table.selectRow(0)
        dlg2.remove_selected_courses()
        assert dlg2.course_table.rowCount() == 1
        dlg2._save()
        assert [c["name"] for c in CourseService(cdb).load_courses()] == ["大学物理"]

        # 总开关关闭后重开设置页仍为关闭状态（数据保留）
        dlg2.course_enabled_check.setChecked(False)
        dlg2._save()
        assert CourseService(cdb).is_enabled() is False
        assert len(CourseService(cdb).load_courses()) == 1
        dlg3 = SettingsDialog(cdb)
        assert dlg3.course_enabled_check.isChecked() is False
        dlg3.close(); dlg2.close(); dlg.close()
    finally:
        QMessageBox.information, QMessageBox.warning = orig_info, orig_warning
check("设置页课程表页签 添加/保存/回填/删除", t_settings_course_tab)

# ─── 9. 设置页课程表校验：非法数据被拦截且不破坏原数据 ──────
def t_settings_course_invalid():
    import tempfile as _tempfile
    from PyQt6.QtWidgets import QMessageBox
    from course_service import CourseService
    from settings_dialog import SettingsDialog

    tmp = _tempfile.mkdtemp()
    cdb = DBManager(os.path.join(tmp, "course.db"))
    svc = CourseService(cdb)
    svc.save_courses([{"name": "高等数学", "weekday": 1, "start": "08:00",
                       "end": "09:40", "room": "教三-201",
                       "remind_before": 10, "enabled": True}])
    before = svc.load_courses()
    cdb.set("city", "Beijing")

    orig_info, orig_warning = QMessageBox.information, QMessageBox.warning
    warnings = []
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a))
    try:
        dlg = SettingsDialog(cdb)
        dlg.radio_manual.setChecked(True)
        dlg.city_input.setText("BadCity")   # 城市设置也应一并中止，避免半截保存

        # 非法时间 25:00
        dlg.course_table.item(0, 2).setText("25:00")
        dlg._save()
        assert len(warnings) == 1, warnings
        assert warnings[-1][1] == "课程表有误"
        assert "第 1 行" in warnings[-1][2] and "开始时间" in warnings[-1][2], warnings[-1]
        assert svc.load_courses() == before, "非法保存破坏了原有课程数据"
        assert cdb.get("city") == "Beijing", "非法保存写入了城市设置"

        # 无法解析的时间 abc
        dlg.course_table.item(0, 2).setText("abc")
        dlg._save()
        assert len(warnings) == 2 and "第 1 行" in warnings[-1][2], warnings
        assert svc.load_courses() == before

        # 空课程名
        dlg.course_table.item(0, 0).setText("   ")
        dlg._save()
        assert len(warnings) == 3 and "课程名" in warnings[-1][2], warnings
        assert svc.load_courses() == before

        # start >= end
        dlg.course_table.item(0, 0).setText("高等数学")
        dlg.course_table.item(0, 2).setText("09:00")
        dlg.course_table.item(0, 3).setText("08:00")
        dlg._save()
        assert len(warnings) == 4 and "早于" in warnings[-1][2], warnings
        assert svc.load_courses() == before

        # 提前分钟数越界
        dlg.course_table.item(0, 3).setText("10:30")
        dlg.course_table.item(0, 5).setText("999")
        dlg._save()
        assert len(warnings) == 5 and "提前提醒" in warnings[-1][2], warnings
        assert svc.load_courses() == before

        # 全部修正后保存成功
        dlg.course_table.item(0, 5).setText("15")
        dlg._save()
        assert len(warnings) == 5, "修正后不应再弹错误提示"
        fixed = svc.load_courses()
        assert fixed[0]["start"] == "09:00" and fixed[0]["remind_before"] == 15, fixed
        assert cdb.get("city") == "BadCity"
        dlg.close()
    finally:
        QMessageBox.information, QMessageBox.warning = orig_info, orig_warning
check("设置页课程表校验 拦截非法/保护原数据", t_settings_course_invalid)

# ─── 10. 课程提醒：气泡触发 / 去重 / 总开关 / 定时器 ────────
def t_course_reminder():
    import tempfile as _tempfile
    from datetime import datetime, timedelta
    from course_service import CourseReminder, CourseService
    from pet_window import PetWindow

    tmp = _tempfile.mkdtemp()
    rdb = DBManager(os.path.join(tmp, "reminder.db"))
    svc = CourseService(rdb)

    pet = PetWindow(rdb, WeatherService(rdb), UIConfig(), plugin_manager=pm)
    # 与 main.py 相同的接线：事件总线 → 宠物气泡
    handler = lambda e: pet.show_bubble(e.data.get("text", ""),
                                       int(e.data.get("duration", 5000)))
    bus.on("pet.show_bubble", handler)
    try:
        reminder = CourseReminder(rdb, bus)

        # 课程表为空 → 静默跳过，不报错、不弹空气泡
        assert reminder.check_now() == []
        assert not pet.bubble._visible

        # 「当前时间 + 2 分钟」开课，落在 10 分钟提醒窗口内。
        # now 对齐到整分钟：课程时间只精确到分钟，秒数会让"还有几分钟"在 1~2 之间浮动
        now = datetime.now().replace(second=0, microsecond=0)
        start = now + timedelta(minutes=2)
        if start.strftime("%H:%M") == "23:59":
            # end 必须晚于 start，"23:59" 无法再大；挪到次日 00:00 附近（概率极低的分支）
            start = now + timedelta(minutes=3)
        course = {"name": "高等数学", "weekday": start.date().isoweekday(),
                  "start": start.strftime("%H:%M"), "end": "23:59",
                  "room": "教三-201", "remind_before": 10, "enabled": True}
        svc.save_courses([course])

        due = reminder.check_now(now)   # 传入固定 now，断言不受执行耗时影响
        assert len(due) == 1, due
        assert due[0]["minutes_left"] == 2, due
        assert pet.bubble._visible is True, "提醒气泡未显示"
        text = pet.bubble._text
        assert "高等数学" in text and "教三-201" in text, repr(text)
        assert "📚 还有" in text and "分钟上课" in text, repr(text)
        assert pet.state == "greet", pet.state   # 用 greet 举手，而不是 alert

        # 去重：同一门课同一天只提醒一次
        pet.bubble.hide_bubble()
        assert reminder.check_now() == []
        assert not pet.bubble._visible, "去重失效，重复弹了气泡"

        # 总开关关闭 → 完全不提醒；重新打开 → 恢复提醒（走真实当前时间）
        svc.save_courses([dict(course, name="线性代数")])
        svc.set_enabled(False)
        assert reminder.check_now() == []
        assert not pet.bubble._visible
        svc.set_enabled(True)
        assert len(reminder.check_now()) == 1
        assert "线性代数" in pet.bubble._text, repr(pet.bubble._text)

        # 定时器启停
        reminder.start()
        assert reminder.running
        reminder.stop()
        assert not reminder.running
    finally:
        bus.off("pet.show_bubble", handler)
        pet.close()
check("课程提醒 气泡/去重/总开关/定时器", t_course_reminder)

# ─── 11. 右键菜单「📅 今日课程」 ───────────────────────────
def t_today_courses_menu():
    import tempfile as _tempfile
    from datetime import date
    from course_service import CourseService
    from pet_window import PetWindow

    tmp = _tempfile.mkdtemp()
    cdb = DBManager(os.path.join(tmp, "today.db"))
    svc = CourseService(cdb)
    pet = PetWindow(cdb, WeatherService(cdb), UIConfig(), plugin_manager=pm)
    try:
        # 菜单项齐全：新增一项的同时原有项不能丢
        texts = [a.text() for a in pet._build_context_menu().actions() if a.text()]
        for expected in ("💬 AI 对话", "🌤️ 查询天气", "📊 系统状态",
                         "📅 今日课程", "⚙️ 设置", "🚪 退出"):
            assert expected in texts, (expected, texts)

        # 无课分支
        pet._show_today_courses()
        assert pet.bubble._visible
        assert pet.bubble._text == "📅 今天没有课，好好休息～", repr(pet.bubble._text)

        # 有课分支：按开始时间排序，教室为空时省略括号
        today = date.today()
        svc.save_courses([
            {"name": "高等数学", "weekday": today.isoweekday(), "start": "08:00",
             "end": "09:40", "room": "教三-201", "remind_before": 10, "enabled": True},
            {"name": "大学英语", "weekday": today.isoweekday(), "start": "10:00",
             "end": "11:40", "room": "", "remind_before": 10, "enabled": True},
        ])
        pet._show_today_courses()
        assert pet.bubble._text == ("📅 今天有 2 节课\n"
                                    "08:00 高等数学（教三-201）\n"
                                    "10:00 大学英语"), repr(pet.bubble._text)

        # 数据库里的 JSON 被改坏 → 仍走"没有课"分支，不抛异常
        cdb.set("course_schedule", "{坏数据")
        pet._show_today_courses()
        assert pet.bubble._text == "📅 今天没有课，好好休息～"
    finally:
        pet.close()
check("右键菜单 今日课程（有课/无课/数据损坏）", t_today_courses_menu)

# ─── 汇总 ────────────────────────────────────────────────
passed = sum(1 for _, s, _ in results if s == "PASS")
print(f"\n==== GUI 测试: {passed}/{len(results)} 通过 ====", file=out)
out.close()
sys.exit(0 if passed == len(results) else 1)
