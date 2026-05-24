"""
Menu blueprint — CRUD for tblMenu (site navigation / content categories).

VB equivalents: menu.aspx / menu.aspx.vb

Hierarchy rules (IDM format):
  Level 1: XX0000   e.g. '010000'  — created with parent = None
  Level 2: XXYY00   e.g. '010100'  — created under a Level-1 IDM
  Level 3: XXYYZZ   e.g. '010101'  — created under a Level-2 IDM
  Maximum depth: 3.  Max siblings per parent: 99.

Create flow:
  1. Admin picks optional parent from dropdown (None → Level 1)
  2. Server generates next available IDM via _next_idm()
  3. Record saved with generated IDM, name, type_m, lang, levels

Edit flow:
  - Can change: name, type_m, lang
  - CANNOT change parent / IDM — reparenting would require cascading
    IDM renames across tblMenu children, tblNews.MenuIDN, and tblLink.RowIDM.

Delete flow:
  - BLOCKED if menu has direct children (prevent orphaned sub-trees)
  - BLOCKED if news articles reference this IDM (protect tblNews integrity)
  - Otherwise: DELETE FROM tblMenu WHERE IDM = :idm

Sort/order:
  Rows are ordered by IDM ASC — which naturally encodes tree position.
  Explicit drag-and-drop reorder is a future enhancement.

Compatibility with News module:
  - News.menu_id (MenuIDN) is a 6-char FK to Menu.IDM.
  - _get_menus() in news/routes.py reads tblMenu unchanged — no migration needed.
  - Deleting a menu that has news is blocked here to prevent orphaned news.

Permission-system readiness:
  IDM is the stable natural key. A future user×menu permission table
  (e.g., tblMenuPerm) should reference IDM so prefix queries still work:
    SELECT * FROM tblMenuPerm WHERE Left(IDM, 2) = '01'  → all of category 01.
"""

import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select, text

from admin.blueprints.menu import bp
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash
from extensions import db, limiter


@bp.before_request
def _guard():
    return super_admin_redirect()
from models.lang import Lang, get_active_langs
from models.menu import Menu, MENU_AC, MENU_CHK, MENU_TYPES, MENU_LANGS
from models.news import News
from admin.utils.upload import (
    delete_menu_image_file,
    save_menu_image,
    validate_upload_file,
)

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Tree helpers
# ------------------------------------------------------------------ #

def _get_all_menus() -> list[Menu]:
    """All menus ordered by SortM then IDM — mirrors VB loadMenu ORDER BY SortM."""
    return (
        db.session.execute(
            select(Menu).order_by(Menu.sort_order.asc(), Menu.IDM.asc())
        )
        .scalars()
        .all()
    )


def _build_tree(menus: list[Menu]) -> list[dict]:
    """
    Convert a flat, IDM-sorted list into a 3-level nested structure.

    Return value shape:
      [
        {'menu': <L1>, 'children': [
          {'menu': <L2>, 'children': [
            {'menu': <L3>, 'children': []},
          ]},
        ]},
      ]

    Algorithm: single O(n) grouping pass builds two prefix → children
    dicts (L2 keyed by 2-char L1 prefix, L3 keyed by 4-char L2 prefix),
    then a single O(n) assembly pass constructs the tree.
    This avoids the O(n1 × n2 × n3) triple-nested-loop approach.

    Level is read from Menu.levels (not re-derived from IDM) so the
    tree is correct even if IDM values are non-contiguous.
    Orphaned nodes (no matching parent) are silently dropped to keep
    the template simple; they remain in the DB and can be fixed.
    """
    # --- grouping pass ----------------------------------------------- #
    level1: list[Menu] = []
    # l2_by_l1_prefix: "01" → [m2a, m2b, ...]
    l2_by_l1_prefix: dict[str, list[Menu]] = {}
    # l3_by_l2_prefix: "0101" → [m3a, m3b, ...]
    l3_by_l2_prefix: dict[str, list[Menu]] = {}

    for m in menus:
        lvl = m.levels or 1
        idm = m.IDM or ""
        if lvl == 1:
            level1.append(m)
        elif lvl == 2:
            key = idm[:2]
            l2_by_l1_prefix.setdefault(key, []).append(m)
        elif lvl == 3:
            key = idm[:4]
            l3_by_l2_prefix.setdefault(key, []).append(m)
        # lvl > 3: silently ignore — max supported depth is 3

    # --- assembly pass ------------------------------------------------ #
    tree: list[dict] = []
    for m1 in level1:
        prefix1 = (m1.IDM or "")[:2]
        children_l2: list[dict] = []
        for m2 in l2_by_l1_prefix.get(prefix1, []):
            prefix2 = (m2.IDM or "")[:4]
            children_l3 = [
                {"menu": m3, "children": []}
                for m3 in l3_by_l2_prefix.get(prefix2, [])
            ]
            children_l2.append({"menu": m2, "children": children_l3})
        tree.append({"menu": m1, "children": children_l2})

    return tree


