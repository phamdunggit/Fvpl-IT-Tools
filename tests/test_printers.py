from __future__ import annotations

import pytest

from fvpl_ittools.actions.model import PowerShellStep
from fvpl_ittools.printers import inf, manage

SAMPLE_INF = r"""
; Driver mẫu, không phải của hãng nào
[Version]
Signature="$Windows NT$"
Class=Printer
ClassGuid={4D36E979-E325-11CE-BFC1-08002BE10318}
Provider=%MFG%

[Manufacturer]
%MFG% = Models, NTamd64, NTamd64.10.0, NTx86   ; chú thích cuối dòng

[Models.NTamd64]
"Contoso Laser 100 PCL6" = INSTALL, USBPRINT\Contoso100
%Model200% = INSTALL, \
    USBPRINT\Contoso200
"Contoso Laser 100 PCL6" = INSTALL, WSDPRINT\Contoso100

[Models.NTamd64.10.0]
"Contoso Laser 300; Duplex" = INSTALL

[Models.NTx86]
"Contoso Old x86" = INSTALL

[Strings]
MFG = "Contoso"
Model200 = "Contoso Laser 200 PS"
"""

# Kết quả mẫu của list.ps1 (tên máy, IP bịa ra). PowerShell 5.1 hay xuất mảng một phần tử thành một giá trị.
SNAPSHOT = {
    "tool_user": "TEST\\it",
    "other_user": True,
    "spooler": "Running",
    "error": "",
    "printers": [
        {"name": "Contoso Laser (10.0.0.5)", "port": "IP_10.0.0.5", "host": "10.0.0.5", "driver": "Contoso PCL6",
         "shared": True, "share_name": "Laser", "status": 3, "error_state": 0, "offline": False, "jobs": 2},
        {"name": "Microsoft Print to PDF", "port": "PORTPROMPT:", "host": "", "driver": "Microsoft Print To PDF",
         "shared": False, "share_name": "", "status": 3, "error_state": 0, "offline": False, "jobs": 0},
        {"name": "\\\\PC02\\Kho", "port": "USB001", "host": "", "driver": "Contoso PS", "shared": True,
         "share_name": "Kho", "status": 3, "error_state": 0, "offline": True, "jobs": 0},
        {"name": "\\\\PC03\\Ke toan", "port": "USB001", "host": "", "driver": "Contoso PCL6", "shared": True,
         "share_name": "Ke toan", "status": 7, "error_state": 0, "offline": False, "jobs": 0},
    ],
    "machine_connections": ["\\\\PC03\\Ke toan", "\\\\PC04\\Moi"],
    "user_connections": ["\\\\PC05\\Nhan su", "\\\\pc03\\ke toan"],
    "default_printer": "\\\\PC05\\Nhan su",
    "drivers": ["Contoso PCL6", "Microsoft IPP Class Driver"],
}


# ---------------------------------------------------------------- file .inf


def test_inf_models_for_each_architecture():
    assert inf.models_from_text(SAMPLE_INF, "ntamd64") == [
        "Contoso Laser 100 PCL6", "Contoso Laser 200 PS", "Contoso Laser 300; Duplex"]
    assert inf.models_from_text(SAMPLE_INF, "ntx86") == ["Contoso Old x86"]


def test_inf_models_reads_utf16_file(tmp_path):
    file = tmp_path / "contoso.inf"
    file.write_bytes(SAMPLE_INF.encode("utf-16"))  # có BOM, như phần lớn file .inf của hãng
    assert inf.inf_models(file, "ntamd64")[0] == "Contoso Laser 100 PCL6"


def test_inf_models_explains_unusable_files(tmp_path):
    with pytest.raises(inf.InfError, match="không phải driver máy in"):
        inf.models_from_text(SAMPLE_INF.replace("Class=Printer", "Class=Net").replace("ClassGuid", "X"), "ntamd64")
    only_x86 = SAMPLE_INF.replace("NTamd64, NTamd64.10.0, ", "")
    with pytest.raises(inf.InfError, match="64-bit"):
        inf.models_from_text(only_x86, "ntamd64")
    with pytest.raises(inf.InfError, match="Không đọc được"):
        inf.inf_models(tmp_path / "missing.inf")


