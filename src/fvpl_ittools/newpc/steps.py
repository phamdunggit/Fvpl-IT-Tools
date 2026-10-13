"""Các mục chạy của wizard Cài máy mới, dựng từ thông tin IT nhập (tên máy, domain, OU...).

Chạy qua executor như mọi mục khác: có log, nút Huỷ, mật khẩu đi qua stdin. Giá trị đặt vào script bằng
shell.ps_quote sau khi đã kiểm tra.
"""

from __future__ import annotations

import re

from ..actions.loader import parse_action
from ..actions.model import Action
from ..core import paths, shell
from . import naming, state

_GROUP = re.compile(r"^[^\\/\"]+\\[^\\/\"]+$")
_OU = re.compile(r"^(?:[A-Za-z]+=[^,]+,)*DC=[^,]+(?:,DC=[^,]+)*$", re.IGNORECASE)

# Mã lỗi hay gặp khi join và cách xử lý. Lời báo của Add-Computer không có sẵn mã lỗi nên dò thêm theo chữ
# (Windows tiếng Anh); không khớp thì in danh sách nguyên nhân hay gặp.
_JOIN = """\
$cs = Get-CimInstance Win32_ComputerSystem
$current = $env:COMPUTERNAME
$sameDomain = [bool]$cs.PartOfDomain -and ($cs.Domain -eq $Domain)
if ($sameDomain -and $current -eq $NewName) {
    Write-Ok ('Máy đã tên {0} và đã ở domain {1}, không cần đổi.' -f $NewName, $Domain)
    exit 0
}
if ($cs.PartOfDomain -and -not $sameDomain) {
    Write-Bad ('Máy đang ở domain khác ({0}). Cho máy ra workgroup trước rồi chạy lại.' -f $cs.Domain)
    exit 3
}
try {
    if ($sameDomain) {
        Rename-Computer -NewName $NewName -DomainCredential $Credential -Force -ErrorAction Stop
        Write-Ok ('Đã đổi tên máy {0} thành {1}.' -f $current, $NewName)
    }
    else {
        $options = @{ DomainName = $Domain; Credential = $Credential; Force = $true; ErrorAction = 'Stop' }
        if ($NewName -ne $current) { $options.NewName = $NewName }
        if ($OUPath) { $options.OUPath = $OUPath }
        Add-Computer @options
        $where = ''
        if ($OUPath) { $where = ', OU ' + $OUPath }
        Write-Ok ('Đã join máy vào domain {0} với tên {1}{2}.' -f $Domain, $NewName, $where)
    }
}
catch {
    $text = [string]$_.Exception.Message
    Write-Bad ('Không join / đổi tên được: {0}' -f $text)
    $code = 0
    if ($text -match '0x([0-9A-Fa-f]{8})') { $code = [Convert]::ToInt32($Matches[1], 16) -band 0xFFFF }
    elseif ($text -match 'already exists|different set of credentials|reuse') { $code = 2224 }
    elseif ($text -match 'user name or password|unknown user name') { $code = 1326 }
    elseif ($text -match 'could not be contacted|does not exist|cannot be found') { $code = 1355 }
    elseif ($text -match 'Access is denied') { $code = 5 }
    elseif ($text -match 'no such object|object does not exist') { $code = 8240 }
    switch ($code) {
        1326 { Write-Warn 'Sai tên hoặc mật khẩu tài khoản join.' }
        1355 { Write-Warn 'Không tìm thấy domain: DNS của card mạng chưa trỏ về DC. Xem bước 0 Kiểm tra trước.' }
        { $_ -in 2224, 2732 } { Write-Warn 'Tên máy đã có trong AD và tài khoản join không được dùng lại computer object đó (KB5020276). Xoá hoặc reset object trong Active Directory Users and Computers, hoặc join bằng tài khoản Domain Admin, hoặc đặt tên khác.' }
        5 { Write-Warn 'Tài khoản join không có quyền tạo máy trong OU này (hoặc đã hết hạn mức 10 máy của tài khoản thường).' }
        8240 { Write-Warn 'OU không đúng: kiểm tra computer_ou trong site.yaml.' }
        default { Write-Warn 'Hay gặp: sai mật khẩu tài khoản join; DNS không trỏ về DC; giờ lệch quá 5 phút; tên máy đã có trong AD (KB5020276); OU sai.' }
    }
    exit 2
}
"""

