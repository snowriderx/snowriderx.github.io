import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from admin.blueprints.comment import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.comment import Comment
from models.news import News
from models.menu import Menu
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
    if request.method == "POST":
        action  = request.form.get("_action", "update")
        row_ids = request.form.getlist("row_id")

        if action == "update":
            for rid in row_ids:
                try:
                    rec = db.session.get(Comment, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec is None:
                    continue
                try:
                    rec.is_show = int(request.form.get(f"ac_{rid}", rec.is_show))
                except (ValueError, TypeError):
                    pass
            commit_or_flash("Đã cập nhật.", action="batch_update Comment")

        elif action == "delete":
            deleted = 0
            for rid in request.form.getlist("item_id"):
                try:
                    rec = db.session.get(Comment, int(rid))
                except (ValueError, TypeError):
                    continue
                if rec:
                    db.session.delete(rec)
                    deleted += 1
            commit_or_flash(f"Đã xóa {deleted} comment.", action="batch_delete Comment")

        return redirect(url_for("comment.index"))

    # Filters
    ac_filter = request.args.get("ac", "")
    news_filter = request.args.get("news_id", "")

    stmt = select(Comment).order_by(Comment.created_at.desc())
    if ac_filter in ("0", "1"):
        stmt = stmt.where(Comment.is_show == int(ac_filter))
    if news_filter:
        try:
            stmt = stmt.where(Comment.news_id == int(news_filter))
        except ValueError:
            pass

    records = db.session.execute(stmt).scalars().all()

    # Build news map for "Tin bài" column (TypeC != 1 → tblNews)
    news_map: dict[int, str] = {}
    news_ids = {r.news_id for r in records if r.news_id and r.type_c != 1}
    if news_ids:
        rows = db.session.execute(
            select(News.ID, News.name).where(News.ID.in_(news_ids))
        ).all()
        news_map = {r.ID: r.name for r in rows}

    # Build menu map for TypeC == 1 comments (lookup by AutoM)
    menu_map: dict[int, str] = {}
    menu_news_ids = {r.news_id for r in records if r.news_id and r.type_c == 1}
    if menu_news_ids and Menu.auto_m is not None:
        rows = db.session.execute(
            select(Menu.auto_m, Menu.name).where(Menu.auto_m.in_(menu_news_ids))
        ).all()
        menu_map = {r[0]: r[1] for r in rows}

    # Count hidden (pending moderation)
    hidden_count = db.session.execute(
        select(db.func.count()).select_from(Comment).where(Comment.is_show == 0)
    ).scalar_one()

    return render_template(
        "comment/index.html",
        records=records,
        total=len(records),
        news_map=news_map,
        menu_map=menu_map,
        ac_filter=ac_filter,
        news_filter=news_filter,
        hidden_count=hidden_count,
    )


@bp.route("/<int:comment_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(comment_id: int):
    record = db.session.get(Comment, comment_id)
    if record is None:
        flash("Không tìm thấy comment.", "danger")
        return redirect(url_for("comment.index"))

    if request.method == "POST":
        record.name    = request.form.get("name", record.name)
        record.email   = request.form.get("email", record.email)
        record.content = request.form.get("content", record.content)
        try:
            record.is_show = int(request.form.get("is_show", record.is_show))
        except (ValueError, TypeError):
            pass
        if commit_or_flash("Đã cập nhật comment.", action=f"update Comment {comment_id}"):
            return redirect(url_for("comment.index"))
        return redirect(url_for("comment.index"))

    linked = None
    if record.news_id:
        if record.type_c == 1 and Menu.auto_m is not None:
            linked = db.session.execute(
                select(Menu).where(Menu.auto_m == record.news_id)
            ).scalar_one_or_none()
        elif record.type_c != 1:
            linked = db.session.get(News, record.news_id)

    return render_template("comment/edit.html", record=record, linked=linked)


@bp.route("/<int:comment_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(comment_id: int):
    record = db.session.get(Comment, comment_id)
    if record is None:
        flash("Không tìm thấy comment.", "danger")
        return redirect(url_for("comment.index"))
    db.session.delete(record)
    commit_or_flash("Đã xóa comment.", action=f"delete Comment {comment_id}")
    return redirect(url_for("comment.index"))