def test_inf_strings_fall_back_to_language_section():
    text = SAMPLE_INF.replace("[Strings]", "[Strings.0409]")
    assert "Contoso Laser 200 PS" in inf.models_from_text(text, "ntamd64")


# ---------------------------------------------------------------- giá trị IT nhập


@pytest.mark.parametrize("text, ok", [
    ("192.168.1.50", True), ("printer-01.corp.example", True),
    ("", False), ("-x", False), ("10.0.0.1; calc", False), ("10.0.0.1 & calc", False),
])
def test_valid_address(text, ok):
    assert manage.valid_address(text) is ok


@pytest.mark.parametrize("text, expected", [
    ("\\\\PC01\\HP LaserJet", "\\\\PC01\\HP LaserJet"),
    ("pc01/HP", "\\\\pc01\\HP"),
    ("  \\\\pc01\\Máy in màu  ", "\\\\pc01\\Máy in màu"),
    ("\\\\pc 01\\x", None),
    ("\\\\pc01\\", None),
    ('\\\\pc01\\a"b', None),
    ("\\\\pc01\\a\\b", None),
    ("\\\\pc01\\a,b", None),
])
def test_normalize_share(text, expected):
    assert manage.normalize_share(text) == expected


def test_valid_printer_name():
    assert manage.valid_printer_name("Máy in phòng Kế toán")
    assert not manage.valid_printer_name("a,b")
    assert not manage.valid_printer_name(" a")
    assert not manage.valid_printer_name("x" * 201)


# ---------------------------------------------------------------- danh sách


def test_parse_snapshot_merges_connections():
    snap = manage.parse_snapshot(SNAPSHOT)
    by_name = {printer.name: printer for printer in snap.printers}
    assert [printer.name for printer in snap.printers] == [
        "Contoso Laser (10.0.0.5)", "Microsoft Print to PDF",       # máy in trên máy
        "\\\\PC03\\Ke toan", "\\\\PC04\\Moi",                      # share của cả máy
        "\\\\PC05\\Nhan su",                                      # share của người đang đăng nhập
        "\\\\PC02\\Kho",                                          # share của tài khoản chạy tool
    ]
    laser = by_name["Contoso Laser (10.0.0.5)"]
    assert (laser.kind, laser.label, laser.where, laser.share_name, laser.jobs) == (
        manage.KIND_LOCAL, "Mạng (IP)", "10.0.0.5", "Laser", 2)
    assert by_name["Microsoft Print to PDF"].label == "Khác / máy in ảo"

    kho = by_name["\\\\PC02\\Kho"]
    assert kho.kind == manage.KIND_SHARE and kho.label == "Share (tài khoản chạy tool)"
    assert kho.share_name == ""  # Shared = True là của máy PC02, không phải máy này
    assert kho.problem and "Offline" in kho.status and kho.server == "PC02"

    assert by_name["\\\\PC03\\Ke toan"].kind == manage.KIND_MACHINE and by_name["\\\\PC03\\Ke toan"].problem
    assert by_name["\\\\PC04\\Moi"].status.startswith("Chưa hiện")
    nhan_su = by_name["\\\\PC05\\Nhan su"]
    assert nhan_su.kind == manage.KIND_USER and nhan_su.default
    assert snap.other_user and snap.spooler == "Running" and snap.drivers == ["Contoso PCL6", "Microsoft IPP Class Driver"]