# ------------------------------------------------------------------ #
# IDM generation
# ------------------------------------------------------------------ #

def _next_idm(parent: "Menu | None") -> str:
    """
    Return the next available 6-char IDM under the given parent.

    parent = None  → new Level-1 item  (e.g. '030000')
    parent = L1    → new Level-2 item  (e.g. '010300')
    parent = L2    → new Level-3 item  (e.g. '010103')

    Accepts the already-fetched parent object (not just its IDM string)
    to avoid a redundant DB round-trip from the caller.

    Raises ValueError when a namespace is full (99 siblings used).
    """
    if parent is None:
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
            raise ValueError("Đã đạt tối đa 99 danh mục cấp 1.")
        return f"{nxt:02d}0000"

    parent_level = parent.levels or 1

    if parent_level == 1:
        prefix = (parent.IDM or "")[:2]
        # Siblings are Level-2 items: IDM pattern 'XX??00'
        existing = (
            db.session.execute(
                select(Menu.IDM).where(
                    Menu.levels == 2,
                    Menu.IDM.like(f"{prefix}__00"),
                )
            )
            .scalars()
            .all()
        )
        if not existing:
            return f"{prefix}0100"
        max_yy = max(int(idm[2:4]) for idm in existing if idm and len(idm) >= 4)
        nxt = max_yy + 1
        if nxt > 99:
            raise ValueError(
                f"Đã đạt tối đa 99 danh mục cấp 2 dưới '{parent.name}'."
            )
        return f"{prefix}{nxt:02d}00"

    if parent_level == 2:
        prefix = (parent.IDM or "")[:4]
        # Siblings are Level-3 items: IDM pattern 'XXYY??'
        existing = (
            db.session.execute(
                select(Menu.IDM).where(
                    Menu.levels == 3,
                    Menu.IDM.like(f"{prefix}__"),
                )
            )
            .scalars()
            .all()
        )
        if not existing:
            return f"{prefix}01"
        max_zz = max(int(idm[4:6]) for idm in existing if idm and len(idm) >= 6)
        nxt = max_zz + 1
        if nxt > 99:
            raise ValueError(
                f"Đã đạt tối đa 99 danh mục cấp 3 dưới '{parent.name}'."
            )
        return f"{prefix}{nxt:02d}"

    raise ValueError("Không thể tạo danh mục cấp 4 (tối đa 3 cấp).")


# ------------------------------------------------------------------ #
# Safety guards for delete
# ------------------------------------------------------------------ #

