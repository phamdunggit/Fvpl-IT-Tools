"""Dựng mục cài đặt cho từng ứng dụng để chạy bằng executor (log, huỷ, timeout, hỏi restart dùng chung).

- winget: `winget install --id … --exact --silent`, chỉ lấy từ nguồn winget.
- share MSI: `msiexec /i … /qn /norestart`, ghi log MSI riêng; gặp mã 1618 (đang có bộ cài khác) thì chờ và thử lại.
- share EXE: chạy bộ cài với tham số im lặng khai báo trong apps.yaml.
- share portable: chép thư mục vào Program Files, tạo shortcut trong Start Menu (và Startup nếu autostart).

Bộ cài thường là chương trình giao diện: gọi thẳng trong PowerShell thì không chờ, nên dùng Start-Process rồi
WaitForExit (không dùng -Wait vì nó chờ cả tiến trình con, mà nhiều bộ cài mở luôn ứng dụng sau khi cài xong).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..actions.model import Action, CmdStep, PowerShellStep
from ..core import shell
from .catalog import App, expand

WINGET_OK = (0, 0x8A15002B, 0x8A150061, 0x8A15010D)  # cài xong / đã có sẵn, không có bản mới hơn
WINGET_REBOOT = (3010, 1641, 0x8A150109)
WINGET_MESSAGES = {
    0x8A150014: "winget không tìm thấy gói này (kiểm tra winget_id trong apps.yaml)",
    0x8A150010: "Gói không có bản cài hợp với máy này",
    0x8A150011: "File cài tải về sai mã băm, thử lại sau hoặc báo lỗi cho người đóng gói",
    0x8A150008: "Tải bộ cài lỗi, kiểm tra Internet hoặc proxy",
    0x8A150107: "Bộ cài cần Internet",
    0x8A150102: "Đang có bộ cài khác chạy, thử lại sau",
    0x8A15003A: "GPO đang chặn winget",
    0x8A15010F: "Chính sách công ty chặn cài ứng dụng này",
    0x8A150056: "Bộ cài không cho chạy bằng quyền admin",
    0x8A150049: "Bộ cài MSI của gói bị lỗi",
    0x8A15010A: "Cần khởi động lại máy rồi cài lại",
    0x8A150046: "Chưa chấp nhận điều khoản của nguồn winget",
}
SHARE_REBOOT = (3010, 1641)
SHARE_MESSAGES = {
    20: "Không thấy bộ cài trên share (sai đường dẫn trong apps.yaml hoặc không vào được share)",
    21: "Đã chép nhưng không thấy file chạy chính, kiểm tra 'exe' trong apps.yaml",
    22: "Mount ISO được nhưng không thấy ổ đĩa của ISO; thử chép ISO về máy hoặc giải nén ra thư mục",
    1603: "Bộ cài báo lỗi nghiêm trọng (1603), xem file log MSI trong thư mục logs",
    1618: "Đang có bộ cài khác chạy, đã thử lại 3 lần",
    1619: "Không mở được file cài (1619)",
    1625: "Chính sách công ty chặn cài đặt (1625)",
}
ROBOCOPY_MESSAGES = {8: "Có file không chép được (ứng dụng đang mở?)", 16: "Lỗi nghiêm trọng khi chép file"}


@dataclass(frozen=True)
class SoftwareEnv:
    """Những gì cần biết về máy để quyết định ứng dụng nào cài được."""
    is_admin: bool
    runs_as_other_user: bool
    winget: str | None
    share_root: str
    share_ok: bool
    missing: frozenset[str] = frozenset()  # id ứng dụng share không thấy bộ cài


def blocked_reason(app: App, senv: SoftwareEnv) -> str | None:
    if not senv.is_admin:
        return "Cần mở tool bằng quyền admin"
    if app.source == "winget" and not senv.winget:
        return "Chưa có winget cho tài khoản đang chạy tool: chạy mục Sửa / cài lại winget ở trang Sửa lỗi"
    if app.source == "share":
        if not senv.share_root:
            return ("Chưa có kho bộ cài: chép thư mục SOFT cạnh tool (bản SSD) "
                    "hoặc khai báo share_root trong site.yaml (bản USB)")
        if not senv.share_ok:
            return f"Không vào được kho bộ cài {senv.share_root}"
        if app.id in senv.missing:
            return "Không thấy bộ cài trên share"
    if app.scope == "user" and senv.runs_as_other_user:
        return "Ứng dụng cài theo người dùng; tool đang chạy bằng tài khoản khác nên sẽ cài nhầm tài khoản"
    return None


def winget_command(app: App) -> str:
    return (
        f"winget install --id {app.winget_id} --exact --source winget --silent "
        "--accept-package-agreements --accept-source-agreements --disable-interactivity"
    )


def _safe_file_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", text).strip() or "app"


_RUN_INSTALLER = """\
for ($try = 1; ; $try++) {
    if ($arguments) { $process = Start-Process -FilePath $program -ArgumentList $arguments -WorkingDirectory $folder -PassThru }
    else { $process = Start-Process -FilePath $program -WorkingDirectory $folder -PassThru }
    $null = $process.Handle  # giữ handle để đọc được ExitCode sau khi tiến trình thoát
    $process.WaitForExit()
    $code = $process.ExitCode
    if ($code -ne 1618 -or $try -ge 3) { break }
    Write-Output 'Đang có bộ cài khác chạy (mã 1618), chờ 30 giây rồi thử lại…'
    Start-Sleep -Seconds 30
}
"""


def msi_script(app: App, share_root: str) -> str:
    return (
        f"$file = {shell.ps_quote(expand(app.installer, share_root))}\n"
        "if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { exit 20 }\n"
        f"$log = Join-Path $LogDir ('msi_{app.id}_{{0:yyyyMMdd_HHmmss}}.log' -f (Get-Date))\n"
        "$program = Join-Path $env:SystemRoot 'System32\\msiexec.exe'\n"
        "$folder = Split-Path -Parent $file\n"
        "$arguments = '/i \"{0}\" /qn /norestart /l*v \"{1}\"' -f $file, $log\n"
        f"$extra = {shell.ps_quote(expand(app.args, share_root))}\n"
        "if ($extra) { $arguments += ' ' + $extra }\n"
        "Write-Output \"msiexec $arguments\"\n"
        + _RUN_INSTALLER
        + "Write-Output \"Log cài đặt: $log\"\nexit $code"
    )


def exe_script(app: App, share_root: str) -> str:
    return (
        f"$program = {shell.ps_quote(expand(app.installer, share_root))}\n"
        "if (-not (Test-Path -LiteralPath $program -PathType Leaf)) { exit 20 }\n"
        "$folder = Split-Path -Parent $program\n"
        f"$arguments = {shell.ps_quote(expand(app.args, share_root))}\n"
        "Write-Output \"$program $arguments\"\n"
        + _RUN_INSTALLER
        + "exit $code"
    )


def iso_script(app: App, share_root: str) -> str:
    """Mount ISO, chạy bộ cài bên trong, rồi tháo ISO ra (kể cả khi bộ cài lỗi)."""
    indented = "".join(f"        {line}\n" for line in _RUN_INSTALLER.splitlines())
    return (
        f"$image = {shell.ps_quote(expand(app.installer, share_root))}\n"
        "if (-not (Test-Path -LiteralPath $image -PathType Leaf)) { exit 20 }\n"
        "# ISO đang được mount sẵn (IT tự mở) thì dùng luôn và để nguyên khi xong.\n"
        "$mountedBefore = [bool](Get-DiskImage -ImagePath $image).Attached\n"
        "if (-not $mountedBefore) { Write-Output \"Mount $image…\"; Mount-DiskImage -ImagePath $image | Out-Null }\n"
        "$code = 0\n"
        "try {\n"
        "    $letter = (Get-DiskImage -ImagePath $image | Get-Volume).DriveLetter\n"
        "    if (-not $letter) { $code = 22 }\n"
        "    else {\n"
        "        $folder = \"${letter}:\\\"\n"
        f"        $program = Join-Path $folder {shell.ps_quote(app.setup)}\n"
        f"        $arguments = {shell.ps_quote(expand(app.args, share_root))}\n"
        "        Write-Output \"$program $arguments\"\n"
        + indented
        + "    }\n"
        "}\n"
        "finally {\n"
        "    if (-not $mountedBefore) { Dismount-DiskImage -ImagePath $image | Out-Null }\n"
        "}\n"
        "exit $code"
    )


def portable_script(app: App, share_root: str) -> str:
    links = [f"(Join-Path $programs {shell.ps_quote(_safe_file_name(app.name) + '.lnk')})"]
    if app.autostart:
        links.append(f"(Join-Path $programs {shell.ps_quote('StartUp\\' + _safe_file_name(app.name) + '.lnk')})")
    return (
        f"$source = {shell.ps_quote(expand(app.installer, share_root))}\n"
        "if (-not (Test-Path -LiteralPath $source -PathType Container)) { exit 20 }\n"
        f"$target = Join-Path $env:ProgramFiles {shell.ps_quote(app.install_folder)}\n"
        "Write-Output \"Chép $source vào $target…\"\n"
        "robocopy $source $target /E /R:1 /W:1 /NP /NFL /NDL /NJH /NJS\n"
        "# robocopy: mã dưới 8 là chép được\n"
        "if ($LASTEXITCODE -ge 8) { exit $LASTEXITCODE }\n"
        f"$exePath = Join-Path $target {shell.ps_quote(app.exe)}\n"
        "if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { exit 21 }\n"
        "$programs = Join-Path $env:ProgramData 'Microsoft\\Windows\\Start Menu\\Programs'\n"
        "$shell = New-Object -ComObject WScript.Shell\n"
        f"foreach ($path in @({', '.join(links)})) {{\n"
        "    $link = $shell.CreateShortcut($path)\n"
        "    $link.TargetPath = $exePath\n"
        "    $link.WorkingDirectory = $target\n"
        "    $link.Save()\n"
        "    Write-Output \"Tạo shortcut: $path\"\n"
        "}\n"
        "exit 0"
    )


def install_action(app: App, share_root: str) -> Action:
    timeout = float(app.timeout)
    if app.source == "winget":
        step = CmdStep(
            command=winget_command(app), timeout=timeout, ok_codes=WINGET_OK, reboot_codes=WINGET_REBOOT,
            messages=tuple(WINGET_MESSAGES.items()),
        )
    elif app.type == "portable":
        step = PowerShellStep(
            script=portable_script(app, share_root), timeout=timeout, ok_codes=(0,), reboot_codes=(),
            messages=tuple((SHARE_MESSAGES | ROBOCOPY_MESSAGES).items()),
        )
    else:
        builders = {"msi": msi_script, "iso": iso_script}
        script = builders.get(app.type, exe_script)(app, share_root)
        step = PowerShellStep(
            script=script, timeout=timeout, ok_codes=(0,), reboot_codes=SHARE_REBOOT,
            messages=tuple(SHARE_MESSAGES.items()),
        )
    description = app.description or f"Cài {app.name} từ {app.source_label}."
    return Action(
        id=f"app.{app.id}", name=f"Cài {app.name}", category=app.group, apply=(step,),
        page="utilities", description=description,
    )
