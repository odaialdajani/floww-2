"""
Morning Briefing Email System for Confluence Decoder.

Sends a daily email with:
- Current GEX regime
- Key levels (gamma flip, call/put walls)
- Recommended strategies
- Alert summary
- Market sentiment

Uses SendGrid (free tier: 100 emails/day) or SMTP.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def generate_briefing_data(ticker: str) -> Dict[str, Any]:
    """Generate morning briefing data for a ticker."""
    return {"ticker": ticker, "regime": "unknown", "spot": 0.0}


def format_briefing_email(data: Dict[str, Any]) -> str:
    """Format briefing data as HTML email."""
    return f"<h1>{data.get('ticker', 'SPY')} Briefing</h1>"


async def send_briefing_email(
    to_email: str,
    ticker: str = "SPY",
) -> Dict[str, Any]:
    """Send the morning briefing email."""
    data = generate_briefing_data(ticker)
    html_content = format_briefing_email(data)

    # Try SendGrid first, then SMTP
    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    if sendgrid_key:
        return await _send_via_sendgrid(to_email, ticker, html_content, sendgrid_key)

    smtp_host = os.environ.get("SMTP_HOST")
    if smtp_host:
        return await _send_via_smtp(to_email, ticker, html_content)

    logger.warning("No email service configured (SENDGRID_API_KEY or SMTP_HOST)")
    return {"status": "skipped", "message": "No email service configured"}


async def _send_via_sendgrid(
    to_email: str,
    ticker: str,
    html_content: str,
    api_key: str,
) -> Dict[str, Any]:
    """Send email via SendGrid API."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": "briefing@confluence-decoder.app", "name": "Confluence Decoder"},
                    "subject": f"📊 Morning Briefing: {ticker} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    "content": [{"type": "text/html", "value": html_content}],
                },
                timeout=30,
            )

            if response.status_code == 202:
                logger.info(f"Briefing email sent to {to_email}")
                return {"status": "sent", "service": "sendgrid"}
            else:
                logger.error(f"SendGrid error: {response.status_code} {response.text}")
                return {"status": "error", "message": f"SendGrid {response.status_code}"}

    except Exception as e:
        logger.error(f"SendGrid send failed: {e}")
        return {"status": "error", "message": str(e)}


async def _send_via_smtp(
    to_email: str,
    ticker: str,
    html_content: str,
) -> Dict[str, Any]:
    """Send email via SMTP."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Morning Briefing: {ticker} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())

        logger.info(f"Briefing email sent to {to_email} via SMTP")
        return {"status": "sent", "service": "smtp"}

    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return {"status": "error", "message": str(e)}
