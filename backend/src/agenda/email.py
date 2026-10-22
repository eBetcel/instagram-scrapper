"""Envio de e-mail (link mágico). Em desenvolvimento, o SMTP é o Mailpit do compose."""

import smtplib
from email.message import EmailMessage
from typing import Protocol

from agenda.config import ConfigApi


class EnviadorEmail(Protocol):
    def enviar(self, para: str, assunto: str, texto: str) -> None: ...


class SmtpEnviador:
    def __init__(self, config: ConfigApi):
        self.config = config

    def enviar(self, para: str, assunto: str, texto: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.config.email_remetente, para, assunto
        msg.set_content(texto)
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_porta, timeout=10) as smtp:
            if self.config.smtp_tls:
                smtp.starttls()
            if self.config.smtp_usuario:
                smtp.login(self.config.smtp_usuario, self.config.smtp_senha.get_secret_value())
            smtp.send_message(msg)


class FakeEnviador:
    def __init__(self) -> None:
        self.enviados: list[tuple[str, str, str]] = []

    def enviar(self, para: str, assunto: str, texto: str) -> None:
        self.enviados.append((para, assunto, texto))
