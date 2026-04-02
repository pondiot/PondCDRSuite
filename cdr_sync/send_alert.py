#!/usr/bin/env python3
# send_alert.py - Send alerts via Telegram and/or Email (Microsoft Graph API)

from __future__ import annotations

import argparse
import logging
import os
import sys
from urllib.parse import quote

import requests
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
)


def send_telegram(subject: str, message: str, token: str, chat_id: str) -> bool:
    try:
        # Convert literal \n to actual newlines
        message = message.replace('\\n', '\n')
        text = f"*{subject}*\n\n{message}"
        r = requests.post(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=30,
        )
        if not r.ok:
            logging.error("Telegram API returned %d: %s", r.status_code, r.text)
            return False
        logging.info("Telegram alert sent")
        return True
    except Exception:
        logging.exception("Failed to send Telegram alert")
        return False


def _get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    response = requests.post(
        url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def send_email(
    subject: str,
    message: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    email_from: str,
    email_to: str,
) -> bool:
    try:
        # Convert literal \n to actual newlines
        message = message.replace('\\n', '\n')
        access_token = _get_access_token(tenant_id, client_id, client_secret)

        recipients = [
            {"emailAddress": {"address": addr.strip()}}
            for addr in email_to.split(",")
            if addr.strip()
        ]

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": message,
                },
                "toRecipients": recipients,
            }
        }

        url = f"https://graph.microsoft.com/v1.0/users/{quote(email_from)}/sendMail"
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        logging.info("Email alert sent to %s", email_to)
        return True
    except Exception:
        logging.exception("Failed to send email alert")
        return False


def is_true(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send alerts via Telegram and/or Email")
    parser.add_argument("--subject", required=True, help="Alert subject")
    parser.add_argument("--message", required=True, help="Alert message")
    parser.add_argument("--telegram", default="false", help="Send via Telegram (true/false)")
    parser.add_argument("--email", default="false", help="Send via Email (true/false)")
    args = parser.parse_args()

    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.isfile(env_path):
        load_dotenv(env_path)

    success = True

    if is_true(args.telegram):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env")
            success = False
        else:
            if not send_telegram(args.subject, args.message, token, chat_id):
                success = False

    if is_true(args.email):
        tenant_id = os.getenv("MS_TENANT_ID", "").strip()
        client_id = os.getenv("MS_CLIENT_ID", "").strip()
        client_secret = os.getenv("MS_CLIENT_SECRET", "").strip()
        email_from = os.getenv("EMAIL_FROM", "").strip()
        email_to = os.getenv("EMAIL_TO", "").strip()

        if not tenant_id or not client_id or not client_secret:
            logging.error("MS_TENANT_ID, MS_CLIENT_ID, or MS_CLIENT_SECRET not set in .env")
            success = False
        elif not email_from or not email_to:
            logging.error("EMAIL_FROM or EMAIL_TO not set in .env")
            success = False
        else:
            if not send_email(
                args.subject,
                args.message,
                tenant_id,
                client_id,
                client_secret,
                email_from,
                email_to,
            ):
                success = False

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
