"""
Contact blueprint — list, view, status update, delete for tblContact.

VB equivalent: contact.aspx

VB list query:
  SELECT IDC, NameC, EmailC, TelC, MobileC, TimeC,
         (SELECT u.Users FROM tblUser u WHERE u.IDU=UserID) AS Users
  FROM tblContact WHERE AcC='<filter>' ORDER BY TimeC DESC

AcC: 0=chưa đọc, 1=đã đọc
"""

import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from admin.blueprints.contact import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.contact import Contact
from models.news import News
from models.user import User
from admin.utils.access import super_admin_redirect

log = logging.getLogger(__name__)


@bp.before_request
def _guard():
    return super_admin_redirect()


@bp.route("/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    # VB: drlAc1 has 4 values; default=0 (Chưa xử lý), ?id= overrides
    ac_filter = request.args.get("id", "0")
    if ac_filter not in ("0", "1", "2", "3"):
        ac_filter = "0"

    if request.method == "POST":
        action   = request.form.get("_action", "update")
        row_ids  = request.form.getlist("row_id")

        if action == "update":
            updated = 0
            for rid in row_ids:
                try:
                    rec = db.session.get(Contact, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec is None:
                    continue
                try:
                    rec.is_read = int(request.form.get(f"ac_{rid}", rec.is_read))
                except (ValueError, TypeError):
                    pass
                updated += 1
            commit_or_flash(f"Đã cập nhật {updated} liên hệ.", action="batch_update Contact")

        elif action == "delete":
            item_ids = request.form.getlist("item_id")
            deleted  = 0
            for rid in item_ids:
                try:
                    rec = db.session.get(Contact, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec:
                    db.session.delete(rec)
                    deleted += 1
            commit_or_flash(f"Đã xóa {deleted} liên hệ.", action="batch_delete Contact")

        return redirect(url_for("contact.index", id=ac_filter))

    # VB: WHERE AcC='<filter>' ORDER BY TimeC DESC
    records = (
        db.session.execute(
            select(Contact)
            .where(Contact.is_read == int(ac_filter))
            .order_by(Contact.created_at.desc())
        )
        .scalars()
        .all()
    )

    # Attach handler username — mirrors VB JOIN tblUser
    user_map: dict[int, str] = {}
    uids = {r.user_id for r in records if r.user_id}
    if uids:
        rows = db.session.execute(
            select(User.IDU, User.username).where(User.IDU.in_(uids))
        ).all()
        user_map = {r.IDU: r.username for r in rows}

    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for status, cnt in db.session.execute(
        select(Contact.is_read, db.func.count().label("cnt"))
        .group_by(Contact.is_read)
    ).all():
        if status in counts:
            counts[status] = cnt

    return render_template(
        "contact/index.html",
        records=records,
        total=len(records),
        ac_filter=ac_filter,
        counts=counts,
        user_map=user_map,
    )


@bp.route("/<int:contact_id>", methods=["GET"])
def view(contact_id: int):
    record = db.session.get(Contact, contact_id)
    if record is None:
        flash("Không tìm thấy liên hệ.", "danger")
        return redirect(url_for("contact.index"))

    # Linked news (PostID)
    linked_news = None
    if record.post_id:
        linked_news = db.session.get(News, record.post_id)

    # Handler user
    handler = None
    if record.user_id:
        handler = db.session.get(User, record.user_id)

    return render_template(
        "contact/view.html",
        record=record,
        linked_news=linked_news,
        handler=handler,
        ac_filter="0",
    )


@bp.route("/<int:contact_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(contact_id: int):
    record = db.session.get(Contact, contact_id)
    if record is None:
        flash("Không tìm thấy liên hệ.", "danger")
        return redirect(url_for("contact.index"))

    ac_filter = request.args.get("ac_filter", str(record.is_read or "0"))

    if request.method == "POST":
        record.name    = request.form.get("name", record.name)
        record.email   = request.form.get("email", record.email)
        record.tel     = request.form.get("tel", record.tel)
        record.mobile  = request.form.get("mobile", record.mobile)
        record.address = request.form.get("address", record.address)
        record.content = request.form.get("content", record.content)
        try:
            record.is_read = int(request.form.get("is_read", record.is_read))
        except (ValueError, TypeError):
            pass
        if commit_or_flash("Đã cập nhật liên hệ.", action=f"update Contact {contact_id}"):
            return redirect(url_for("contact.index", id=record.is_read))
        return redirect(url_for("contact.index"))

    linked_news = None
    if record.post_id:
        linked_news = db.session.get(News, record.post_id)

    return render_template(
        "contact/edit.html",
        record=record,
        linked_news=linked_news,
        ac_filter=ac_filter,
    )


@bp.route("/<int:contact_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(contact_id: int):
    ac_filter = request.form.get("ac_filter", "0")
    record = db.session.get(Contact, contact_id)
    if record is None:
        flash("Không tìm thấy liên hệ.", "danger")
        return redirect(url_for("contact.index"))

    db.session.delete(record)
    commit_or_flash("Đã xóa liên hệ.", action=f"delete Contact {contact_id}")
    return redirect(url_for("contact.index", id=ac_filter))