def _has_children(menu: Menu) -> bool:
    """
    True if this menu item has any direct children in tblMenu.

    Uses explicit LIKE patterns per level to avoid the fragile
    conditional-suffix f-string.
    """
    lvl = menu.levels or 1
    idm = menu.IDM or ""

    if lvl == 1:
        # Children are Level-2 items matching 'XX__00'
        pattern = idm[:2] + "__00"
        child_level = 2
    elif lvl == 2:
        # Children are Level-3 items matching 'XXYY__'
        pattern = idm[:4] + "__"
        child_level = 3
    else:
        # Level 3 is a leaf — can never have children
        return False

    count = (
        db.session.execute(
            select(func.count()).where(
                Menu.levels == child_level,
                Menu.IDM.like(pattern),
            )
        ).scalar()
        or 0
    )
    return count > 0


def _news_count(idm: str) -> int:
    """Count tblNews rows whose MenuIDN equals this IDM exactly."""
    return (
        db.session.execute(
            select(func.count()).where(News.menu_id == idm)
        ).scalar()
        or 0
    )


# ------------------------------------------------------------------ #
# Form helpers
# ------------------------------------------------------------------ #

def _parse_form(record: Menu) -> None:
    """Write POST fields onto a Menu instance (mirrors VB btnAddU1_Click)."""
    from admin.utils.text import slugify_vi

    g = lambda key, default="": request.form.get(key, default).strip()

    record.name = g("name")

    # Name1M: use explicit input if provided, else auto-generate from name.
    raw_slug = g("slug")
    record.slug = raw_slug if raw_slug else slugify_vi(record.name)

    record.sort_order = g("sort_order") or "00"

    # Extended fields — only write to columns that were actually mapped.
    # Columns missing from the DB remain as class-level None and SQLAlchemy
    # will ignore writes to non-instrumented attributes.
    _mapped = Menu.__mapper__.columns.keys()

    if "name_mh"     in _mapped: record.name_mh     = g("name_mh") or None
    if "url"         in _mapped: record.url          = g("url") or None
    if "desc_m"      in _mapped: record.desc_m       = request.form.get("desc_m", "").strip() or None
    if "seo_title"   in _mapped: record.seo_title    = g("seo_title") or None
    if "keywords"    in _mapped: record.keywords     = g("keywords") or None
    if "description" in _mapped: record.description  = g("description") or None
    if "ischema"     in _mapped: record.ischema      = request.form.get("ischema", "").strip() or None
    if "rel"         in _mapped: record.rel          = g("rel") or None
    if "home_m"      in _mapped:
        try:
            record.home_m = 1 if request.form.get("home_m") else 0
        except Exception:
            record.home_m = 0
    if "chk_m"       in _mapped:
        try:
            v = int(request.form.get("chk_m", 0))
            record.chk_m = v if v in (1, 2) else None
        except (ValueError, TypeError):
            record.chk_m = None
    if "tab_m"       in _mapped:
        # Build '-1-,-2-' format from multi-checkbox values
        selected = request.form.getlist("tab_m")
        if selected:
            record.tab_m = ",".join(f"-{v}-" for v in selected if v.isdigit())
        else:
            record.tab_m = None
    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1
    try:
        record.type_m = int(request.form.get("type_m", 1))
    except (ValueError, TypeError):
        record.type_m = 1
    try:
        record.lang = int(request.form.get("lang", 1))
    except (ValueError, TypeError):
        record.lang = 1
    raw_lang_id = request.form.get("lang_id", "").strip()
    try:
        record.lang = int(raw_lang_id) if raw_lang_id else 1
    except (ValueError, TypeError):
        record.lang = 1


