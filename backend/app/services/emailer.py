"""Envoi de l'email quotidien (digest) via SMTP — mot de passe d'application Gmail conseillé."""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings


def smtp_configured() -> bool:
    return bool(settings.smtp_user and settings.smtp_password and settings.digest_email_to)


def send_email(subject: str, html_body: str) -> None:
    """Envoie un email HTML. Lève une exception en cas d'échec."""
    if not smtp_configured():
        raise RuntimeError("SMTP non configuré (SMTP_USER / SMTP_PASSWORD / DIGEST_EMAIL_TO dans .env)")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = settings.digest_email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
