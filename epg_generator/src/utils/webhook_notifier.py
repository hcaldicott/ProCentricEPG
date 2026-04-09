"""
Webhook Notification Utility

This module provides webhook notification support for error reporting to various platforms
including Microsoft Teams, Discord, and Slack.
"""
import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any


class WebhookNotifier:
    """Handles webhook notifications to various platforms."""

    def __init__(self):
        """Initialize webhook notifier with configuration from environment variables."""
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.webhook_type = os.environ.get('WEBHOOK_TYPE', 'auto').lower()
        self.enabled = bool(self.webhook_url)

        if self.enabled:
            # Auto-detect webhook type if not specified
            if self.webhook_type == 'auto':
                self.webhook_type = self._detect_webhook_type(self.webhook_url)
            logging.info(f"Webhook notifications enabled for {self.webhook_type}")
        else:
            logging.debug("Webhook notifications disabled (no WEBHOOK_URL configured)")

    def _detect_webhook_type(self, url: str) -> str:
        """
        Auto-detect webhook type based on URL pattern.

        Args:
            url: The webhook URL

        Returns:
            Detected webhook type (teams, discord, slack, or generic)
        """
        url_lower = url.lower()
        if 'webhook.office.com' in url_lower or 'teams.microsoft.com' in url_lower:
            return 'teams'
        elif 'discord.com' in url_lower or 'discordapp.com' in url_lower:
            return 'discord'
        elif 'hooks.slack.com' in url_lower:
            return 'slack'
        else:
            return 'generic'

    def _format_teams_message(self, title: str, message: str, error_details: Optional[str] = None, severity: str = 'error') -> Dict[str, Any]:
        """
        Format message for Microsoft Teams using Adaptive Cards.

        Args:
            title: Message title
            message: Main message content
            error_details: Optional error details
            severity: Message severity (error, warning, info)

        Returns:
            Formatted Teams message payload with Adaptive Card
        """
        # Build fact set for the adaptive card
        facts = [
            {"title": "Status", "value": severity.upper()},
            {"title": "Timestamp", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
        ]

        # Build card body
        card_body = [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Large",
                "wrap": True
            },
            {
                "type": "TextBlock",
                "text": message,
                "wrap": True,
                "spacing": "Medium"
            },
            {
                "type": "FactSet",
                "facts": facts,
                "spacing": "Medium"
            }
        ]

        if error_details:
            card_body.append({
                "type": "TextBlock",
                "text": "**Details:**",
                "weight": "Bolder",
                "spacing": "Medium"
            })
            card_body.append({
                "type": "TextBlock",
                "text": error_details,
                "wrap": True,
                "fontType": "Monospace",
                "spacing": "Small"
            })

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.4",
                        "body": card_body,
                        "msteams": {
                            "width": "Full"
                        }
                    }
                }
            ]
        }

    def _format_discord_message(self, title: str, message: str, error_details: Optional[str] = None, severity: str = 'error') -> Dict[str, Any]:
        """
        Format message for Discord.

        Args:
            title: Message title
            message: Main message content
            error_details: Optional error details
            severity: Message severity (error, warning, info)

        Returns:
            Formatted Discord message payload
        """
        color_map = {
            'error': 16711680,      # Red
            'warning': 16753920,    # Orange
            'info': 491520          # Blue
        }

        fields = [
            {"name": "Message", "value": message, "inline": False}
        ]

        if error_details:
            # Discord has a 1024 character limit per field, truncate if needed
            truncated_details = error_details[:1000] + "..." if len(error_details) > 1000 else error_details
            fields.append({"name": "Details", "value": f"```\n{truncated_details}\n```", "inline": False})

        return {
            "embeds": [{
                "title": title,
                "color": color_map.get(severity, 16711680),
                "fields": fields,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "ProCentric EPG Generator"}
            }]
        }

    def _format_slack_message(self, title: str, message: str, error_details: Optional[str] = None, severity: str = 'error') -> Dict[str, Any]:
        """
        Format message for Slack.

        Args:
            title: Message title
            message: Main message content
            error_details: Optional error details
            severity: Message severity (error, warning, info)

        Returns:
            Formatted Slack message payload
        """
        color_map = {
            'error': 'danger',
            'warning': 'warning',
            'info': 'good'
        }

        fields = [
            {"title": "Message", "value": message, "short": False}
        ]

        if error_details:
            fields.append({"title": "Details", "value": f"```{error_details}```", "short": False})

        return {
            "attachments": [{
                "color": color_map.get(severity, 'danger'),
                "title": title,
                "fields": fields,
                "footer": "ProCentric EPG Generator",
                "ts": int(datetime.utcnow().timestamp())
            }]
        }

    def _format_generic_message(self, title: str, message: str, error_details: Optional[str] = None, severity: str = 'error') -> Dict[str, Any]:
        """
        Format message for generic webhooks (simple JSON).

        Args:
            title: Message title
            message: Main message content
            error_details: Optional error details
            severity: Message severity (error, warning, info)

        Returns:
            Formatted generic message payload
        """
        payload = {
            "title": title,
            "message": message,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "ProCentric EPG Generator"
        }

        if error_details:
            payload["details"] = error_details

        return payload

    def send_notification(self, title: str, message: str, error_details: Optional[str] = None, severity: str = 'error') -> bool:
        """
        Send notification to configured webhook.

        Args:
            title: Notification title
            message: Main message content
            error_details: Optional error details/stack trace
            severity: Message severity (error, warning, info)

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.enabled:
            logging.debug("Webhook notification skipped (not configured)")
            return False

        # Log the webhook attempt
        logging.info(f"Sending webhook notification - Severity: {severity.upper()}, Title: '{title}'")

        try:
            # Format message based on webhook type
            if self.webhook_type == 'teams':
                payload = self._format_teams_message(title, message, error_details, severity)
            elif self.webhook_type == 'discord':
                payload = self._format_discord_message(title, message, error_details, severity)
            elif self.webhook_type == 'slack':
                payload = self._format_slack_message(title, message, error_details, severity)
            else:
                payload = self._format_generic_message(title, message, error_details, severity)

            # Send webhook request
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )

            response.raise_for_status()
            logging.info(f"✓ Webhook notification sent successfully - Type: {self.webhook_type}, Status: {response.status_code}, Title: '{title}'")
            return True

        except requests.exceptions.Timeout:
            logging.error(f"✗ Webhook notification FAILED - Timeout after 10 seconds - Title: '{title}'")
            return False
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'
            logging.error(f"✗ Webhook notification FAILED - Status: {status_code}, Error: {e}, Title: '{title}'")
            return False
        except Exception as e:
            logging.error(f"✗ Webhook notification FAILED - Unexpected error: {e}, Title: '{title}'")
            return False

    def notify_error(self, error_title: str, error_message: str, exception: Optional[Exception] = None) -> bool:
        """
        Send error notification.

        Args:
            error_title: Error title/summary
            error_message: Error message
            exception: Optional exception object for stack trace

        Returns:
            True if notification was sent successfully, False otherwise
        """
        error_details = None
        if exception:
            error_details = f"{type(exception).__name__}: {str(exception)}"

        return self.send_notification(
            title=error_title,
            message=error_message,
            error_details=error_details,
            severity='error'
        )

    def notify_warning(self, warning_title: str, warning_message: str) -> bool:
        """
        Send warning notification.

        Args:
            warning_title: Warning title/summary
            warning_message: Warning message

        Returns:
            True if notification was sent successfully, False otherwise
        """
        return self.send_notification(
            title=warning_title,
            message=warning_message,
            severity='warning'
        )

    def notify_success(self, title: str, message: str) -> bool:
        """
        Send success notification.

        Args:
            title: Success title/summary
            message: Success message

        Returns:
            True if notification was sent successfully, False otherwise
        """
        return self.send_notification(
            title=title,
            message=message,
            severity='info'
        )
