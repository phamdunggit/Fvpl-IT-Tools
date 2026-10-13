"""Hộp thoại nhập tài khoản domain cho các mục `needs_credential: domain`.

Mật khẩu chỉ được giữ trong RAM cho một lượt chạy, không ghi vào file, config hay log (PLAN.md mục 6.7).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


def qualify_user(user: str, domain: str) -> str:
    """Thêm tiền tố DOMAIN\\ nếu IT chỉ gõ tên tài khoản."""
    user = user.strip()
    if not user or "\\" in user or "@" in user or not domain:
        return user
    return f"{domain}\\{user}"


class CredentialDialog(QDialog):
    def __init__(self, action_names: list[str], domain: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.domain = domain
        self.result_credential: tuple[str, str] | None = None
        self.setWindowTitle("Tài khoản domain")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        names = "\n".join(f"• {name}" for name in action_names)
        intro = QLabel(
            f"Các mục sau cần một tài khoản domain có quyền trên computer account của máy này:\n{names}\n\n"
            "Mật khẩu chỉ dùng cho lượt chạy này: không lưu vào file, không ghi vào log."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.user = QLineEdit()
        self.user.setPlaceholderText(f"{domain}\\tên_tài_khoản" if domain else "DOMAIN\\tên_tài_khoản")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Tài khoản", self.user)
        form.addRow("Mật khẩu", self.password)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Chạy")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.user.textChanged.connect(self._update)
        self.password.textChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        ok = bool(self.user.text().strip()) and bool(self.password.text())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def credential(self) -> tuple[str, str]:
        return qualify_user(self.user.text(), self.domain), self.password.text()

    def done(self, result: int) -> None:
        # Lấy tài khoản ra rồi xoá ô mật khẩu, không để mật khẩu nằm lại trong widget.
        self.result_credential = self.credential() if result else None
        self.password.clear()
        super().done(result)


def ask_credential(action_names: list[str], domain: str, parent: QWidget | None = None) -> tuple[str, str] | None:
    dialog = CredentialDialog(action_names, domain, parent)
    dialog.exec()
    return dialog.result_credential
