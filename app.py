"""Compatibility entrypoint for the surveillance application."""
from surveillance_app import (
    AppConfig,
    SurveillanceGUI,
    build_dashboard_url,
    ctk,
    ensure_directories,
    generate_html_report,
    load_config,
    load_csv_rows,
    main,
)

__all__ = [
    "AppConfig",
    "SurveillanceGUI",
    "build_dashboard_url",
    "ctk",
    "ensure_directories",
    "generate_html_report",
    "load_config",
    "load_csv_rows",
    "main",
]

if __name__ == "__main__":
    main()
