"""
Email notifier for sending hackathon notifications
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from datetime import datetime
from html import escape

from .models import Hackathon


logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends hackathon notifications via email"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender_email: str,
        password: str,
        recipients: List[str],
        use_tls: bool = True,
        subject_prefix: str = "[Hackathon Scout]",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.password = password
        self.recipients = recipients
        self.use_tls = use_tls
        self.subject_prefix = subject_prefix

    def send(self, hackathons: List[Hackathon]) -> bool:
        """Send email with hackathon list"""
        if not hackathons:
            logger.info("No hackathons to send")
            return True

        if not self.recipients:
            logger.warning("No recipients configured")
            return False

        try:
            # Build email content
            subject = f"{self.subject_prefix} {len(hackathons)} New Hackathons"
            html_body = self._build_html_email(hackathons)
            text_body = self._build_text_email(hackathons)

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = ", ".join(self.recipients)

            # Attach both plain text and HTML
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.sender_email, self.password)
                server.send_message(msg)

            logger.info(
                f"Sent email to {len(self.recipients)} recipients with {len(hackathons)} hackathons"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def _format_date(self, dt: datetime) -> str:
        """Format date for display"""
        if dt:
            return dt.strftime("%b %d, %Y")
        return "TBD"

    def _build_html_email(self, hackathons: List[Hackathon]) -> str:
        """Build HTML email body"""

        rows = ""
        for h in hackathons:
            mode_badge = f"""<span style="background: {"#10b981" if h.mode.value == "online" else "#6366f1" if h.mode.value == "hybrid" else "#f59e0b"}; 
                           color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{escape(h.mode.value.upper())}</span>"""

            dates = (
                f"{self._format_date(h.start_date)} - {self._format_date(h.end_date)}"
            )

            rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    <strong style="font-size: 16px; color: #1f2937;">{escape(h.name[:100])}</strong>
                    <br>
                    <span style="color: #6b7280; font-size: 13px;">{escape(h.source.value)}</span>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    {dates}
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    {mode_badge}
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    <a href="{escape(h.url)}" style="color: #2563eb; text-decoration: none; font-size: 13px;">View Details →</a>
                </td>
            </tr>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    background: #f9fafb; margin: 0; padding: 20px;">
            <div style="max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; 
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            padding: 20px; color: white;">
                    <h1 style="margin: 0; font-size: 24px;">🏆 Hackathon Scout</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">{len(hackathons)} upcoming hackathons found</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f3f4f6;">
                            <th style="padding: 12px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase;">Hackathon</th>
                            <th style="padding: 12px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase;">Dates</th>
                            <th style="padding: 12px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase;">Mode</th>
                            <th style="padding: 12px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                
                <div style="padding: 20px; background: #f9fafb; text-align: center; color: #6b7280; font-size: 12px;">
                    <p>Sent by Hackathon Scout • Scraper runs daily</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _build_text_email(self, hackathons: List[Hackathon]) -> str:
        """Build plain text email body"""

        lines = [
            f"🏆 Hackathon Scout - {len(hackathons)} Upcoming Hackathons",
            "=" * 50,
            "",
        ]

        for i, h in enumerate(hackathons, 1):
            lines.append(f"{i}. {h.name}")
            lines.append(f"   Source: {h.source.value}")
            lines.append(
                f"   Dates: {self._format_date(h.start_date)} - {self._format_date(h.end_date)}"
            )
            lines.append(f"   Mode: {h.mode.value}")
            lines.append(f"   URL: {h.url}")
            lines.append("")

        lines.append("-" * 50)
        lines.append("Sent by Hackathon Scout")

        return "\n".join(lines)