def _field_errors(record: Menu, parent: "Menu | None", is_new: bool) -> dict:
    """
    Return per-field errors.

    Accepts the pre-fetched parent object so the caller avoids an extra
    DB round-trip (parent is needed by both this function and _next_idm).
    """
    errors: dict = {}
    if not (record.name or "").strip():
        errors["name"] = "Tên danh mục là trường bắt buộc."
    elif len(record.name) > 200:
        errors["name"] = "Không được vượt quá 200 ký tự."

    if record.slug and len(record.slug) > 100:
        errors["slug"] = "Slug không được vượt quá 100 ký tự."

    sort_val = record.sort_order or ""
    if sort_val and (not sort_val.isdigit() or len(sort_val) > 10):
        errors["sort_order"] = "Thứ tự sắp xếp phải là số nguyên (tối đa 10 ký tự)."

    if record.is_active not in (0, 1):
        errors["is_active"] = "Trạng thái không hợp lệ."

    if record.name_mh and len(record.name_mh) > 200:
        errors["name_mh"] = "Không được vượt quá 200 ký tự."
    if record.url and len(record.url) > 100:
        errors["url"] = "Không được vượt quá 100 ký tự."
    if record.seo_title and len(record.seo_title) > 200:
        errors["seo_title"] = "Không được vượt quá 200 ký tự."
    if record.keywords and len(record.keywords) > 100:
        errors["keywords"] = "Không được vượt quá 100 ký tự."
    if record.description and len(record.description) > 300:
        errors["description"] = "Không được vượt quá 300 ký tự."
    if record.rel and len(record.rel) > 100:
        errors["rel"] = "Không được vượt quá 100 ký tự."

    img_err = validate_upload_file(request.files.get("img_file"))
    if img_err:
        errors["img_file"] = img_err
    img1_err = validate_upload_file(request.files.get("img1_file"))
    if img1_err:
        errors["img1_file"] = img1_err

    if is_new:
        parent_idm = request.form.get("parent_idm", "").strip()
        if parent_idm:
            if parent is None:
                errors["parent_idm"] = "Danh mục cha không tồn tại."
            elif (parent.levels or 1) >= 3:
                errors["parent_idm"] = "Không thể tạo danh mục cấp 4."

    return errors


def _get_tab_positions() -> list[dict]:
    """
    Fetch position tabs from tblTab WHERE Ac != 0 AND Type = 3 ORDER BY Sort.
    Mirrors VB insert_data() cblTab population.
    Returns list of {'id': int, 'name': str}.
    """
    try:
        rows = db.session.execute(
            text('SELECT "ID", "Name" FROM "tblTab" WHERE "Ac" != 0 AND "Type" = 3 ORDER BY "Sort"')
        ).fetchall()
        return [{"id": int(r[0]), "name": str(r[1])} for r in rows]
    except Exception:
        return []


