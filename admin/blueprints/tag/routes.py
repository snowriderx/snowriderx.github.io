"""
Tag blueprint — CRUD for tblTag, split by section (news / menu / website).

VB equivalents:
  tag.aspx  → /admin/tag/menu/
  tagn.aspx → /admin/tag/news/
  tagw.aspx → /admin/tag/website/

URL pattern:
  GET/POST /admin/tag/<section>/                  list + batch update/delete
  GET/POST /admin/tag/<section>/new               create
  GET/POST /admin/tag/<section>/<tag_id>/edit     edit
  POST     /admin/tag/<section>/<tag_id>/delete   delete

section = "news" | "menu" | "website"

Owner context (menu_id column):
  news    → str(News.ID)   e.g. "42"
  menu    → Menu.IDM       e.g. "010000"
  website → "0"            fixed global

Access: super-admin only.
"""

import logging

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from admin.blueprints.tag import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.menu import Menu
from models.news import News
from models.tag import SECTION_LABELS, SECTIONS, Tag
from admin.utils.access import super_admin_redirect

log = logging.getLogger(__name__)

_LANG = 1


@bp.before_request
def _guard():
    return super_admin_redirect()


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _tag_type(section: str) -> int:
    """Return tag_type int for section, or 404 on unknown section."""
    if section not in SECTIONS:
        abort(404)
    return SECTIONS[section]


def _get_owners(section: str) -> list[tuple[str, str]]:
    """
    Return (id_str, label) pairs for the owner dropdown.
    Empty list for website section (no selector needed).
    """
    if section == "news":
        # VB tagn.aspx: AcN NOT IN (0,99) ORDER BY TimeN ASC
        rows = db.session.execute(
            select(News.ID, News.name)
            .where(News.is_active.not_in([0, 99]))
            .order_by(News.created_at.asc())
            .limit(500)
        ).all()
        return [(str(r.ID), f"{r.ID} - {r.name or '(chưa đặt tên)'}") for r in rows]

    if section == "menu":
        # VB tag.aspx: TypeM in (1,2) AND AcM=1 ORDER BY IDM ASC
        # Prepend 2 special items matching VB's hardcoded inserts
        special = [
            ("999999", "Tab toàn trang"),
            ("000000", "Tab trang chủ"),
        ]
        rows = db.session.execute(
            select(Menu)
            .where(Menu.lang == _LANG, Menu.type_m.in_([1, 2]), Menu.is_active == 1)
            .order_by(Menu.IDM.asc())
        ).scalars().all()
        return special + [(r.IDM, r.display_name) for r in rows]

    return []


def _get_owner_label(section: str, owner_id: str) -> str:
    """Human-readable label for the selected owner."""
    if not owner_id:
        return ""
    if section == "news":
        try:
            n_id = int(owner_id)
        except (ValueError, TypeError):
            return owner_id
        row = db.session.execute(
            select(News.name).where(News.ID == n_id)
        ).scalar_one_or_none()
        return f"#{owner_id} — {row or ''}"

    if section == "menu":
        if owner_id == "999999":
            return "Tab toàn trang"
        if owner_id == "000000":
            return "Tab trang chủ"
        row = db.session.execute(
            select(Menu.name).where(Menu.IDM == owner_id)
        ).scalar_one_or_none()
        return f"{owner_id} — {row or ''}"

    return ""


def _get_tags(section: str, owner_id: str) -> list[Tag]:
    """Return tags for the given section + owner, ordered by sort ASC."""
    tag_type = SECTIONS[section]
    effective_id = "0" if section == "website" else owner_id
    if not effective_id:
        return []
    return (
        db.session.execute(
            select(Tag)
            .where(Tag.tag_type == tag_type, Tag.menu_id == effective_id)
            .order_by(Tag.sort.asc(), Tag.ID.asc())
        )
        .scalars()
        .all()
    )


def _parse_form(record: Tag, section: str) -> None:
    """Write POST fields onto a Tag instance.
    Sort and Rel only exist for menu tags (VB tag.aspx) — not news or website.
    """
    record.title = request.form.get("title", "").strip()[:300] or None
    record.link  = request.form.get("link",  "").strip()[:300] or "#"
    if section == "menu":
        record.sort = request.form.get("sort", "00").strip()[:10] or "00"
        record.rel  = request.form.get("rel",  "").strip()[:50] or None
    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1


