"""Deliver the shortlist: always to a file, optionally by email (SMTP or Resend)."""
import os
import smtplib
from email.message import EmailMessage

from .http import post_json


def send(cfg, subject, md, html_body, log=print):
    n = cfg["notify"]
    method = n["method"]
    if method == "file":
        return True
    if not n["to"]:
        log("notify: no 'to' address in config, so the shortlist was only saved to a file")
        return False
    if method == "smtp":
        user = os.environ.get("SMTP_USER") or n["from"]
        pw = os.environ.get("SMTP_PASSWORD", "")
        if not pw:
            log("notify: SMTP_PASSWORD is not set")
            return False
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, n["from"] or user, n["to"]
        msg.set_content(md)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(n["smtp_host"], int(n["smtp_port"]), timeout=60) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True
    if method == "resend":
        key = os.environ.get("RESEND_API_KEY", "")
        st, d = post_json("https://api.resend.com/emails",
                          {"from": n["from"], "to": [n["to"]], "subject": subject, "html": html_body, "text": md},
                          headers={"Authorization": f"Bearer {key}"})
        if st != 200:
            log(f"notify: Resend answered HTTP {st}")
        return st == 200
    log(f"notify: unknown method '{method}' (use file, smtp or resend)")
    return False
