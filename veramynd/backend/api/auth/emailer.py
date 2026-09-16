"""SMTP helpers for verification + password reset emails."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("veramynd.auth.email")


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    cfg = settings()
    host = str(cfg["smtp_host"])
    user = str(cfg["smtp_user"])
    password = str(cfg["smtp_password"])
    if not host or not user or not password:
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = str(cfg["smtp_from"])
    msg["To"] = to_email
    msg.set_content(text_body or subject)
    msg.add_alternative(html_body, subtype="html")

    port = int(cfg["smtp_port"])
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if cfg["smtp_use_tls"]:
            smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    log.info("Sent email to %s (%s)", to_email, subject)


def send_verification_email(to_email: str, name: str, verify_url: str) -> None:
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0b3d34">
      <h2 style="margin:0 0 12px">Verify your Veramynd account</h2>
      <p>Hi {name},</p>
      <p>Thanks for signing up. Confirm your email to activate your account:</p>
      <p style="margin:24px 0">
        <a href="{verify_url}" style="background:#20b898;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:600">
          Verify email
        </a>
      </p>
      <p style="color:#5f726c;font-size:13px">Or open this link:<br/>{verify_url}</p>
    </div>
    """
    send_email(to_email, "Verify your Veramynd email", html, f"Verify your email: {verify_url}")


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> None:
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0b3d34">
      <h2 style="margin:0 0 12px">Reset your password</h2>
      <p>Hi {name},</p>
      <p>We received a request to reset your Veramynd password:</p>
      <p style="margin:24px 0">
        <a href="{reset_url}" style="background:#20b898;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:600">
          Reset password
        </a>
      </p>
      <p style="color:#5f726c;font-size:13px">If you did not request this, you can ignore this email.</p>
    </div>
    """
    send_email(to_email, "Reset your Veramynd password", html, f"Reset password: {reset_url}")