def _index_url(section: str, owner_id: str = "") -> str:
    if owner_id:
        return url_for("tag.index", section=section, owner_id=owner_id)
    return url_for("tag.index", section=section)


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@bp.route("/<section>/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index(section: str):
    tag_type = _tag_type(section)
    owner_id = request.args.get("owner_id", "")
    if section == "website":
        owner_id = "0"

    if request.method == "POST":
        action   = request.form.get("_action", "update")
        owner_id = request.form.get("owner_id", owner_id)

        if action == "update":
            row_ids = request.form.getlist("row_id")
            updated = 0
            for tid in row_ids:
                try:
                    rec = db.session.get(Tag, int(tid))
                except (ValueError, TypeError):
                    continue
                if rec is None or rec.tag_type != tag_type:
                    continue
                rec.title = (
                    request.form.get(f"title_{tid}", rec.title or "").strip()[:300]
                    or rec.title
                )
                rec.link = request.form.get(f"link_{tid}", rec.link or "#").strip()[:300] or "#"
                if section == "menu":
                    rec.sort = request.form.get(f"sort_{tid}", rec.sort or "00").strip()[:10] or "00"
                    rec.rel = request.form.get(f"rel_{tid}", "").strip()[:50] or None
                try:
                    rec.is_active = int(request.form.get(f"ac_{tid}", rec.is_active))
                except (ValueError, TypeError):
                    pass
                updated += 1
            commit_or_flash(f"Đã cập nhật {updated} tag.", action="batch_update Tag")

        elif action == "delete":
            item_ids = request.form.getlist("item_id")
            deleted = 0
            for tid in item_ids:
                try:
                    rec = db.session.get(Tag, int(tid))
                except (ValueError, TypeError):
                    continue
                if rec and rec.tag_type == tag_type:
                    db.session.delete(rec)
                    deleted += 1
            commit_or_flash(f"Đã xóa {deleted} tag.", action="batch_delete Tag")

        return redirect(_index_url(section, owner_id))

    owners = _get_owners(section)
    if not owner_id and owners:
        owner_id = owners[0][0]

    tags        = _get_tags(section, owner_id)
    owner_label = _get_owner_label(section, owner_id) if section != "website" else ""

    return render_template(
        "tag/index.html",
        section=section,
        section_label=SECTION_LABELS[section],
        owner_id=owner_id,
        owner_label=owner_label,
        owners=owners,
        tags=tags,
        total=len(tags),
    )


@bp.route("/<section>/new", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create(section: str):
    tag_type = _tag_type(section)
    owner_id = request.args.get("owner_id", request.form.get("owner_id", ""))
    if section == "website":
        owner_id = "0"

    record = Tag(
        tag_type  = tag_type,
        menu_id   = owner_id or ("0" if section == "website" else None),
        is_active = 1,
        sort      = "00",
    )
    form_errors: dict = {}

    if request.method == "POST":
        owner_id       = request.form.get("owner_id", owner_id)
        record.menu_id = owner_id or ("0" if section == "website" else None)
        _parse_form(record, section)

        if not record.title:
            form_errors["title"] = "Tiêu đề tag là bắt buộc."
        if section != "website" and not owner_id:
            form_errors["owner_id"] = (
                "Vui lòng chọn " + ("tin tức" if section == "news" else "menu") + " để gán tag."
            )

        if not form_errors:
            db.session.add(record)
            if commit_or_flash(f'Đã thêm tag "{record.title}".', action="create Tag"):
                return redirect(_index_url(section, owner_id))
            return redirect(_index_url(section, owner_id))

    owners      = _get_owners(section)
    owner_label = _get_owner_label(section, owner_id) if section != "website" else ""

    return render_template(
        "tag/form.html",
        record       = record,
        section      = section,
        section_label= SECTION_LABELS[section],
        owner_id     = owner_id,
        owner_label  = owner_label,
        owners       = owners,
        form_errors  = form_errors,
        is_edit      = False,
    )


@bp.route("/<section>/<int:tag_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(section: str, tag_id: int):
    tag_type = _tag_type(section)
    record   = db.session.get(Tag, tag_id)
    if record is None or record.tag_type != tag_type:
        flash("Không tìm thấy tag.", "danger")
        return redirect(url_for("tag.index", section=section))

    owner_id    = record.menu_id or ""
    form_errors : dict = {}

    if request.method == "POST":
        new_owner = request.form.get("owner_id", owner_id)
        if section != "website" and new_owner:
            record.menu_id = new_owner
            owner_id = new_owner
        _parse_form(record, section)
        if not record.title:
            form_errors["title"] = "Tiêu đề tag là bắt buộc."
        if section != "website" and not owner_id:
            form_errors["owner_id"] = (
                "Vui lòng chọn " + ("tin tức" if section == "news" else "menu") + " để gán tag."
            )

        if not form_errors:
            if commit_or_flash(f'Đã cập nhật tag "{record.title}".', action=f"update Tag {tag_id}"):
                return redirect(_index_url(section, owner_id))
            return redirect(_index_url(section, owner_id))

    owners      = _get_owners(section)
    owner_label = _get_owner_label(section, owner_id) if section != "website" else ""

    return render_template(
        "tag/form.html",
        record       = record,
        section      = section,
        section_label= SECTION_LABELS[section],
        owner_id     = owner_id,
        owner_label  = owner_label,
        owners       = owners,
        form_errors  = form_errors,
        is_edit      = True,
    )


@bp.route("/<section>/<int:tag_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(section: str, tag_id: int):
    tag_type = _tag_type(section)
    record   = db.session.get(Tag, tag_id)
    if record is None or record.tag_type != tag_type:
        flash("Không tìm thấy tag.", "danger")
        return redirect(url_for("tag.index", section=section))

    owner_id = record.menu_id or ""
    title = record.title or str(tag_id)
    db.session.delete(record)
    commit_or_flash(f'Đã xóa tag "{title}".', action=f"delete Tag {tag_id}")
    return redirect(_index_url(section, owner_id))
