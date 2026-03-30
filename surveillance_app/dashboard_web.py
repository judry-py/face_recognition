from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template_string, send_from_directory

from .config import build_dashboard_url, load_config, resolve_project_path
from .logging_utils import get_logger, setup_logging
from .services import load_csv_rows

LOGGER = get_logger(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <title>Dashboard Surveillance</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #101826; color: #f5f7fb; }
    .container { max-width: 1240px; margin: 0 auto; padding: 20px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .card { background: #182235; padding: 16px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.2); }
    .value { font-size: 28px; font-weight: bold; margin-top: 8px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 18px; }
    .panel { background: #182235; padding: 16px; border-radius: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px; border-bottom: 1px solid #2d3a52; text-align: left; font-size: 14px; }
    .gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; }
    .gallery-item { background: #182235; padding: 10px; border-radius: 12px; }
    img { width: 100%; border-radius: 8px; display: block; }
    a { color: #75c2ff; text-decoration: none; }
    .muted { color: #b8c2d6; }
    ul { padding-left: 18px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="container">
    <h1>📊 Dashboard de surveillance</h1>
    <p class="muted">Vue locale du système de surveillance faciale, mouvement, vidéos et rapports.</p>

    <div class="cards">
      <div class="card"><div>Détections totales</div><div class="value">{{ total_detections }}</div></div>
      <div class="card"><div>Alertes totales</div><div class="value">{{ total_alerts }}</div></div>
      <div class="card"><div>Visages inconnus</div><div class="value">{{ unknown_detections }}</div></div>
      <div class="card"><div>Personnes reconnues</div><div class="value">{{ known_people }}</div></div>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>Dernières détections</h2>
        <table>
          <tr><th>Heure</th><th>Nom</th><th>Confiance</th><th>Statut</th></tr>
          {% for row in latest_detections %}
          <tr>
            <td>{{ row.get('timestamp', '-') }}</td>
            <td>{{ row.get('name', '-') }}</td>
            <td>{{ row.get('confidence', '-') }}</td>
            <td>{{ row.get('status', '-') }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>

      <div class="panel">
        <h2>Dernières alertes</h2>
        <table>
          <tr><th>Heure</th><th>Raison</th><th>Mouvement</th><th>Visages</th></tr>
          {% for row in latest_alerts %}
          <tr>
            <td>{{ row.get('timestamp', '-') }}</td>
            <td>{{ row.get('reason', '-') }}</td>
            <td>{{ row.get('motion_percent', '-') }}%</td>
            <td>{{ row.get('faces_detected', '-') }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>Rapports récents</h2>
        <ul>
          {% for report in reports %}
          <li><a href="{{ report.url }}" target="_blank">{{ report.name }}</a></li>
          {% else %}
          <li>Aucun rapport généré pour le moment.</li>
          {% endfor %}
        </ul>
      </div>

      <div class="panel">
        <h2>Vidéos d'alerte</h2>
        <ul>
          {% for video in videos %}
          <li><a href="{{ video.url }}" target="_blank">{{ video.name }}</a></li>
          {% else %}
          <li>Aucune vidéo enregistrée pour le moment.</li>
          {% endfor %}
        </ul>
      </div>
    </div>

    <h2 style="margin-top: 20px;">Captures récentes</h2>
    <div class="gallery">
      {% for image in gallery_images %}
      <div class="gallery-item">
        <a href="{{ image.url }}" target="_blank"><img src="{{ image.url }}" alt="capture"></a>
        <div style="margin-top: 8px; font-size: 13px;">{{ image.name }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</body>
</html>
"""


def latest_files(folder_name: str, patterns: tuple[str, ...], limit: int = 12) -> list[dict]:
    folder = resolve_project_path(folder_name)
    if not folder.exists():
        return []

    all_files = []
    for pattern in patterns:
        all_files.extend(folder.glob(pattern))

    files = sorted(all_files, key=lambda item: item.stat().st_mtime, reverse=True)[:limit]
    return [{"name": file_path.name, "url": f"/media/{Path(folder_name).name}/{file_path.name}"} for file_path in files]


def create_dashboard_app() -> Flask:
    config = load_config()
    app = Flask(__name__)

    @app.route("/media/<folder>/<path:filename>")
    def media(folder: str, filename: str):
        allowed = {
            Path(config.alerts_dir).name: resolve_project_path(config.alerts_dir),
            Path(config.captures_dir).name: resolve_project_path(config.captures_dir),
            Path(config.reports_dir).name: resolve_project_path(config.reports_dir),
        }
        if folder not in allowed:
            return "Not found", 404
        return send_from_directory(str(allowed[folder]), filename)

    @app.route("/api/status")
    def api_status():
        detections = load_csv_rows(config.detections_log)
        alerts = load_csv_rows(config.alerts_log)
        unknown_count = sum(1 for row in detections if row.get("status", "").lower() == "inconnu")
        known_people = len({row.get("name") for row in detections if row.get("status") == "reconnu" and row.get("name")})
        return jsonify(
            {
                "total_detections": len(detections),
                "total_alerts": len(alerts),
                "unknown_detections": unknown_count,
                "known_people": known_people,
                "dashboard_url": build_dashboard_url(config),
            }
        )

    @app.route("/")
    def index():
        detections = load_csv_rows(config.detections_log)
        alerts = load_csv_rows(config.alerts_log)
        unknown_count = sum(1 for row in detections if row.get("status", "").lower() == "inconnu")
        known_people = len({row.get("name") for row in detections if row.get("status") == "reconnu" and row.get("name")})

        return render_template_string(
            HTML_TEMPLATE,
            total_detections=len(detections),
            total_alerts=len(alerts),
            unknown_detections=unknown_count,
            known_people=known_people,
            latest_detections=list(reversed(detections[-10:])),
            latest_alerts=list(reversed(alerts[-10:])),
            gallery_images=latest_files(config.alerts_dir, ("*.jpg",)) + latest_files(config.captures_dir, ("*.jpg",)),
            videos=latest_files(config.alerts_dir, ("*.avi", "*.mp4"), limit=10),
            reports=latest_files(config.reports_dir, ("*.html",), limit=10),
        )

    return app


app = create_dashboard_app()


def main() -> None:
    setup_logging()
    config = load_config()
    LOGGER.info("Dashboard local disponible sur %s", build_dashboard_url(config))
    print(f"Dashboard local disponible sur {build_dashboard_url(config)}")
    app.run(host=config.dashboard_host, port=int(config.dashboard_port), debug=False)
