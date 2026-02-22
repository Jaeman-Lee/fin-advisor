#!/usr/bin/env python3
"""Email report sender for portfolio monitoring.

Sends analysis results via SMTP. Works with Gmail, Naver, or any SMTP provider.

Environment variables:
    SMTP_SERVER   - SMTP host (default: smtp.gmail.com)
    SMTP_PORT     - SMTP port (default: 587)
    SMTP_USERNAME - sender email address
    SMTP_PASSWORD - sender password / app password
    EMAIL_TO      - recipient (default: jaeman1118@naver.com)

Usage:
    # Send a report file
    python scripts/send_report.py --subject "Daily Report" --body-file data/daily_logs/daily_20260222.md

    # Send quick scan alert (from stdin/string)
    python scripts/quick_scan.py --no-color | python scripts/send_report.py --subject "Trigger Alert" --stdin

    # Send with attachment
    python scripts/send_report.py --subject "Daily Report" --body-file report.md --attach report.md
"""

import argparse
import html
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

DEFAULT_TO = "jaeman1118@naver.com"
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


def get_smtp_config() -> dict:
    """Read SMTP configuration from environment variables."""
    server = os.environ.get("SMTP_SERVER", DEFAULT_SMTP_SERVER)
    port = int(os.environ.get("SMTP_PORT", DEFAULT_SMTP_PORT))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    to_addr = os.environ.get("EMAIL_TO", DEFAULT_TO)

    if not username or not password:
        print("ERROR: SMTP_USERNAME and SMTP_PASSWORD environment variables required.", file=sys.stderr)
        sys.exit(2)

    return {
        "server": server,
        "port": port,
        "username": username,
        "password": password,
        "to": to_addr,
    }


def markdown_to_html(md: str) -> str:
    """Lightweight markdown → HTML conversion (no external deps)."""
    lines = md.split("\n")
    html_lines = []
    in_table = False
    in_code = False
    table_header_done = False

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code:
                html_lines.append("</pre>")
                in_code = False
            else:
                html_lines.append("<pre style='background:#f4f4f4;padding:10px;border-radius:4px;font-size:13px;'>")
                in_code = True
            continue
        if in_code:
            html_lines.append(html.escape(line))
            continue

        # Tables
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # Skip separator rows
            if all(re.match(r'^[-:]+$', c) for c in cells):
                table_header_done = True
                continue
            if not in_table:
                html_lines.append("<table style='border-collapse:collapse;width:100%;margin:8px 0;'>")
                in_table = True
            tag = "th" if not table_header_done else "td"
            style = "border:1px solid #ddd;padding:6px 10px;text-align:left;"
            if tag == "th":
                style += "background:#f0f0f0;font-weight:bold;"
            row = "".join(f"<{tag} style='{style}'>{_inline_format(c)}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            html_lines.append("</table>")
            in_table = False
            table_header_done = False

        # Headers
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            sizes = {1: "22px", 2: "18px", 3: "15px"}
            html_lines.append(f"<h{level} style='font-size:{sizes[level]};margin:16px 0 8px;'>{m.group(2)}</h{level}>")
            continue

        # Horizontal rule
        if line.strip() in ("---", "***", "___"):
            html_lines.append("<hr style='border:1px solid #ddd;margin:16px 0;'>")
            continue

        # List items
        m = re.match(r'^(\s*)-\s+(.*)', line)
        if m:
            html_lines.append(f"<li style='margin:2px 0;'>{_inline_format(m.group(2))}</li>")
            continue

        # Emphasis / italic line
        if line.strip().startswith("*") and line.strip().endswith("*") and not line.strip().startswith("**"):
            text = line.strip().strip("*")
            html_lines.append(f"<p style='color:#666;font-style:italic;font-size:12px;'>{text}</p>")
            continue

        # Regular paragraph
        if line.strip():
            html_lines.append(f"<p style='margin:4px 0;'>{_inline_format(line)}</p>")
        else:
            html_lines.append("<br>")

    if in_table:
        html_lines.append("</table>")

    body = "\n".join(html_lines)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,Arial,sans-serif;max-width:700px;margin:0 auto;padding:16px;color:#333;font-size:14px;line-height:1.6;">
{body}
</body></html>"""


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting (bold, links, code)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`(.+?)`', r'<code style="background:#f4f4f4;padding:1px 4px;border-radius:3px;">\1</code>', text)
    # Color P&L values
    text = re.sub(r'(\+\$[\d,.]+)', r'<span style="color:#16a34a">\1</span>', text)
    text = re.sub(r'(\+[\d.]+%)', r'<span style="color:#16a34a">\1</span>', text)
    text = re.sub(r'(-\$[\d,.]+)', r'<span style="color:#dc2626">\1</span>', text)
    text = re.sub(r'(-[\d.]+%)', r'<span style="color:#dc2626">\1</span>', text)
    return text


def send_email(config: dict, subject: str, body_text: str, body_html: str,
               attachments: list[str] | None = None):
    """Send email via SMTP with TLS."""
    msg = MIMEMultipart("alternative")
    msg["From"] = config["username"]
    msg["To"] = config["to"]
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Attachments
    if attachments:
        # Switch to mixed multipart for attachments
        outer = MIMEMultipart("mixed")
        outer["From"] = msg["From"]
        outer["To"] = msg["To"]
        outer["Subject"] = msg["Subject"]
        outer.attach(msg)

        for filepath in attachments:
            path = Path(filepath)
            if not path.exists():
                print(f"WARNING: Attachment not found: {filepath}", file=sys.stderr)
                continue
            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={path.name}")
            outer.attach(part)
        msg = outer

    try:
        with smtplib.SMTP(config["server"], config["port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["username"], config["password"])
            server.sendmail(config["username"], [config["to"]], msg.as_string())
        print(f"Email sent to {config['to']}: {subject}")
    except smtplib.SMTPAuthenticationError:
        print("ERROR: SMTP authentication failed. Check SMTP_USERNAME/SMTP_PASSWORD.", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}", file=sys.stderr)
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Send portfolio report via email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body-file", help="Read body from markdown file")
    parser.add_argument("--body", help="Body as string")
    parser.add_argument("--stdin", action="store_true", help="Read body from stdin")
    parser.add_argument("--attach", nargs="*", help="File(s) to attach")
    args = parser.parse_args()

    config = get_smtp_config()

    # Read body
    if args.body_file:
        body_text = Path(args.body_file).read_text(encoding="utf-8")
    elif args.stdin:
        body_text = sys.stdin.read()
    elif args.body:
        body_text = args.body
    else:
        print("ERROR: Provide --body-file, --body, or --stdin", file=sys.stderr)
        sys.exit(1)

    body_html = markdown_to_html(body_text)
    send_email(config, args.subject, body_text, body_html, args.attach)


if __name__ == "__main__":
    main()
