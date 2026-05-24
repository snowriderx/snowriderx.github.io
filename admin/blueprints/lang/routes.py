"""
Lang blueprint — CRUD for tblLangM (language-2 menu tree).

VB equivalent: lang.aspx / lang.aspx.vb

tblLangM has the same schema as tblMenu. This blueprint manages the
navigation structure for the second site language (typically English).

Operations mirror menu.aspx exactly:
  - List: tree view, batch update SortM + AcM
  - Delete: blocked if children exist; cascades tblLink
  - Create/Edit: full menu fields + tblLink sync

Routes:
  GET/POST /admin/lang/              list + batch update/delete
  GET/POST /admin/lang/new           create
  GET/POST /admin/lang/<idm>/edit    edit
  POST     /admin/lang/<idm>/delete  delete
"""

import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select, text

from admin.blueprints.lang import lang_bp
from extensions import db, limiter
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash


@lang_bp.before_request
def _guard():
    return super_admin_redirect()


from models.lang import LangMenu, LANG_AC, LANG_TYPES

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Tree helpers (mirrors menu/routes.py)
# ------------------------------------------------------------------ #

def _get_all_menus() -> list[LangMenu]:
    try:
        return (
            db.session.execute(
                select(LangMenu).order_by(LangMenu.sort_order.asc(), LangMenu.IDM.asc())
            )
            .scalars()
            .all()
        )
    except Exception:
        db.session.rollback()
        return []


def _build_tree(menus: list[LangMenu]) -> list[dict]:
    level1: list[LangMenu] = []
    l2_by_l1: dict[str, list[LangMenu]] = {}
    l3_by_l2: dict[str, list[LangMenu]] = {}

    for m in menus:
        lvl = m.levels or 1
        idm = m.IDM or ""
        if lvl == 1:
            level1.append(m)
        elif lvl == 2:
            l2_by_l1.setdefault(idm[:2], []).append(m)
        elif lvl == 3:
            l3_by_l2.setdefault(idm[:4], []).append(m)

    tree = []
    for m1 in level1:
        p1 = (m1.IDM or "")[:2]
        children_l2 = []
        for m2 in l2_by_l1.get(p1, []):
            p2 = (m2.IDM or "")[:4]
            children_l3 = [{"menu": m3, "children": []} for m3 in l3_by_l2.get(p2, [])]
            children_l2.append({"menu": m2, "children": children_l3})
        tree.append({"menu": m1, "children": children_l2})
    return tree


# ------------------------------------------------------------------ #
# IDM generation (mirrors menu/routes.py _next_idm)
# ------------------------------------------------------------------ #

def _next_idm(parent: "LangMenu | None") -> str:
    if parent is None:
        existing = db.session.execute(
            select(LangMenu.IDM).where(LangMenu.levels == 1)
        ).scalars().all()
        if not existing:
            return "010000"
        max_xx = max(int(idm[:2]) for idm in existing if idm and len(idm) >= 2)
        nxt = max_xx + 1
        if nxt > 99:
            raise ValueError("Đã đạt tối đa 99 mục cấp 1.")
        return f"{nxt:02d}0000"

    parent_level = parent.levels or 1
    if parent_level == 1:
        prefix = (parent.IDM or "")[:2]
        existing = db.session.execute(
            select(LangMenu.IDM).where(LangMenu.levels == 2, LangMenu.IDM.like(f"{prefix}__00"))
        ).scalars().all()
        if not existing:
            return f"{prefix}0100"
        max_yy = max(int(idm[2:4]) for idm in existing if idm and len(idm) >= 4)
        nxt = max_yy + 1
        if nxt > 99:
            raise ValueError(f"Đã đạt tối đa 99 mục cấp 2 dưới '{parent.name}'.")
        return f"{prefix}{nxt:02d}00"

    if parent_level == 2:
        prefix = (parent.IDM or "")[:4]
        existing = db.session.execute(
            select(LangMenu.IDM).where(LangMenu.levels == 3, LangMenu.IDM.like(f"{prefix}__"))
        ).scalars().all()
        if not existing:
            return f"{prefix}01"
        max_zz = max(int(idm[4:6]) for idm in existing if idm and len(idm) >= 6)
        nxt = max_zz + 1
        if nxt > 99:
            raise ValueError(f"Đã đạt tối đa 99 mục cấp 3 dưới '{parent.name}'.")
        return f"{prefix}{nxt:02d}"

    raise ValueError("Không thể tạo mục cấp 4 (tối đa 3 cấp).")


