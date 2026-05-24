"""
Advertc blueprint — CRUD for tblAdvert filtered by MenuID (tblMenu tree).

VB equivalent: advertc.aspx
  - Filter: Type=1 (Adsense No-Ads position) AND MenuID from tblMenu dropdown
  - Inline edit: Title, Name, sCode, Sort, Ac  (more fields than advert.aspx)
  - Add/Edit form: same columns as advert.aspx

VB list query (advertc.aspx LoadAdvert):
  SELECT ID, Name, Title, sCode, <img/>, Ac, Sort, <TypeD label>
  FROM tblAdvert
  WHERE Type=1 AND MenuID='<menu_id>'
  ORDER BY Sort ASC

VB batch-update (btnUpdate1_Click) writes: Title, Name, Sort, Ac, sCode
VB batch-delete (btnDel1_Click): DELETE + remove /images/media/<id>.*
"""

import logging

from flask import current_app, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required
from sqlalchemy import select

from admin.blueprints.advertc import bp
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash


@bp.before_request
def _guard():
    return super_admin_redirect()
from admin.blueprints.banner.routes import _menu_options, _clean_link
from extensions import db, limiter
from models.banner import Advert, DISPLAY_TYPES
from admin.utils.html import sanitize_html
from admin.utils.upload import delete_media_image, save_media_image, validate_upload_file

log = logging.getLogger(__name__)

# advertc.aspx only manages Type=1 (Adsense No-Ads fallback banners)
ADVERTC_ZONE = 1
ADVERTC_ZONE_LABEL = "Adsense Vị trí No Ads"


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _current_menu_id() -> str:
    return request.args.get("menu_id", "000000").strip() or "000000"


def _parse_form(advert: Advert) -> None:
    advert.title = request.form.get("title", "").strip()
    advert.link = _clean_link(request.form.get("link", ""))
    advert.sort = request.form.get("sort", "").strip()
    advert.menu_id = request.form.get("menu_id", "000000").strip()
    advert.s_code = request.form.get("s_code", "").strip()
    advert.contents = request.form.get("contents", "").strip()
    advert.html = sanitize_html(request.form.get("html", ""))
    advert.zone_type = ADVERTC_ZONE
    advert.is_active = 1 if request.form.get("is_active") else 0
    advert.is_heading = 1 if request.form.get("is_heading") else 0
    try:
        advert.type_d = int(request.form.get("type_d", 1))
    except (ValueError, TypeError):
        advert.type_d = 1


def _validate(advert: Advert) -> dict:
    errors = {}
    if not (advert.title or "").strip():
        errors["title"] = "Tiêu đề là trường bắt buộc."
    elif len(advert.title) > 100:
        errors["title"] = "Tiêu đề không được vượt quá 100 ký tự."
    link = (advert.link or "").strip()
    if link and link != "#" and len(link) > 300:
        errors["link"] = "URL không được vượt quá 300 ký tự."
    return errors


def _render_form(advert: Advert, menu_id: str, form_errors: dict | None = None):
    return render_template(
        "advertc/form.html",
        advert=advert,
        display_types=DISPLAY_TYPES,
        menu_options=_menu_options(),
        current_menu_id=menu_id,
        zone_label=ADVERTC_ZONE_LABEL,
        form_errors=form_errors or {},
    )


# ------------------------------------------------------------------ #
# List + batch-update / batch-delete
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    """
    List No-Ads banners for the selected menu page with inline editing.

    POST _action=update → update Title/Name/sCode/Sort/Ac for all rows
    POST _action=delete → delete checked rows
    """
    menu_id = _current_menu_id()

    if request.method == "POST":
        if request.form.get("_action") == "delete":
            _batch_delete(request.form.getlist("item_id"))
        else:
            _batch_update(request.form.getlist("row_id"))
        return redirect(url_for("advertc.index", menu_id=menu_id))

    stmt = (
        select(Advert)
        .where(
            Advert.zone_type == ADVERTC_ZONE,
            Advert.menu_id == menu_id,
        )
        .order_by(Advert.sort.asc())
    )
    adverts = db.session.execute(stmt).scalars().all()

    return render_template(
        "advertc/index.html",
        adverts=adverts,
        display_types=DISPLAY_TYPES,
        menu_options=_menu_options(),
        current_menu_id=menu_id,
        zone_label=ADVERTC_ZONE_LABEL,
    )


