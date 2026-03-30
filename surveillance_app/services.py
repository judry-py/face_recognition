from __future__ import annotations

import csv
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

try:
    import winsound
except ImportError:
    winsound = None

from .config import AppConfig, resolve_project_path
from .utils import safe_timestamp, timestamp_label


def append_csv_row(file_path: str, fieldnames: list[str], row: dict) -> None:
    path = resolve_project_path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_csv_rows(path_str: str | Path) -> list[dict]:
    path = resolve_project_path(path_str)
    if not path.exists():
        return []

    try:
        with path.open("r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))
    except Exception:
        return []


def alert_beep() -> None:
    if winsound is not None:
        try:
            winsound.Beep(1400, 300)
        except RuntimeError:
            pass


def send_telegram_message(config: AppConfig, text: str) -> tuple[bool, str]:
    if not config.telegram_enabled:
        return False, "Telegram désactivé"
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return False, "Token ou chat_id Telegram manquant"

    try:
        payload = urlencode({"chat_id": config.telegram_chat_id, "text": text}).encode("utf-8")
        with urlopen(
            f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
            data=payload,
            timeout=8,
        ) as response:
            response.read()
        return True, "Notification Telegram envoyée"
    except Exception as exc:
        return False, f"Échec Telegram : {exc}"


def generate_html_report(config: AppConfig) -> str:
    detections = load_csv_rows(config.detections_log)
    alerts = load_csv_rows(config.alerts_log)
    known_count = len({row.get("name") for row in detections if row.get("status") == "reconnu" and row.get("name")})
    unknown_count = sum(1 for row in detections if row.get("status", "").lower() == "inconnu")

    rows_html = "".join(
        f"<tr><td>{row.get('timestamp', '-')}</td><td>{row.get('reason', '-')}</td><td>{row.get('motion_percent', '-')}%</td><td>{row.get('faces_detected', '-')}</td></tr>"
        for row in alerts[-20:]
    )

    html = f"""
    <!doctype html>
    <html lang='fr'>
    <head>
      <meta charset='utf-8'>
      <title>Rapport de surveillance</title>
      <style>
        body {{ font-family: Arial, sans-serif; padding: 24px; background: #f4f7fb; color: #182235; }}
        .card {{ background: white; padding: 16px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,.08); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border-bottom: 1px solid #e0e6ef; padding: 8px; text-align: left; }}
      </style>
    </head>
    <body>
      <h1>Rapport de surveillance</h1>
      <p>Généré le {timestamp_label()}</p>
      <div class='card'>
        <strong>Détections:</strong> {len(detections)}<br>
        <strong>Alertes:</strong> {len(alerts)}<br>
        <strong>Visages inconnus:</strong> {unknown_count}<br>
        <strong>Personnes reconnues:</strong> {known_count}
      </div>
      <div class='card'>
        <h2>Dernières alertes</h2>
        <table>
          <tr><th>Heure</th><th>Raison</th><th>Mouvement</th><th>Visages</th></tr>
          {rows_html}
        </table>
      </div>
    </body>
    </html>
    """

    report_dir = resolve_project_path(config.reports_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"report_{safe_timestamp()}.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path.resolve())


def get_startup_bat_path() -> Path:
    appdata = os.getenv("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "surveillance_app.bat"