_RESUME_TASK = """\
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT20S'
# Nhóm Administrators của máy (theo SID, không phụ thuộc ngôn ngữ Windows), chạy bằng quyền cao nhất.
$principal = New-ScheduledTaskPrincipal -GroupId 'S-1-5-32-544' -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$taskAction = New-ScheduledTaskAction -Execute $ResumeProgram -Argument $ResumeArguments
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Ok 'Đã hẹn tool tự mở lại khi một tài khoản admin đăng nhập sau khi khởi động lại.'
"""

_VERIFY = """\
$cs = Get-CimInstance Win32_ComputerSystem
if (-not $cs.PartOfDomain) { Write-Bad 'Máy chưa vào domain. Làm lại bước 2.'; Exit-Checks }
Write-Ok ('Máy {0} đang ở domain {1}.' -f $env:COMPUTERNAME, $cs.Domain)
if ($ExpectedName -and $env:COMPUTERNAME -ne $ExpectedName) {
    Write-Bad ('Tên máy là {0}, chưa phải {1}: có thể chưa khởi động lại sau khi đổi tên.' -f $env:COMPUTERNAME, $ExpectedName)
}
try {
    if (Test-ComputerSecureChannel -ErrorAction Stop) { Write-Ok 'Kênh bảo mật với DC (secure channel) tốt.' }
    else { Write-Bad 'Secure channel với DC hỏng: chạy mục Sửa lỗi trust relationship ở trang Sửa lỗi.' }
}
catch { Write-Bad ('Không kiểm tra được secure channel: {0}' -f $_.Exception.Message) }
Exit-Checks
"""

_IT_ADMINS = """\
$admins = (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')).Translate([Security.Principal.NTAccount]).Value.Split('\\')[-1]
$local = [ADSI]('WinNT://./{0},group' -f $admins)
try {
    $local.Add(('WinNT://{0},group' -f $Group.Replace('\\', '/')))
    Write-Ok ('Đã thêm {0} vào nhóm {1} của máy.' -f $Group, $admins)
}
catch {
    $inner = $_.Exception.InnerException
    if ($inner -and $inner.HResult -eq -2147023518) { Write-Ok ('{0} đã có trong nhóm {1}.' -f $Group, $admins) }
    else { Write-Bad ('Không thêm được {0} vào nhóm {1}: {2}' -f $Group, $admins, $_.Exception.Message); exit 2 }
}
"""

_FINISH = """\
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Ok 'Đã bỏ hẹn tự mở lại tool.'
"""


class StepError(ValueError):
    pass


def valid_ou(text: str) -> bool:
    return not text or bool(_OU.match(text))


def valid_group(text: str) -> bool:
    return bool(_GROUP.match(text))


def _ps(values: dict[str, str], body: str) -> str:
    return shell.ps_variable_lines(values) + body


