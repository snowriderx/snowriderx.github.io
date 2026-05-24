"""
Layout blueprint — CRUD for landing/content pages (tblMenu WHERE ChkM=80).

VB equivalent: layout.aspx / layout.aspx.vb

VB list query:
  SELECT IDM, NameM, Name1M, SortM, AcM, ImgM, HomeM, URL, DescM, Css, BgM
  FROM tblContent       ← tblMenu alias / view
  WHERE levels=1 AND ChkM=80 AND Lang=1
  ORDER BY SortM ASC

Key insight from VB code:
  - "tblContent" = tblMenu filtered by ChkM=80 — same physical table.
  - tblIntro is shown as a reference panel on the form so admin can copy
    content blocks into DescM. No DB relation is stored.
  - DescM holds the page body HTML (CKEditor).
  - URL = optional external URL or slug override.
  - BgM = optional CSS background color (#hex).
  - ChkM=80, TypeM=80, Levels=1 are hardcoded on every insert.

Access: super-admin only (IDU=1).
"""

import logging
import re

from flask import current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from admin.blueprints.layout import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.intro import get_active_intros
from models.menu import Menu, get_layout_pages
from admin.utils.access import super_admin_redirect
from admin.utils.html import sanitize_html
from admin.utils.text import slugify_vi

log = logging.getLogger(__name__)

_LANG = 1
_CHK_M = 80  # identifies layout/landing pages in tblMenu


@bp.before_request
def _guard():
    return super_admin_redirect()


@bp.context_processor
def _inject_intro_blocks():
    return {"intro_blocks": get_active_intros()}


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _chk_m_ready() -> bool:
    """True when ChkM is mapped on the Menu model (optional column)."""
    try:
        return "chk_m" in Menu.__mapper__.columns
    except Exception:
        return False


def _next_layout_idm() -> str:
    """
    Generate the next available Level-1 IDM for a new layout page.
    Shares the same IDM namespace as regular tblMenu rows.
    VB: MenuCode() — finds max 2-digit prefix among all tblContent rows.
    """
    existing = (
        db.session.execute(select(Menu.IDM).where(Menu.levels == 1))
        .scalars()
        .all()
    )
    if not existing:
        return "010000"
    max_xx = max(int(idm[:2]) for idm in existing if idm and len(idm) >= 2)
    nxt = max_xx + 1
    if nxt > 99:
        raise ValueError("Đã đạt tối đa 99 trang cấp 1.")
    return f"{nxt:02d}0000"


def _parse_form(record: Menu) -> None:
    """Write POST form fields onto a Menu instance for a layout page."""
    name = request.form.get("name", "").strip()
    record.name = name or "-"
    record.slug = request.form.get("slug", "").strip() or slugify_vi(record.name)

    # DescM: CKEditor body — h1→h2, then sanitize
    desc_raw = request.form.get("desc_m", "")
    desc_raw = re.sub(r"<h1([^>]*)>", r"<h2\1>", desc_raw)
    desc_raw = desc_raw.replace("</h1>", "</h2>")
    record.desc_m = sanitize_html(desc_raw)

    record.sort_order = request.form.get("sort_order", "10").strip() or "10"

    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1

    # Optional fields — written only when column is mapped
    if _has_col("url"):
        record.url = request.form.get("url", "").strip()  # type: ignore[attr-defined]

    if _has_col("bg_m"):
        bg = request.form.get("bg_m", "").strip()
        if bg and not bg.startswith("#"):
            bg = "#" + bg
        record.bg_m = bg  # type: ignore[attr-defined]

    # HomeM: slide integration (0=none, 1=Banner trên, 6=Banner dưới)
    if _has_col("home_m"):
        try:
            record.home_m = int(request.form.get("home_m", 0))  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            record.home_m = 0  # type: ignore[attr-defined]

    # Css: custom CSS block
    if _has_col("css_m"):
        record.css_m = request.form.get("css_m", "").strip() or None  # type: ignore[attr-defined]

    # SEO fields (optional columns)
    for attr, field in [
        ("seo_title",   "seo_title"),
        ("keywords",    "keywords"),
        ("description", "description"),
        ("name_mh",     "name_mh"),
    ]:
        if _has_col(attr):
            setattr(record, attr, request.form.get(field, "").strip() or None)


