"""
URL Redirect blueprint — CRUD for tblURL (301 redirect rules).

VB equivalent: link.aspx / link.aspx.vb

URL pattern:
  GET/POST /admin/urlredirect/          list + batch update/delete
  GET/POST /admin/urlredirect/new       create
  GET/POST /admin/urlredirect/<id>/edit edit
  POST     /admin/urlredirect/<id>/delete delete
"""

import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from admin.blueprints.urlredirect import bp
from extensions import db, limiter
from models.url_redirect import UrlRedirect
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash

log = logging.getLogger(__name__)


@bp.before_request
def _guard():
    return super_admin_redirect()


def _parse_form(record: UrlRedirect) -> None:
    record.old_url = request.form.get("old_url", "").strip()[:255] or None
    record.new_url = request.form.get("new_url", "").strip()[:255] or None
    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1
    try:
        record.url_type = int(request.form.get("url_type", 0))
    except (ValueError, TypeError):
        record.url_type = 0


@bp.route("/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    if request.method == "POST":
        action = request.form.get("_action", "update")

        if action == "update":
            row_ids = request.form.getlist("row_id")
            updated = 0
            for rid in row_ids:
                try:
                    rec = db.session.get(UrlRedirect, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec is None:
                    continue
                rec.old_url = request.form.get(f"old_{rid}", rec.old_url or "").strip()[:255] or rec.old_url
                rec.new_url = request.form.get(f"new_{rid}", rec.new_url or "").strip()[:255] or rec.new_url
                try:
                    rec.is_active = int(request.form.get(f"ac_{rid}", rec.is_active))
                except (ValueError, TypeError):
                    pass
                updated += 1
            commit_or_flash(f"Đã cập nhật {updated} redirect.", action="batch_update UrlRedirect")

        elif action == "delete":
            item_ids = request.form.getlist("item_id")
            deleted = 0
            for rid in item_ids:
                try:
                    rec = db.session.get(UrlRedirect, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec:
                    db.session.delete(rec)
                    deleted += 1
            commit_or_flash(f"Đã xóa {deleted} redirect.", action="batch_delete UrlRedirect")

        return redirect(url_for("urlredirect.index"))

    # VB: Url_Ac <> 99 ORDER BY Url_ID DESC, optional Url_Type filter
    type_filter = request.args.get("url_type", "")
    q = select(UrlRedirect).where(UrlRedirect.is_active != 99)
    if type_filter.lstrip("-").isdigit():
        q = q.where(UrlRedirect.url_type == int(type_filter))
    q = q.order_by(UrlRedirect.ID.desc())

    records = db.session.execute(q).scalars().all()

    return render_template(
        "urlredirect/index.html",
        records=records,
        total=len(records),
        type_filter=type_filter,
    )


@bp.route("/new", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    record = UrlRedirect(is_active=1, url_type=0)
    form_errors: dict = {}

    if request.method == "POST":
        _parse_form(record)
        if not record.old_url:
            form_errors["old_url"] = "URL cũ là bắt buộc."
        if not record.new_url:
            form_errors["new_url"] = "URL mới là bắt buộc."

        if not form_errors:
            db.session.add(record)
            if commit_or_flash("Đã thêm redirect.", action="create UrlRedirect"):
                return redirect(url_for("urlredirect.index"))
            return redirect(url_for("urlredirect.index"))

    return render_template(
        "urlredirect/form.html",
        record=record,
        form_errors=form_errors,
        is_edit=False,
    )


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(record_id: int):
    record = db.session.get(UrlRedirect, record_id)
    if record is None:
        flash("Không tìm thấy redirect.", "danger")
        return redirect(url_for("urlredirect.index"))

    form_errors: dict = {}

    if request.method == "POST":
        _parse_form(record)
        if not record.old_url:
            form_errors["old_url"] = "URL cũ là bắt buộc."
        if not record.new_url:
            form_errors["new_url"] = "URL mới là bắt buộc."

        if not form_errors:
            if commit_or_flash("Đã cập nhật redirect.", action=f"update UrlRedirect {record_id}"):
                return redirect(url_for("urlredirect.index"))
            return redirect(url_for("urlredirect.index"))

    return render_template(
        "urlredirect/form.html",
        record=record,
        form_errors=form_errors,
        is_edit=True,
    )


@bp.route("/<int:record_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(record_id: int):
    record = db.session.get(UrlRedirect, record_id)
    if record is None:
        flash("Không tìm thấy redirect.", "danger")
        return redirect(url_for("urlredirect.index"))

    db.session.delete(record)
    commit_or_flash("Đã xóa redirect.", action=f"delete UrlRedirect {record_id}")
    return redirect(url_for("urlredirect.index"))
