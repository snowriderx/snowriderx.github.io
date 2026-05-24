"""
Central middleware registration for Flask app.

Usage in create_app():
    from admin.utils.middleware import register_middleware
    register_middleware(app)
"""

import logging
import time

from flask import Flask, g, redirect, request

log = logging.getLogger(__name__)


def _redirect_301(app: Flask) -> None:
    """
    301 redirect middleware — mirrors VB Default.aspx.vb logic.
    Skips /admin and /static to avoid overhead on internal requests.

    DB index recommended:
      CREATE INDEX ix_tblURL_active_old ON tblURL (Url_Ac, Url_Old)
    """
    @app.before_request
    def _url_redirect_hook():
        path = request.path
        if path.startswith("/admin") or path.startswith("/static"):
            return None

        from models.url_redirect import find_redirect
        new_url = find_redirect(path, request.url)
        if new_url:
            return redirect(new_url, 301)
        return None


def _request_logging(app: Flask) -> None:
    """Log every request: method, path, status, duration, user, IP."""

    def _before():
        g._request_start = time.monotonic()

    def _after(response):
        if request.path.startswith("/static"):
            return response
        duration_ms = int((time.monotonic() - getattr(g, "_request_start", time.monotonic())) * 1000)
        try:
            from flask_login import current_user
            user = current_user.username if current_user.is_authenticated else "-"
        except Exception:
            user = "-"
        log.info(
            "%s %s %s %dms user=%s ip=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            user,
            request.remote_addr or "-",
        )
        return response

    def _teardown(exc):
        if exc is not None:
            log.error(
                "Unhandled exception during %s %s: %s",
                request.method,
                request.path,
                exc,
                exc_info=exc,
            )
            try:
                from extensions import db
                db.session.rollback()
            except Exception:
                pass

    app.before_request(_before)
    app.after_request(_after)
    app.teardown_request(_teardown)


def register_middleware(app: Flask) -> None:
    """Register all middleware hooks onto the app."""
    _redirect_301(app)
    _request_logging(app)
