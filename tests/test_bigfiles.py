from __future__ import annotations

import _winapi
import threading

from fvpl_ittools.cleanup import bigfiles


def make(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_find_large_files_and_folder_sizes(tmp_path):
    make(tmp_path / "Users" / "nva" / "video.mp4", 5000)
    make(tmp_path / "Users" / "nva" / "small.txt", 10)
    make(tmp_path / "Data" / "backup.zip", 3000)
    make(tmp_path / "root.iso", 4000)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    make(outside / "huge.bin", 9000)
    _winapi.CreateJunction(str(outside), str(tmp_path / "Data" / "link"))  # không được đếm

    result = bigfiles.find(str(tmp_path), 1000, threading.Event())
    assert [item.size for item in result.files] == [5000, 4000, 3000]
    assert result.files[0].path.endswith("video.mp4")
    assert result.scanned == 4 and not result.cancelled
    assert result.folders == [(5010, str(tmp_path / "Users")), (3000, str(tmp_path / "Data"))]


def test_limit_keeps_largest(tmp_path):
    for index in range(10):
        make(tmp_path / f"f{index}.bin", 100 * (index + 1))
    result = bigfiles.find(str(tmp_path), 1, threading.Event(), limit=3)
    assert [item.size for item in result.files] == [1000, 900, 800]


def test_cancel_and_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(bigfiles, "PROGRESS_EVERY", 2)
    for index in range(5):
        make(tmp_path / str(index) / "a.bin", 10)
    seen = []
    result = bigfiles.find(str(tmp_path), 1, threading.Event(), progress=seen.append)
    assert seen and result.scanned == 5
    cancel = threading.Event()
    cancel.set()
    assert bigfiles.find(str(tmp_path), 1, cancel).cancelled
