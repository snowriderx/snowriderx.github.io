"""
Banner blueprint — CRUD for tblAdvert (content blocks).

VB equivalent: advert.aspx
  - Filter: drlSubID from tblPro (product ID = langid) + drlType1 radio (96/95)
  - Inline edit: Sort + Ac only
  - Grid shows: image, Title + Html content (no link/sCode in grid)
  - Form zones: 96, 95, 91–98

NOT in VB sidebar — accessed via internal links only.

VB list query (advert.aspx LoadAdvert):
  SELECT * FROM tblAdvert
  WHERE Type = <zone_type> AND MenuID = Val(Request("langid"))
  ORDER BY Sort ASC

VB batch-update (btnUpdate1_Click): Sort, Ac only
VB insert/update columns: Title, Contents, Html, Name, Sort, Type, TypeD, Ac,
                          MenuID (=langid), isHeading, Lang
"""

import logging

from flask import current_app, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required
from sqlalchemy import select

from admin.blueprints.banner import bp
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.lang import Lang, get_active_langs


@bp.before_request
def _guard():
    return super_admin_redirect()
from models.banner import Advert, DISPLAY_TYPES
from models.product import Product
from admin.utils.html import sanitize_html
from admin.utils.upload import delete_media_image, save_media_image, validate_upload_file

log = logging.getLogger(__name__)

# VB advert.aspx: drlType1 RadioButtonList default = 96 (Selected="True")
_DEFAULT_ZONE = 96

# VB advert.aspx drlType1 filter — only these 2 zones in the list view radio
FILTER_ZONE_TYPES = {
    96: "Banner",
    95: "Tổng quan",
}

# VB advert.aspx drlType form dropdown — full list for add/edit form
FORM_ZONE_TYPES = {
    96: "Banner",
    95: "Tổng quan",
    91: "Tính năng",
    92: "Ưu điểm",
    93: "Hướng dẫn",
    94: "Hỏi đáp",
    97: "Nội dung",
    98: "Chân trang",
}


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _filter_params() -> tuple[int, int]:
    """
    Parse zone_type and langid from query-string.
    VB: If Val(Request("langid")) = 0 Then Redirect("advert.aspx?langid=1")
    """
    try:
        zone_type = int(request.args.get("type", _DEFAULT_ZONE))
    except (ValueError, TypeError):
        zone_type = _DEFAULT_ZONE
    try:
        langid = int(request.args.get("langid", 1))
    except (ValueError, TypeError):
        langid = 1
    if langid <= 0:
        langid = 1
    return zone_type, langid


def _product_options() -> list[tuple[str, str]]:
    """
    Build product filter dropdown from tblPro.
    VB advert.aspx: SELECT IDP, NameP FROM tblPro WHERE AcP=1
    Returns list of (value, label) tuples.
    """
    stmt = select(Product.ID, Product.name).where(Product.is_active == 1)
    rows = db.session.execute(stmt).fetchall()
    return [(str(r.ID), r.name) for r in rows]


def _menu_options() -> list[tuple[str, str]]:
    """
    Build MenuID dropdown from tblMenu — used by advertc blueprint.
    VB advertc.aspx: SELECT IDM, <indented NameM> FROM tblMenu
                     WHERE AcM=1 AND TypeM IN (1,2) ORDER BY IDM ASC
                     + insert("Trang chủ", "000000") at position 0
    """
    from sqlalchemy import text
    sql = text("""
        SELECT "IDM",
               CASE WHEN "Levels" = 2 THEN '.... ' || "NameM"
                    WHEN "Levels" = 3 THEN '......... ' || "NameM"
                    ELSE "NameM"
               END AS "Name"
        FROM "tblMenu"
        WHERE "AcM" = 1 AND "TypeM" IN (1, 2)
        ORDER BY "IDM" ASC
    """)
    rows = db.session.execute(sql).fetchall()
    options = [("000000", "Trang chủ")]
    options += [(str(r.IDM), r.Name) for r in rows]
    return options


def _clean_link(value: str) -> str:
    """VB: Replace(txtName.Text, "http://", "")"""
    return value.strip().replace("http://", "")


def _parse_form(advert: Advert, langid: int) -> None:
    """
    Write form fields onto an Advert instance.
    advert.aspx has: Title, Contents, Html, Name(hidden), Sort, Type, Ac, isHeading
    Does NOT have sCode or TypeD radio — TypeD defaults to 1.
    MenuID is set from langid (URL param), not user-selectable.
    """
    advert.title = request.form.get("title", "").strip()
    advert.contents = request.form.get("contents", "").strip()
    advert.html = sanitize_html(request.form.get("html", ""))
    advert.link = _clean_link(request.form.get("link", "#"))
    advert.sort = request.form.get("sort", "").strip()
    advert.zone_type = _int_field("zone_type", _DEFAULT_ZONE)
    advert.is_active = 1 if request.form.get("is_active") else 0
    advert.is_heading = 1 if request.form.get("is_heading") else 0
    advert.menu_id = str(langid)
    advert.type_d = 1  # advert.aspx has no TypeD radio; default Banner
    raw_lang = request.form.get("lang_id", "").strip()
    try:
        advert.lang = int(raw_lang) if raw_lang else 1
    except (ValueError, TypeError):
        advert.lang = 1


def _int_field(name: str, default: int) -> int:
    try:
        return int(request.form.get(name, default))
    except (ValueError, TypeError):
        return default


