from __future__ import annotations

import pytest

from fvpl_ittools.core import executor, progress
from fvpl_ittools.core.executor import Level, Status

from .test_executor import cmd_action


@pytest.mark.parametrize(("line", "percent", "phase"), [
    ("##PROGRESS - Đang cài đặt", None, "Đang cài đặt"),
    ("##PROGRESS 30 Đang chép", 30.0, "Đang chép"),
    ("##PROGRESS 140 quá", 100.0, "quá"),
    ("  ██████████▒▒▒▒▒▒▒▒▒▒  56.0 MB / 112 MB", 50.0, progress.DOWNLOADING),
    ("  ━━━━━━━━━━━━━  1.00 GB / 2.00 GB", 50.0, progress.DOWNLOADING),
    ("[==========================23.4%                          ]", 23.4, ""),
    ("  45%", 45.0, ""),
    ("  ██████▒▒▒▒  60%", 60.0, ""),
    ("Downloading https://dl.google.com/chrome.msi", 0.0, progress.DOWNLOADING),
    ("Starting package install...", None, progress.INSTALLING),
    ("Successfully installed", 100.0, "Cài xong"),
])
def test_parse_reads_progress_lines(line, percent, phase):
    hint = progress.parse(line)
    assert hint is not None
    assert hint.percent == (pytest.approx(percent) if percent is not None else None)
    assert hint.phase == phase
    assert hint.hide == line.startswith("##")


@pytest.mark.parametrize("line", ["", "Ổ C còn 5% dung lượng", "Đã xong 3/8 mục", "Found Google Chrome [Google.Chrome]",
                                  "  120%", "5 MB / 2 MB"])
def test_parse_ignores_ordinary_lines(line):
    assert progress.parse(line) is None


def test_marker_line_is_powershell_write_output():
    assert progress.marker("Đang cài đặt") == "Write-Output '##PROGRESS - Đang cài đặt'"
    assert progress.marker("Bob's", 40) == "Write-Output '##PROGRESS 40 Bob''s'"


def _tracker():
    started = progress.BatchStarted(7, (progress.PlanItem("a", "Cài A"), progress.PlanItem("b", "Cài B", "Cần admin"),
                                        progress.PlanItem("c", "Cài C"), progress.PlanItem("d", "Cài D")))
    return progress.Tracker(started)


def test_tracker_counts_fraction_and_headline():
    tracker = _tracker()
    assert tracker.count(progress.SKIPPED) == 1 and tracker.items[1].message == "Cần admin"
    assert tracker.headline() == "Đang chuẩn bị…"
    assert tracker.apply(progress.ItemUpdate(7, progress.BATCH, phase="Đang tạo điểm khôi phục"))
    assert tracker.headline() == "Đang tạo điểm khôi phục"
    tracker.apply(progress.ItemUpdate(7, 0, progress.RUNNING))
    tracker.apply(progress.ItemUpdate(7, 0, progress.RUNNING, 0.0, progress.DOWNLOADING))
    tracker.apply(progress.ItemUpdate(7, 0, progress.RUNNING, 50.0, ""))  # chỉ có % thì giữ giai đoạn cũ
    assert tracker.headline() == "Mục 1/4: Cài A · Đang tải về 50%"
    assert tracker.fraction == pytest.approx((1 + 0.5) / 4)  # mục bỏ qua tính là xong
    tracker.apply(progress.ItemUpdate(7, 0, progress.RUNNING, None, progress.INSTALLING))
    assert tracker.items[0].percent is None and tracker.headline().endswith("Đang cài đặt")
    tracker.apply(progress.ItemUpdate(7, 0, progress.OK, reboot=True))
    tracker.apply(progress.ItemUpdate(7, 2, progress.FAILED, message="mã 1603"))
    assert tracker.current is None and tracker.items[0].reboot and tracker.items[2].message == "mã 1603"
    assert not tracker.apply(progress.ItemUpdate(8, 3, progress.RUNNING))  # lượt khác
    assert tracker.count(progress.WAITING) == 1 and tracker.fraction == pytest.approx(3 / 4)


def test_batch_reports_plan_items_and_percent(ctx):
    events = []
    ctx.report = events.append
    actions = [cmd_action("echo ##PROGRESS 40 Tai ve& echo   75%& exit /b 0", id="test.one", name="Một"),
               cmd_action("exit /b 2", id="test.two", name="Hai"),
               cmd_action(id="test.admin", name="Ba", admin=True)]
    batch = executor.run_batch(actions, ctx)
    assert [result.status for result in batch.results] == [Status.SKIPPED, Status.OK, Status.FAILED]
    started = events[0]
    assert isinstance(started, progress.BatchStarted)
    assert [item.name for item in started.items] == ["Một", "Hai", "Ba"] and started.items[2].skipped
    updates = [(event.index, event.state, event.percent) for event in events[1:]]
    assert updates == [(0, "running", None), (0, "running", 40.0), (0, "running", 75.0), (0, "ok", None),
                       (1, "running", None), (1, "failed", None)]
    assert all(event.batch_id == started.batch_id for event in events[1:])
    logged = [event.text for event in ctx.events if event.level is Level.OUTPUT]
    assert not any("##PROGRESS" in text for text in logged)  # dòng đánh dấu không vào log
    assert ctx.current is None


def test_stop_after_current_cancels_the_rest(ctx, monkeypatch):
    events = []
    ctx.report = events.append
    run_action = executor.run_action

    def run_and_stop(action, context):
        context.stop_after.set()  # IT bấm "Dừng sau mục đang chạy" trong lúc mục đầu chạy
        return run_action(action, context)

    monkeypatch.setattr(executor, "run_action", run_and_stop)
    batch = executor.run_batch([cmd_action(id="test.one"), cmd_action(id="test.two"), cmd_action(id="test.three")], ctx)
    assert [result.status for result in batch.results] == [Status.OK, Status.CANCELLED, Status.CANCELLED]
    assert batch.cancelled
    assert [(event.index, event.state) for event in events[1:]] == [
        (0, "running"), (0, "ok"), (1, "cancelled"), (2, "cancelled")]