def _has_col(attr: str) -> bool:
    """True when attr is a mapped column on Menu (not just a class-level None)."""
    try:
        return attr in Menu.__mapper__.columns
    except Exception:
        return False


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    if request.method == "POST":
        action = request.form.get("_action", "update")
        row_ids = request.form.getlist("row_id")

        if action == "update":
            updated = 0
            for idm in row_ids:
                record = db.session.get(Menu, idm)
                if record is None:
                    continue
                record.sort_order = (
                    request.form.get(f"sort_{idm}", record.sort_order or "10").strip()
                    or "10"
                )
                try:
                    record.is_active = int(
                        request.form.get(f"ac_{idm}", record.is_active)
                    )
                except (ValueError, TypeError):
                    pass
                updated += 1
            commit_or_flash(f"Đã cập nhật {updated} trang.", action="batch_update Layout")
        elif action == "delete":
            item_ids = request.form.getlist("item_id")
            deleted = 0
            for idm in item_ids:
                record = db.session.get(Menu, idm)
                if record:
                    db.session.delete(record)
                    deleted += 1
            commit_or_flash(f"Đã xóa {deleted} trang.", action="batch_delete Layout")

        return redirect(url_for("layout.index"))

    pages = get_layout_pages()
    chk_ready = _chk_m_ready()
    return render_template(
        "layout/index.html",
        pages=pages,
        chk_ready=chk_ready,
    )


@bp.route("/new", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    if not _chk_m_ready():
        flash("Cột ChkM chưa tồn tại trong cơ sở dữ liệu.", "danger")
        return redirect(url_for("layout.index"))

    form_errors: dict = {}
    record = Menu(
        levels=1,
        lang=_LANG,
        sort_order="10",
        is_active=1,
        type_m=_CHK_M,
    )
    record.chk_m = _CHK_M  # type: ignore[attr-defined]

    if request.method == "POST":
        _parse_form(record)
        if not (record.name and record.name.strip() and record.name != "-"):
            form_errors["name"] = "Tiêu đề là trường bắt buộc."

        if not form_errors:
            try:
                record.IDM = _next_layout_idm()
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template(
                    "layout/form.html",
                    page=record,
                    form_errors=form_errors,
                    is_edit=False,
                    has_col=_has_col,
                )
            db.session.add(record)
            commit_or_flash(
                f'Đã tạo trang "{record.name}".',
                action=f"create Layout {record.IDM}",
            )
            return redirect(url_for("layout.index"))

    return render_template(
        "layout/form.html",
        page=record,
        form_errors=form_errors,
        is_edit=False,
        has_col=_has_col,
    )


@bp.route("/<page_idm>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(page_idm: str):
    record = db.session.get(Menu, page_idm)
    if record is None:
        flash("Không tìm thấy trang.", "danger")
        return redirect(url_for("layout.index"))

    form_errors: dict = {}

    if request.method == "POST":
        _parse_form(record)
        if not (record.name and record.name.strip() and record.name != "-"):
            form_errors["name"] = "Tiêu đề là trường bắt buộc."

        if not form_errors:
            commit_or_flash(
                f'Đã cập nhật trang "{record.name}".',
                action=f"update Layout {page_idm}",
            )
            return redirect(url_for("layout.index"))

    return render_template(
        "layout/form.html",
        page=record,
        form_errors=form_errors,
        is_edit=True,
        has_col=_has_col,
    )


@bp.route("/<page_idm>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(page_idm: str):
    record = db.session.get(Menu, page_idm)
    if record is None:
        flash("Không tìm thấy trang.", "danger")
        return redirect(url_for("layout.index"))

    name = record.name or page_idm
    db.session.delete(record)
    commit_or_flash(f'Đã xóa trang "{name}".', action=f"delete Layout {page_idm}")
    return redirect(url_for("layout.index"))