# ------------------------------------------------------------------ #
# Delete guards
# ------------------------------------------------------------------ #

def _has_children(menu: LangMenu) -> bool:
    lvl = menu.levels or 1
    idm = menu.IDM or ""
    if lvl == 1:
        pattern, child_level = idm[:2] + "__00", 2
    elif lvl == 2:
        pattern, child_level = idm[:4] + "__", 3
    else:
        return False
    count = db.session.execute(
        select(func.count()).where(LangMenu.levels == child_level, LangMenu.IDM.like(pattern))
    ).scalar() or 0
    return count > 0


# ------------------------------------------------------------------ #
# tblLink sync (mirrors VB lang.aspx.vb btnAddU1_Click)
# ------------------------------------------------------------------ #

def _sync_tbl_link(idm: str, lang: int = 2) -> None:
    """
    VB lang.aspx.vb btnAddU1_Click:
      DELETE tblLink WHERE RowIDM=IDM AND RowType=1 AND RowLang=lang
      INSERT INTO tblLink (...) SELECT AutoM,Name1M,1,TypeM,Levels,IDM,
        [title],keywords,description,NameMH,Lang FROM tblLangM WHERE IDM=IDM
    """
    try:
        db.session.execute(
            text('DELETE FROM "tblLink" WHERE "RowIDM" = :idm AND "RowType" = 1 AND "RowLang" = :lang'),
            {"idm": idm, "lang": lang},
        )
        db.session.execute(
            text("""
                INSERT INTO "tblLink"
                    ("RowID", "RowUrl", "RowType", "RowTypeM", "RowLevels",
                     "RowIDM", "title", "keywords", "description", "RowName", "RowLang")
                SELECT "AutoM", "Name1M", 1, "TypeM", "Levels", "IDM",
                       "title", "keywords", "description", "NameMH", "Lang"
                FROM "tblLangM" WHERE "IDM" = :idm
            """),
            {"idm": idm},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink sync failed for langmenu %s: %s", idm, exc)


def _delete_tbl_link(idm: str) -> None:
    """
    VB lang.aspx.vb dtgrView_DeleteCommand cascade:
      If Level 1: Delete tblLink WHERE Left(RowIDM,2)=Left(IDM,2) AND RowType=1 AND RowLang=...
      Else:       Delete tblLink WHERE RowIDM=IDM AND RowType=1
    """
    try:
        db.session.execute(
            text('DELETE FROM "tblLink" WHERE "RowIDM" = :idm AND "RowType" = 1'),
            {"idm": idm},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink delete failed for langmenu %s: %s", idm, exc)


def _delete_tbl_link_cascade(idm_prefix2: str) -> None:
    """Delete all tblLink rows for a Level-1 item and its children."""
    try:
        db.session.execute(
            text('DELETE FROM "tblLink" WHERE LEFT("RowIDM", 2) = :px AND "RowType" = 1'),
            {"px": idm_prefix2},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink cascade delete failed for prefix %s: %s", idm_prefix2, exc)


# ------------------------------------------------------------------ #
# Form helpers
# ------------------------------------------------------------------ #

def _parse_form(record: LangMenu) -> None:
    from admin.utils.text import slugify_vi
    g = lambda key, default="": request.form.get(key, default).strip()

    record.name = g("name")
    raw_slug = g("slug")
    record.slug = raw_slug if raw_slug else slugify_vi(record.name)
    record.sort_order = g("sort_order") or "00"

    _mapped = LangMenu.__mapper__.columns.keys()
    if "name_mh"     in _mapped: record.name_mh    = g("name_mh") or None
    if "url"         in _mapped: record.url         = g("url") or None
    if "desc_m"      in _mapped: record.desc_m      = request.form.get("desc_m", "").strip() or None
    if "seo_title"   in _mapped: record.seo_title   = g("seo_title") or None
    if "keywords"    in _mapped: record.keywords    = g("keywords") or None
    if "description" in _mapped: record.description = g("description") or None
    if "home_m"      in _mapped:
        try:
            record.home_m = 1 if request.form.get("home_m") else 0
        except Exception:
            record.home_m = 0

    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1
    try:
        record.type_m = int(request.form.get("type_m", 1))
    except (ValueError, TypeError):
        record.type_m = 1
    try:
        record.lang = int(request.form.get("lang", 2))
    except (ValueError, TypeError):
        record.lang = 2


def _field_errors(record: LangMenu, parent: "LangMenu | None", is_new: bool) -> dict:
    errors: dict = {}
    if not (record.name or "").strip():
        errors["name"] = "Tên là trường bắt buộc."
    elif len(record.name) > 200:
        errors["name"] = "Không được vượt quá 200 ký tự."
    if record.slug and len(record.slug) > 100:
        errors["slug"] = "Slug không được vượt quá 100 ký tự."
    if is_new and request.form.get("parent_idm"):
        if parent is None:
            errors["parent_idm"] = "Mục cha không tồn tại."
        elif (parent.levels or 1) >= 3:
            errors["parent_idm"] = "Không thể tạo mục cấp 4."
    return errors


def _get_eligible_parents() -> list[LangMenu]:
    try:
        return (
            db.session.execute(
                select(LangMenu)
                .where(LangMenu.levels.in_([1, 2]))
                .order_by(LangMenu.sort_order.asc(), LangMenu.IDM.asc())
            )
            .scalars()
            .all()
        )
    except Exception:
        db.session.rollback()
        return []


def _render_form(record, parents, selected_parent_idm, form_errors, is_edit):
    return render_template(
        "lang/form.html",
        menu=record,
        parents=parents,
        selected_parent_idm=selected_parent_idm,
        form_errors=form_errors,
        lang_types=LANG_TYPES,
        lang_ac=LANG_AC,
        is_edit=is_edit,
    )


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@lang_bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"], methods=["POST"])
def index():
    table_missing = False

    if request.method == "POST":
        action = request.form.get("_action", "update")
        if action == "delete":
            _batch_delete(request.form.getlist("item_id"))
        else:
            _batch_update()
        return redirect(url_for("lang.index"))

    menus = _get_all_menus()
    if not menus:
        # Check whether the table truly doesn't exist (vs just empty)
        try:
            db.session.execute(text('SELECT "IDM" FROM "tblLangM" LIMIT 1'))
        except Exception:
            db.session.rollback()
            table_missing = True

    tree = _build_tree(menus)
    return render_template(
        "lang/index.html",
        tree=tree,
        total=len(menus),
        lang_ac=LANG_AC,
        table_missing=table_missing,
    )


@lang_bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"], methods=["POST"])
def create():
    parents = _get_eligible_parents()

    if request.method == "POST":
        record = LangMenu()
        _parse_form(record)

        parent_idm = request.form.get("parent_idm", "").strip() or None
        parent = db.session.get(LangMenu, parent_idm) if parent_idm else None

        form_errors = _field_errors(record, parent, is_new=True)
        if form_errors:
            return _render_form(record, parents, parent_idm, form_errors, is_edit=False)

        try:
            new_idm = _next_idm(parent)
        except ValueError as exc:
            flash(str(exc), "danger")
            return _render_form(record, parents, parent_idm, {}, is_edit=False)

        record.IDM = new_idm
        record.levels = 1 if parent is None else (parent.levels or 1) + 1
        db.session.add(record)
        if not commit_or_flash(f'Đã thêm "{record.name}" ({record.IDM}).', action=f"create LangMenu {record.IDM}"):
            return redirect(url_for("lang.index"))
        _sync_tbl_link(record.IDM, lang=record.lang or 2)
        return redirect(url_for("lang.index"))

    pre_parent = request.args.get("parent_idm", "").strip() or None
    return _render_form(LangMenu(lang=2), parents, pre_parent, {}, is_edit=False)


@lang_bp.route("/<menu_idm>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"], methods=["POST"])
def edit(menu_idm: str):
    record = db.session.get(LangMenu, menu_idm)
    if record is None:
        flash("Không tìm thấy mục.", "danger")
        return redirect(url_for("lang.index"))

    if request.method == "POST":
        _parse_form(record)
        form_errors = _field_errors(record, parent=None, is_new=False)
        if form_errors:
            return _render_form(record, [], record.parent_idm, form_errors, is_edit=True)
        if not commit_or_flash(f'Đã cập nhật "{record.name}".', action=f"update LangMenu {menu_idm}"):
            return redirect(url_for("lang.index"))
        _sync_tbl_link(record.IDM, lang=record.lang or 2)
        return redirect(url_for("lang.index"))

    return _render_form(record, [], record.parent_idm, {}, is_edit=True)


@lang_bp.route("/<menu_idm>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(menu_idm: str):
    record = db.session.get(LangMenu, menu_idm)
    if record is None:
        flash("Không tìm thấy mục.", "danger")
        return redirect(url_for("lang.index"))

    if _has_children(record):
        flash(
            f'Không thể xóa "{record.name}" — còn mục con. Hãy xóa mục con trước.',
            "danger",
        )
        return redirect(url_for("lang.index"))

    name = record.name  # capture before raw DELETE evicts from identity map

    # VB cascade: if level 1, also delete all children
    if (record.levels or 1) == 1:
        _delete_tbl_link_cascade((record.IDM or "")[:2])
        db.session.execute(
            text('DELETE FROM "tblLangM" WHERE LEFT("IDM", 2) = :px'),
            {"px": (record.IDM or "")[:2]},
        )
    else:
        _delete_tbl_link(menu_idm)
        db.session.delete(record)

    commit_or_flash(f'Đã xóa "{name}" ({menu_idm}).', action=f"delete LangMenu {menu_idm}")
    return redirect(url_for("lang.index"))


# ------------------------------------------------------------------ #
# Batch helpers
# ------------------------------------------------------------------ #

def _batch_update() -> None:
    updated = 0
    for key, value in request.form.items():
        if not key.startswith("sort_"):
            continue
        idm = key[5:]
        record = db.session.get(LangMenu, idm)
        if record is None:
            continue
        record.sort_order = value.strip() or "00"
        try:
            record.is_active = int(request.form.get(f"ac_{idm}", record.is_active))
        except (ValueError, TypeError):
            pass
        updated += 1
    commit_or_flash(f"Đã cập nhật {updated} mục.", action="batch_update LangMenu")


def _batch_delete(item_ids: list) -> None:
    if not item_ids:
        flash("Chọn ít nhất một mục để xóa.", "warning")
        return

    deleted, skipped = [], []
    for idm in item_ids:
        idm = idm.strip()
        if not idm:
            continue
        record = db.session.get(LangMenu, idm)
        if record is None:
            continue
        if _has_children(record):
            skipped.append(f'"{record.name}" (còn mục con)')
            continue
        _delete_tbl_link(idm)
        db.session.delete(record)
        deleted.append(idm)

    if deleted:
        commit_or_flash(f"Đã xóa {len(deleted)} mục.", action="batch_delete LangMenu")
    else:
        db.session.rollback()
    if skipped:
        flash("Bỏ qua: " + "; ".join(skipped), "warning")
