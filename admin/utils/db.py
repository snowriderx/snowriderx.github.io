"""
DB transaction helpers — centralize commit/rollback/flash logic.

Usage:
    from admin.utils.db import commit_or_flash

    if commit_or_flash("Đã lưu!"):
        return redirect(url_for(...))
    return render_template(...)   # or redirect to index on error
"""

import logging

from flask import flash

from extensions import db

log = logging.getLogger(__name__)


def commit_or_flash(success_msg: str = "Thành công!", action: str = "") -> bool:
    """
    Commit the current session.

    Returns True on success (caller should redirect to success destination).
    Returns False on failure — rolls back, logs the error, flashes danger message.

    Args:
        success_msg: Flash message shown on success.
        action:      Optional label for the log line (e.g. "create Menu 010000").
    """
    try:
        db.session.commit()
        if action:
            log.info("db_commit ok action=%s", action)
        flash(success_msg, "success")
        return True
    except Exception as exc:
        db.session.rollback()
        log.error("db_commit failed action=%s error=%s", action or "?", exc)
        flash(f"Lỗi khi lưu: {exc}", "danger")
        return False
