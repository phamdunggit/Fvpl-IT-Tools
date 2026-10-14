from __future__ import annotations

import pytest

from fvpl_ittools.core import durations, taskbar


def test_record_keeps_last_runs_and_estimates(state_dir):
    assert durations.estimate("app.chrome") is None
    durations.record([("app.chrome", 60.0), ("app.zalo", 0.4)])  # mục quá nhanh không ghi
    for seconds in (100, 120, 140, 160, 180, 200):
        durations.record([("app.office2016", seconds)])
    data = durations.load()
    assert "app.zalo" not in data and data["app.office2016"] == [120, 140, 160, 180, 200]  # giữ 5 lần gần nhất
    assert durations.estimate("app.office2016") == pytest.approx(160)
    assert durations.total(["app.chrome", "app.office2016"]) == pytest.approx(220)
    assert durations.total(["app.chrome", "app.khong-co"]) is None
    assert durations.minutes_text(20) == "khoảng 1 phút" and durations.minutes_text(400) == "khoảng 7 phút"
    (state_dir / durations.FILE).write_text("{hỏng", encoding="utf-8")
    assert durations.load() == {}


def test_taskbar_progress_never_raises():
    bar = taskbar.TaskbarProgress(0)  # hwnd 0: Windows từ chối, tool không được lỗi
    bar.set_state(taskbar.INDETERMINATE)
    bar.set_value(0.5)
    bar.set_value(1.0, taskbar.ERROR)
    bar.set_state(taskbar.NONE)
    assert isinstance(bar.available, bool)
