"""Compatibility entrypoint for the local surveillance dashboard."""
from surveillance_app.dashboard_web import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