def _batch_update(row_ids: list[str]) -> None:
    """
    Update Title, Name, sCode, Sort, Ac for all visible rows.
    VB: btnUpdate1_Click — loops all DataGrid rows, writes those 5 columns.
    """
    for raw_id in row_ids:
        try:
            rid = int(raw_id)
        except ValueError:
            continue
        advert = db.session.get(Advert, rid)
        if advert is None:
            continue
        advert.title = request.form.get(f"title_{rid}", advert.title or "").strip()
        advert.link = _clean_link(
            request.form.get(f"link_{rid}", advert.link or "")
        )
        advert.s_code = request.form.get(f"s_code_{rid}", advert.s_code or "").strip()
        advert.sort = request.form.get(f"sort_{rid}", advert.sort or "").strip()
        try:
            advert.is_active = int(
                request.form.get(f"ac_{rid}", advert.is_active)
            )
        except ValueError:
            pass
    commit_or_flash("Cập nhật thành công!", action="batch_update Advert(advertc)")


def _batch_delete(item_ids: list[str]) -> None:
    """
    Delete checked rows and their media files.
    VB: btnDel1_Click — only ticked checkboxes are deleted.
    """
    if not item_ids:
        flash("Chọn ít nhất một banner để xóa.", "warning")
        return
    for raw_id in item_ids:
        try:
            rid = int(raw_id)
        except ValueError:
            continue
        advert = db.session.get(Advert, rid)
        if advert is None:
            continue
        delete_media_image(rid)
        db.session.delete(advert)
    commit_or_flash("Xóa thành công!", action="batch_delete Advert(advertc)")


# ------------------------------------------------------------------ #
# Create
# ------------------------------------------------------------------ #

@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    """
    Add a new No-Ads banner.
    VB: btnAdd1_Click + btnAddU1_Click.
    """
    menu_id = _current_menu_id()

    if request.method == "POST":
        advert = Advert(img="null.gif", lang=1)
        _parse_form(advert)

        form_errors = _validate(advert)
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            form_errors["img_file"] = img_err
        if form_errors:
            return _render_form(advert, menu_id, form_errors)

        db.session.add(advert)
        db.session.flush()

        filename = save_media_image(request.files.get("img_file"), advert.ID)
        if filename:
            advert.img = filename

        if commit_or_flash("Thêm mới thành công!", action="create Advert(advertc)"):
            return redirect(url_for("advertc.index", menu_id=advert.menu_id))
        return redirect(url_for("advertc.index", menu_id=menu_id))

    advert = Advert(zone_type=ADVERTC_ZONE, menu_id=menu_id, is_active=1, type_d=1)
    return _render_form(advert, menu_id)


# ------------------------------------------------------------------ #
# Edit
# ------------------------------------------------------------------ #

@bp.route("/<int:advert_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(advert_id: int):
    """
    Edit an existing No-Ads banner.
    VB: dtgrView_ItemCommand (edit) + btnAddU1_Click (save).
    """
    advert = db.session.get(Advert, advert_id)
    if advert is None:
        flash("Banner không tồn tại.", "danger")
        return redirect(url_for("advertc.index"))

    menu_id = advert.menu_id or "000000"

    if request.method == "POST":
        _parse_form(advert)

        form_errors = _validate(advert)
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            form_errors["img_file"] = img_err
        if form_errors:
            return _render_form(advert, advert.menu_id, form_errors)

        if request.form.get("delete_img") == "1":
            delete_media_image(advert.ID)
            advert.img = "null.gif"

        filename = save_media_image(request.files.get("img_file"), advert.ID)
        if filename:
            advert.img = filename

        if commit_or_flash("Cập nhật thành công!", action=f"update Advert(advertc) {advert_id}"):
            return redirect(url_for("advertc.index", menu_id=advert.menu_id))
        return redirect(url_for("advertc.index"))

    return _render_form(advert, menu_id)


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@bp.route("/<int:advert_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(advert_id: int):
    """
    Delete one banner and its media file.
    VB: dtgrView_DeleteCommand.
    """
    advert = db.session.get(Advert, advert_id)
    if advert is None:
        flash("Banner không tồn tại.", "danger")
        return redirect(url_for("advertc.index"))

    menu_id = advert.menu_id or "000000"
    delete_media_image(advert_id)
    db.session.delete(advert)
    commit_or_flash("Xóa thành công!", action=f"delete Advert(advertc) {advert_id}")
    return redirect(url_for("advertc.index", menu_id=menu_id))