def test_parse_snapshot_handles_single_values():
    data = dict(SNAPSHOT, other_user=False, printers=SNAPSHOT["printers"][2], machine_connections={},
                user_connections="\\\\PC05\\Nhan su", drivers="Contoso PCL6")
    snap = manage.parse_snapshot(data)
    assert [(p.name, p.kind) for p in snap.printers] == [
        ("\\\\PC02\\Kho", manage.KIND_SHARE), ("\\\\PC05\\Nhan su", manage.KIND_SHARE)]
    assert snap.printers[0].label == "Share" and snap.drivers == ["Contoso PCL6"]


def test_driver_choices_add_inbox_drivers_not_installed():
    choices = manage.driver_choices(["Contoso PCL6", "Microsoft IPP Class Driver"])
    assert choices[:2] == [("Contoso PCL6", True), ("Microsoft IPP Class Driver", True)]
    assert ("Generic / Text Only", False) in choices
    assert [name for name, _ in choices].count("Microsoft IPP Class Driver") == 1


def test_snapshot_reads_this_machine(env):
    """Chạy thật script đọc danh sách (chỉ đọc)."""
    snap = manage.snapshot(env)
    assert snap.spooler
    assert all(printer.name for printer in snap.printers)


# ---------------------------------------------------------------- mục thêm / gỡ


def _script(action) -> str:
    step = action.apply[0]
    assert isinstance(step, PowerShellStep)
    return step.script


def test_add_ip_action_quotes_values():
    action = manage.add_ip_action("10.0.0.5", "Máy in O'Brien", "Contoso PCL6", r"D:\Drivers\contoso.inf")
    assert (action.id, action.page, action.admin) == ("prn.add_ip", "printers", True)
    script = _script(action)
    assert "$PrinterName = 'Máy in O''Brien'" in script
    assert r"$InfPath = 'D:\Drivers\contoso.inf'" in script
    assert "Add-Printer -Name $PrinterName" in script
    with pytest.raises(ValueError):
        manage.add_ip_action("10.0.0.5; calc", "x", "Contoso PCL6")
    with pytest.raises(ValueError):
        manage.add_ip_action("10.0.0.5", "a,b", "Contoso PCL6")
    with pytest.raises(ValueError):
        manage.add_ip_action("10.0.0.5", "x", "")


def test_add_share_action():
    script = _script(manage.add_share_action("pc01/HP LaserJet", per_machine=True))
    assert "$SharePath = '\\\\pc01\\HP LaserJet'" in script and "$PerMachine = '1'" in script
    assert "$PerMachine = ''" in _script(manage.add_share_action("\\\\pc01\\HP", per_machine=False))
    with pytest.raises(ValueError):
        manage.add_share_action("\\\\pc01", per_machine=False)


def test_remove_and_test_page_actions():
    printer = manage.Printer("\\\\PC05\\Nhan su", manage.KIND_USER, "Share (người đang đăng nhập)")
    script = _script(manage.remove_action(printer, remove_driver=False))
    assert "$Kind = 'user_share'" in script and "$RemoveDriver = ''" in script
    assert "$TargetUserName" in script  # executor đặt sẵn biến này
    local = manage.Printer("Contoso", manage.KIND_LOCAL, "USB", driver="Contoso PCL6")
    assert "$RemoveDriver = '1'" in _script(manage.remove_action(local, remove_driver=True))
    assert manage.test_page_action(local).id == "prn.test_page"


def generated_scripts() -> list[tuple[str, str]]:
    """Mọi script do trang Máy in dựng ra, để test_scripts soát cú pháp."""
    printer = manage.Printer("\\\\PC05\\Nhan su", manage.KIND_USER, "x")
    actions = [
        manage.add_ip_action("10.0.0.5", "Máy in O'Brien", "Contoso PCL6", r"D:\Drivers\contoso.inf"),
        manage.add_share_action("\\\\pc01\\HP", per_machine=True),
        manage.remove_action(printer, remove_driver=True),
        manage.test_page_action(printer),
    ]
    return [(action.id, _script(action)) for action in actions] + [
        ("printers list", manage.LIST_SCRIPT.read_text(encoding="utf-8"))]