def join_action(new_name: str, domain: str, ou: str, copy_app: bool | None = None) -> Action:
    """Đổi tên + join domain (một lần khởi động lại), chép tool vào ProgramData, hẹn tự mở lại sau khi khởi động."""
    problem = naming.name_problem(new_name)
    if problem:
        raise StepError(problem)
    if not naming._DOMAIN.match(domain):
        raise StepError("Chưa có tên domain (khai báo domain trong site.yaml).")
    if not valid_ou(ou):
        raise StepError(f"OU không đúng dạng distinguished name: {ou!r}")
    steps: list[dict] = []
    source, target = paths.app_root(), state.app_copy_dir()
    copy_app = paths.is_frozen() if copy_app is None else copy_app
    if copy_app and source.resolve() != target.resolve():
        # Tool có thể đang chạy từ USB / SSD: chép vào máy để mở lại được sau khi khởi động lại.
        steps.append({
            "cmd": f'robocopy "{source}" "{target}" /MIR /XD "{source / "SOFT"}" "{source / "Reports"}" '
                   "/R:1 /W:1 /NFL /NDL /NJH /NP",
            "ok_codes": [0, 1, 2, 3, 4, 5, 6, 7], "timeout": 600,
            "messages": {8: "Có file không chép được", 16: "Lỗi nghiêm trọng khi chép tool vào ProgramData"},
        })
        # Tác vụ mở lại chạy bản chép này bằng quyền admin. Mặc định Users được tạo file trong thư mục con của
        # ProgramData (thả DLL vào là chạy bằng quyền admin), nên chỉ để Administrators, SYSTEM được ghi.
        steps.append({
            "cmd": f'icacls "{target.parent}" /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" '
                   '"*S-1-5-18:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" /C /Q',
            "messages": {5: "Không đổi được quyền thư mục ProgramData\\FVPL-ITTools"},
        })
    steps.append({
        "powershell": _ps({"NewName": new_name.upper(), "Domain": domain, "OUPath": ou}, _JOIN), "timeout": 300,
        "messages": {2: "Không join / đổi tên được, xem gợi ý ở trên", 3: "Máy đang ở domain khác"},
    })
    program, arguments = state.resume_command()
    steps.append({"powershell": _ps({"TaskName": state.RESUME_TASK, "ResumeProgram": program,
                                     "ResumeArguments": arguments}, _RESUME_TASK)})
    return parse_action({
        "id": "newpc.join", "name": f"Đổi tên thành {new_name.upper()} và join domain {domain}",
        "category": "Cài máy mới", "page": "utilities", "risk": "advanced", "reboot": True, "undo": "none",
        "needs_credential": "domain",
        "description": "Bước 2 của wizard Cài máy mới: chép tool vào máy, đổi tên và join domain trong một lần "
                       "khởi động lại, hẹn tool tự mở lại để làm tiếp.",
        "apply": steps,
    })


def verify_action(expected_name: str) -> Action:
    return parse_action({
        "id": "newpc.verify", "name": "Kiểm tra máy đã vào domain và đúng tên", "category": "Cài máy mới",
        "page": "utilities", "description": "Bước 3 của wizard: máy đã ở domain, đúng tên, secure channel tốt.",
        "apply": [{"powershell": _ps({"ExpectedName": expected_name.upper()}, _VERIFY), "timeout": 120,
                   "messages": {2: "Có mục chưa đạt, xem các dòng ✖ ở trên"}}],
    })


def it_admins_action(group: str) -> Action:
    if not valid_group(group):
        raise StepError(f"it_admins_group trong site.yaml phải có dạng DOMAIN\\Tên nhóm: {group!r}")
    return parse_action({
        "id": "newpc.it_admins", "name": f"Thêm {group} vào nhóm Administrators của máy",
        "category": "Cài máy mới", "page": "utilities", "requires_domain": True,
        "description": "Để tài khoản IT trong nhóm này có quyền admin trên máy (PLAN.md mục 5.2, bước 2).",
        "apply": [{"powershell": _ps({"Group": group}, _IT_ADMINS), "messages": {2: "Không thêm được nhóm IT"}}],
    })


def after_restart_actions(expected_name: str, it_group: str, existing: dict[str, Action]) -> list[Action]:
    """Bước 3: kiểm tra join, đồng bộ giờ, cập nhật Group Policy, thêm nhóm IT vào Administrators."""
    actions = [verify_action(expected_name)]
    actions += [existing[action_id] for action_id in ("dom.time_sync", "dom.gpupdate") if action_id in existing]
    if it_group:
        actions.append(it_admins_action(it_group))
    return actions


def finish_action() -> Action:
    return parse_action({
        "id": "newpc.finish", "name": "Kết thúc wizard: bỏ hẹn tự mở lại tool", "category": "Cài máy mới",
        "page": "utilities", "description": "Xoá tác vụ mở lại tool sau khi khởi động lại (bước 2 đã tạo).",
        "apply": [{"powershell": _ps({"TaskName": state.RESUME_TASK}, _FINISH)}],
    })


def generated_scripts() -> list[tuple[str, str]]:
    """Script mẫu của các mục trên, để test soát cú pháp và độ dài."""
    actions = [join_action("FVPL-KT05", "corp.example", "OU=May tram,DC=corp,DC=example", copy_app=False),
               verify_action("FVPL-KT05"), it_admins_action("CORP\\IT Admins"), finish_action()]
    return [(f"{action.id} bước {index}", step.script)
            for action in actions for index, step in enumerate(action.apply, start=1) if hasattr(step, "script")]