def _validate_banner(advert: Advert) -> dict:
    errors = {}
    if not (advert.title or "").strip():
        errors["title"] = "Tiêu đề là trường bắt buộc."
    elif len(advert.title) > 100:
        errors["title"] = "Tiêu đề không được vượt quá 100 ký tự."
    return errors


def _render_form(advert: Advert, langid: int, zone_type: int,
                 form_errors: dict | None = None):
    langs = get_active_langs()
    return render_template(
        "banner/form.html",
        advert=advert,
        form_zone_types=FORM_ZONE_TYPES,
        product_options=_product_options(),
        current_langid=langid,
        current_zone=zone_type,
        form_errors=form_errors or {},
        langs=langs,
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
    List content-block adverts filtered by product (langid) and zone type.

    POST _action=update → update Sort + Ac for all rows (VB: btnUpdate1_Click)
    POST _action=delete → delete checked rows   (VB: btnDel1_Click)
    """
    zone_type, langid = _filter_params()

    if request.method == "POST":
        if request.form.get("_action") == "delete":
            _batch_delete(request.form.getlist("item_id"))
        else:
            _batch_update(request.form.getlist("row_id"))
        return redirect(
            url_for("banner.index", type=zone_type, langid=langid)
        )

    stmt = (
        select(Advert)
        .where(
            Advert.zone_type == zone_type,
            Advert.menu_id == str(langid),
        )
        .order_by(Advert.sort.asc())
    )

    # Language filter
    lang_filter = request.args.get("lang", "").strip()
    if lang_filter:
        try:
            stmt = stmt.where(Advert.lang == int(lang_filter))
        except (ValueError, TypeError):
            lang_filter = ""

    adverts = db.session.execute(stmt).scalars().all()
    langs = get_active_langs()

    return render_template(
        "banner/index.html",
        adverts=adverts,
        filter_zone_types=FILTER_ZONE_TYPES,
        product_options=_product_options(),
        current_zone=zone_type,
        current_langid=langid,
        langs=langs,
        lang_filter=lang_filter,
    )


def _batch_update(row_ids: list[str]) -> None:
    """
    VB btnUpdate1_Click: update Sort + Ac only.
    """
    for raw_id in row_ids:
        try:
            rid = int(raw_id)
        except ValueError:
            continue
        advert = db.session.get(Advert, rid)
        if advert is None:
            continue
        advert.sort = request.form.get(f"sort_{rid}", advert.sort or "")
        try:
            advert.is_active = int(
                request.form.get(f"ac_{rid}", advert.is_active)
            )
        except ValueError:
            pass
    commit_or_flash("Cập nhật thành công!", action="batch_update Advert")


def _batch_delete(item_ids: list[str]) -> None:
    """VB btnDel1_Click: delete checked rows + image files."""
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
    commit_or_flash("Xóa thành công!", action="batch_delete Advert")


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
    """VB: btnAdd1_Click (show form) + btnAddU1_Click (save)."""
    zone_type, langid = _filter_params()

    if request.method == "POST":
        advert = Advert(img="null.gif", lang=1)
        _parse_form(advert, langid)

        form_errors = _validate_banner(advert)
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            form_errors["img_file"] = img_err
        if form_errors:
            return _render_form(advert, langid, zone_type, form_errors)

        db.session.add(advert)
        db.session.flush()

        filename = save_media_image(request.files.get("img_file"), advert.ID)
        if filename:
            advert.img = filename

        if commit_or_flash("Thêm mới thành công!", action="create Advert"):
            return redirect(
                url_for("banner.index", type=advert.zone_type, langid=langid)
            )
        return redirect(url_for("banner.index", type=zone_type, langid=langid))

    advert = Advert(zone_type=zone_type, menu_id=str(langid), is_active=1)
    return _render_form(advert, langid, zone_type)


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
    """VB: dtgrView_ItemCommand (edit) + btnAddU1_Click (save)."""
    advert = db.session.get(Advert, advert_id)
    if advert is None:
        flash("Banner không tồn tại.", "danger")
        return redirect(url_for("banner.index"))

    try:
        langid = int(advert.menu_id or 1)
    except (ValueError, TypeError):
        langid = 1
    zone_type = advert.zone_type or _DEFAULT_ZONE

    if request.method == "POST":
        _parse_form(advert, langid)

        form_errors = _validate_banner(advert)
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            form_errors["img_file"] = img_err
        if form_errors:
            return _render_form(advert, langid, advert.zone_type, form_errors)

        if request.form.get("delete_img") == "1":
            delete_media_image(advert.ID)
            advert.img = "null.gif"

        filename = save_media_image(request.files.get("img_file"), advert.ID)
        if filename:
            advert.img = filename

        if commit_or_flash("Cập nhật thành công!", action=f"update Advert {advert_id}"):
            return redirect(
                url_for("banner.index", type=advert.zone_type, langid=langid)
            )
        return redirect(url_for("banner.index"))

    return _render_form(advert, langid, zone_type)


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@bp.route("/<int:advert_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(advert_id: int):
    """VB: dtgrView_DeleteCommand."""
    advert = db.session.get(Advert, advert_id)
    if advert is None:
        flash("Banner không tồn tại.", "danger")
        return redirect(url_for("banner.index"))

    try:
        langid = int(advert.menu_id or 1)
    except (ValueError, TypeError):
        langid = 1
    zone_type = advert.zone_type or _DEFAULT_ZONE

    delete_media_image(advert_id)
    db.session.delete(advert)
    commit_or_flash("Xóa thành công!", action=f"delete Advert {advert_id}")
    return redirect(url_for("banner.index", type=zone_type, langid=langid))
