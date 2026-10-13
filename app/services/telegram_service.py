"""
Telegram alerting and weekly reporting service.
Reuses and enhances original notification logic from GUI_W.py with
database-driven reports and error-safe HTTP requests.
"""

import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import cv2
import requests
import schedule
from app.config import Config


class TelegramService:
    def __init__(self, bot_token=None, chat_id=None, enabled=None):
        self.bot_token = bot_token or Config.BOT_TOKEN
        self.chat_id = chat_id or Config.CHAT_ID
        self.enabled = enabled if enabled is not None else Config.ENABLE_TELEGRAM
        self._scheduler_started = False

    def update_config(self, bot_token=None, chat_id=None, enabled=None):
        if bot_token is not None:
            self.bot_token = bot_token
        if chat_id is not None:
            self.chat_id = chat_id
        if enabled is not None:
            self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str) -> bool:
        """Sends markdown formatted Telegram message."""
        if not self.enabled:
            return False
        if not self.is_configured():
            print("[!] Telegram not configured: BOT_TOKEN or CHAT_ID missing.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                print("[+] Telegram text notification sent.")
                return True
            else:
                print(f"[!] Telegram API error ({r.status_code}): {r.text}")
                return False
        except Exception as e:
            print(f"[!] Telegram message request exception: {e}")
            return False

    def send_photo(self, image_input, caption: str = "PPE Snapshot") -> bool:
        """Sends photo snapshot to Telegram."""
        if not self.enabled:
            return False
        if not self.is_configured():
            return False

        try:
            if isinstance(image_input, (str, Path)):
                img_path = Path(image_input)
                if not img_path.exists():
                    return False
                with open(img_path, "rb") as f:
                    file_bytes = f.read()
            else:
                # Assume OpenCV numpy array
                success, buf = cv2.imencode(".jpg", image_input)
                if not success:
                    return False
                file_bytes = buf.tobytes()

            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            files = {"photo": ("snapshot.jpg", file_bytes, "image/jpeg")}
            data = {
                "chat_id": self.chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            r = requests.post(url, data=data, files=files, timeout=15)
            if r.status_code == 200:
                print("[+] Telegram photo snapshot sent.")
                return True
            else:
                print(f"[!] Telegram sendPhoto failed ({r.status_code}): {r.text}")
                return False
        except Exception as e:
            print(f"[!] Telegram photo error: {e}")
            return False

    def get_weekly_summary_text(self, app=None) -> str:
        """Generates weekly report text from SQLite database."""
        try:
            from app.models.daily_stat import DailyStat
            from app.models.violation import Violation

            seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
            today_str = datetime.utcnow().strftime("%Y-%m-%d")

            stats = DailyStat.query.filter(DailyStat.date >= seven_days_ago).all()
            total_h = sum(s.hardhat_not for s in stats)
            total_v = sum(s.vest_not for s in stats)
            total_m = sum(s.mask_not for s in stats)
            total_g = sum(s.gloves_not for s in stats)
            total_days = len(stats)

            summary = (
                f"📅 *Weekly PPE Non-Compliance Report*\n\n"
                f"🧾 Period: {seven_days_ago} → {today_str}\n\n"
                f"🚫 Hardhat Violations: {total_h}\n"
                f"🚫 Safety Vest Violations: {total_v}\n"
                f"🚫 Mask Violations: {total_m}\n"
                f"🚫 Gloves Violations: {total_g}\n\n"
                f"📈 Total Days Logged: {total_days}\n"
                f"📡 Generated automatically by Protecto.AI PPE Monitoring System."
            )
            return summary
        except Exception as e:
            return f"Error compiling weekly report: {e}"

    def trigger_weekly_report(self, app):
        """Sends the weekly report with Flask application context."""
        with app.app_context():
            text = self.get_weekly_summary_text()
            self.send_message(text)

    def start_weekly_scheduler(self, app):
        """Starts background thread to run scheduled reports."""
        if self._scheduler_started:
            return
        self._scheduler_started = True

        day = Config.WEEKLY_REPORT_DAY.lower()
        time_str = Config.WEEKLY_REPORT_TIME

        job_builder = getattr(schedule.every(), day, schedule.every().sunday)
        job_builder.at(time_str).do(lambda: self.trigger_weekly_report(app))

        def _scheduler_loop():
            while True:
                schedule.run_pending()
                time.sleep(60)

        t = threading.Thread(target=_scheduler_loop, daemon=True, name="TelegramScheduler")
        t.start()
        print(f"[+] Weekly report scheduled every {day.capitalize()} at {time_str}.")


# Global service instance
telegram_service = TelegramService()