def _sync_tbl_link(idm: str, lang: int = 1) -> None:
    """
    Regenerate tblLink row for a menu item (RowType=1).

    VB menu.aspx.vb btnAddU1_Click:
      DELETE tblLink WHERE RowIDM=IDM AND RowType=1 AND RowLang=lang
      INSERT INTO tblLink (...) SELECT AutoM,Name1M,1,TypeM,Levels,IDM,
        title,keywords,description,NameMH,Lang FROM tblMenu WHERE IDM=IDM
    """
    try:
        db.session.execute(
            text(
                'DELETE FROM "tblLink" '
                'WHERE "RowIDM" = :idm AND "RowType" = 1 AND "RowLang" = :lang'
            ),
            {"idm": idm, "lang": lang},
        )
        db.session.execute(
            text("""
                INSERT INTO "tblLink"
                    ("RowID", "RowUrl", "RowType", "RowTypeM", "RowLevels",
                     "RowIDM", "title", "keywords", "description", "RowName", "RowLang")
                SELECT "AutoM", "Name1M", 1, "TypeM", "Levels", "IDM",
                       "title", "keywords", "description", "NameMH", "Lang"
                FROM "tblMenu"
                WHERE "IDM" = :idm
            """),
            {"idm": idm},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink sync failed for menu %s: %s", idm, exc)


def _delete_tbl_link(idm: str) -> None:
    """Remove tblLink rows for a deleted menu item."""
    try:
        db.session.execute(
            text('DELETE FROM "tblLink" WHERE "RowIDM" = :idm AND "RowType" = 1'),
            {"idm": idm},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink delete failed for menu %s: %s", idm, exc)


def _get_eligible_parents() -> list[Menu]:
    """
    Return menus that can accept a new child — Level 1 and Level 2 only.
    Ordered by IDM so the dropdown mirrors the tree.
    """
    return (
        db.session.execute(
            select(Menu)
            .where(Menu.levels.in_([1, 2]))
            .order_by(Menu.sort_order.asc(), Menu.IDM.asc())
        )
        .scalars()
        .all()
    )


def _has_upload(field: str) -> bool:
    """True if the request contains a non-empty file upload for the given field."""
    f = request.files.get(field)
    return bool(f and f.filename)


def _handle_images(record: Menu) -> None:
    """
    Process deferred-delete flags and new file uploads for Icon + Banner.
    Mirrors VB UploadFile calls in btnAddU1_Click.
    Must be called AFTER db.session.flush() so record.IDM is available.

    Writes are guarded by _mapped so that optional columns absent from the
    real DB schema are never assigned — SQLAlchemy only tracks writes to
    properly instrumented (mapper-registered) attributes.
    """
    _mapped = Menu.__mapper__.columns.keys()

    # VB: iName1 = slug, iID = AutoM — used as filename prefix
    slug   = record.computed_slug or (record.IDM or "menu")
    auto_m = record.auto_m if "auto_m" in _mapped else None

    # Deferred deletes
    if request.form.get("delete_img") == "1" and "img_m" in _mapped:
        delete_menu_image_file(record.img_m)
        record.img_m = None
    if request.form.get("delete_img1") == "1" and "img_m1" in _mapped:
        delete_menu_image_file(record.img_m1)
        record.img_m1 = None

    # New icon upload — mirrors VB UploadFile(FilePro, iName1 & iID & "_icon", …, 200)
    if "img_m" in _mapped:
        icon = save_menu_image(request.files.get("img_file"), slug, auto_m, "icon")
        if icon:
            record.img_m = icon
    elif _has_upload("img_file"):
        flash("Cột ImgM chưa tồn tại trong DB — ảnh Icon chưa được lưu.", "warning")
        log.warning("img_m not mapped — icon upload skipped for IDM=%s", record.IDM)

    # New banner upload — mirrors VB UploadFile(FilePro2, iName1 & iID & "_banner", …, 500)
    if "img_m1" in _mapped:
        banner = save_menu_image(request.files.get("img1_file"), slug, auto_m, "banner")
        if banner:
            record.img_m1 = banner
    elif _has_upload("img1_file"):
        flash("Cột ImgM1 chưa tồn tại trong DB — ảnh Banner chưa được lưu.", "warning")
        log.warning("img_m1 not mapped — banner upload skipped for IDM=%s", record.IDM)


def _render_create_form(
    record: Menu,
    parents: list[Menu],
    selected_parent_idm: "str | None",
    form_errors: dict,
    tab_items: list | None = None,
):
    """Render the create form — extracted to avoid repeating identical args."""
    _langs = get_active_langs()
    return render_template(
        "menu/form.html",
        menu=record,
        parents=parents,
        selected_parent_idm=selected_parent_idm,
        form_errors=form_errors,
        menu_types=MENU_TYPES,
        menu_langs=MENU_LANGS,
        menu_ac=MENU_AC,
        menu_chk=MENU_CHK,
        tab_items=tab_items or [],
        is_edit=False,
        langs=_langs,
    )


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    """
    GET  → tree view
    POST → batch update (SortM + AcM) or batch delete
    """
    if request.method == "POST":
        action = request.form.get("_action", "update")
        if action == "delete":
            _batch_delete(request.form.getlist("item_id"))
        else:
            _batch_update()
        return redirect(url_for("menu.index"))

    lang_filter = request.args.get("lang", "").strip()
    menus_all = _get_all_menus()
    if lang_filter:
        try:
            lang_filter_int = int(lang_filter)
            menus_filtered = [m for m in menus_all if m.lang == lang_filter_int]
        except (ValueError, TypeError):
            menus_filtered = menus_all
            lang_filter = ""
    else:
        menus_filtered = menus_all
    tree = _build_tree(menus_filtered)
    langs = get_active_langs()
    return render_template(
        "menu/index.html",
        tree=tree,
        total=len(menus_filtered),
        menu_ac=MENU_AC,
        langs=langs,
        lang_filter=lang_filter,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    """
    GET  → form with optional ?parent_idm=... pre-selection
    POST → generate IDM, save, redirect

    Parent is fetched exactly once and passed to both _field_errors and
    _next_idm to avoid redundant DB round-trips.
    """
    parents = _get_eligible_parents()
    tab_items = _get_tab_positions()

    if request.method == "POST":
        record = Menu()
        _parse_form(record)

        parent_idm = request.form.get("parent_idm", "").strip() or None
        # Single fetch — reused by validation, IDM generation, and levels calc.
        parent = db.session.get(Menu, parent_idm) if parent_idm else None

        form_errors = _field_errors(record, parent, is_new=True)
        if form_errors:
            return _render_create_form(record, parents, parent_idm, form_errors, tab_items)

        try:
            new_idm = _next_idm(parent)
        except ValueError as exc:
            flash(str(exc), "danger")
            return _render_create_form(record, parents, parent_idm, {})

        record.IDM = new_idm
        record.levels = 1 if parent is None else (parent.levels or 1) + 1

        db.session.add(record)
        db.session.flush()   # write IDM so _handle_images + tblLink can use it
        _handle_images(record)
        if not commit_or_flash(
            f'Đã thêm danh mục "{record.name}" ({record.IDM}).',
            action=f"create Menu {record.IDM}",
        ):
            return redirect(url_for("menu.index"))
        _sync_tbl_link(record.IDM, lang=record.lang or 1)
        return redirect(url_for("menu.index"))

    # GET — pre-select parent if provided via query string
    pre_parent = request.args.get("parent_idm", "").strip() or None
    return _render_create_form(Menu(), parents, pre_parent, {}, tab_items)


@bp.route("/<menu_idm>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(menu_idm: str):
    """
    Edit name / type_m / lang.
    IDM and parent (levels) are immutable — changing them would cascade
    across tblMenu children, tblNews.MenuIDN, and tblLink.RowIDM.
    """
    record = db.session.get(Menu, menu_idm)
    if record is None:
        flash("Danh mục không tồn tại.", "danger")
        return redirect(url_for("menu.index"))

    tab_items = _get_tab_positions()

    if request.method == "POST":
        _parse_form(record)
        form_errors = _field_errors(record, parent=None, is_new=False)
        if form_errors:
            _langs = get_active_langs()
            return render_template(
                "menu/form.html",
                menu=record,
                parents=[],
                selected_parent_idm=record.parent_idm,
                form_errors=form_errors,
                menu_types=MENU_TYPES,
                menu_langs=MENU_LANGS,
                menu_ac=MENU_AC,
                menu_chk=MENU_CHK,
                tab_items=tab_items,
                is_edit=True,
                langs=_langs,
            )
        _handle_images(record)
        if not commit_or_flash(
            f'Đã cập nhật danh mục "{record.name}".',
            action=f"update Menu {menu_idm}",
        ):
            return redirect(url_for("menu.index"))
        _sync_tbl_link(record.IDM, lang=record.lang or 1)
        return redirect(url_for("menu.index"))

    _langs = get_active_langs()
    return render_template(
        "menu/form.html",
        menu=record,
        parents=[],
        selected_parent_idm=record.parent_idm,
        form_errors={},
        menu_types=MENU_TYPES,
        menu_langs=MENU_LANGS,
        menu_ac=MENU_AC,
        menu_chk=MENU_CHK,
        tab_items=tab_items,
        is_edit=True,
        langs=_langs,
    )


@bp.route("/<menu_idm>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(menu_idm: str):
    """
    Single-row delete with safety checks:
      1. Block if menu has children (prevents orphaned sub-tree).
      2. Block if news articles reference this IDM (prevents orphaned news).
    """
    record = db.session.get(Menu, menu_idm)
    if record is None:
        flash("Danh mục không tồn tại.", "danger")
        return redirect(url_for("menu.index"))

    if _has_children(record):
        flash(
            f'Không thể xóa "{record.name}" — danh mục này còn danh mục con. '
            "Hãy xóa các danh mục con trước.",
            "danger",
        )
        return redirect(url_for("menu.index"))

    nc = _news_count(record.IDM)
    if nc > 0:
        flash(
            f'Không thể xóa "{record.name}" — còn {nc} bài tin tức thuộc danh mục này. '
            "Hãy chuyển hoặc xóa các bài đó trước.",
            "danger",
        )
        return redirect(url_for("menu.index"))

    _delete_tbl_link(menu_idm)
    delete_menu_image_file(record.img_m)
    delete_menu_image_file(record.img_m1)
    db.session.delete(record)
    commit_or_flash(
        f'Đã xóa danh mục "{record.name}" ({menu_idm}).',
        action=f"delete Menu {menu_idm}",
    )
    return redirect(url_for("menu.index"))


# ------------------------------------------------------------------ #
# Batch update / delete (string PK — does NOT cast to int)
# ------------------------------------------------------------------ #

def _batch_update() -> None:
    """
    Update SortM and AcM for every menu visible in the table.

    Mirrors VB btnUpdate1_Click: reads txtSort / drlAc per grid row and
    issues UPDATE tblMenu SET SortM=..., AcM=... for each.

    Form field naming:
      sort_<IDM>  → SortM
      ac_<IDM>    → AcM
    Only rows whose IDM appears as a sort_<IDM> key are touched, so
    rows not rendered (e.g. orphans) are left unchanged.
    """
    updated = 0
    for key, value in request.form.items():
        if not key.startswith("sort_"):
            continue
        idm = key[5:]  # strip "sort_" prefix
        record = db.session.get(Menu, idm)
        if record is None:
            continue

        sort_val = value.strip() or "00"
        try:
            ac_val = int(request.form.get(f"ac_{idm}", record.is_active))
        except (ValueError, TypeError):
            ac_val = record.is_active

        record.sort_order = sort_val
        record.is_active = ac_val
        updated += 1

    commit_or_flash(f"Đã cập nhật {updated} danh mục.", action="batch_update Menu")


def _batch_delete(item_ids: list) -> None:
    """
    Batch-delete selected menu items.
    Each item is validated with the same guards as single-row delete.
    Items that fail guards are skipped with a warning flash.
    """
    if not item_ids:
        flash("Chọn ít nhất một mục để xóa.", "warning")
        return

    deleted: list[str] = []
    skipped: list[str] = []

    for idm in item_ids:
        idm = idm.strip()
        if not idm:
            continue
        record = db.session.get(Menu, idm)
        if record is None:
            continue

        if _has_children(record):
            skipped.append(f'"{record.name}" (còn danh mục con)')
            continue

        nc = _news_count(record.IDM)
        if nc > 0:
            skipped.append(f'"{record.name}" ({nc} bài tin)')
            continue

        delete_menu_image_file(record.img_m)
        delete_menu_image_file(record.img_m1)
        db.session.delete(record)
        deleted.append(idm)

    if deleted:
        commit_or_flash(
            f"Đã xóa {len(deleted)} danh mục.", action="batch_delete Menu"
        )
    if skipped:
        flash(
            "Bỏ qua: " + "; ".join(skipped) + " — xóa con hoặc bài viết trước.",
            "warning",
        )
