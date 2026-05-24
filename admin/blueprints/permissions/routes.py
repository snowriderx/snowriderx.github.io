"""
Permissions blueprint — manage per-user, per-menu access flags in tblPermissions.

VB equivalent: phanquyen.aspx / phanquyen.aspx.vb

VB behaviour summary:
  - Dropdown: SELECT IDU, Users FROM tblUser WHERE Type=1 AND IDU<>1 ORDER BY Users
  - Menu tree: L1 uses TypeM IN (1,2,3); L2/L3 sub-queries use TypeM IN (1,2).
    Sort: SortM ASC. Flask mirrors both.
  - Per-menu read: VB queries tblPermissions N+1 times (once per menu item).
    Flask loads ALL permissions for selected user in ONE query (dict lookup).
  - VB has a per-row chkSelect (master) checkbox — only inserts a row when chkSelect=True.
    Flask: inserts if any of the 5 flags is checked (functionally equivalent; edge case:
    VB can save an all-flags=0 row, Flask cannot — this grants nothing either way).
  - Save: DELETE FROM tblPermissions WHERE UserID=<id>
          INSERT row per checked menu with the 5 flag columns.

VB enforcement in news.aspx: button visibility only (client-side, not server-side).
Flask: server-side abort(403) — more secure than VB.

VB access: Type=1 (is_admin) only. IDU=1 (super-admin) excluded from user list.
Flask: same — @login_required + _admin_required(). Super-admin cannot be managed here.
"""

import logging

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from admin.blueprints.permissions import bp
from admin.utils.db import commit_or_flash
from extensions import db
from models.menu import Menu
from models.permission import Permission
from models.user import User
from admin.utils.access import super_admin_redirect
from admin.utils.permissions import delete_user_permissions, load_user_permissions

log = logging.getLogger(__name__)

_LANG = 1  # single-language site


@bp.before_request
def _guard():
    return super_admin_redirect()


def _get_admin_users() -> list[User]:
    """
    VB: SELECT IDU, Users FROM tblUser WHERE Type=1 AND IDU<>1 ORDER BY Users
    Excludes super-admin (IDU=1) — super-admin always has full access.
    """
    return (
        db.session.execute(
            select(User)
            .where(User.role == 1, User.IDU != 1)
            .order_by(User.username.asc())
        )
        .scalars()
        .all()
    )


def _get_menus() -> list[Menu]:
    """
    Load menus for the permission tree.

    VB BindData: L1 query uses TypeM IN (1,2,3); L2/L3 sub-queries use TypeM IN (1,2).
    Since Flask loads all levels flat then builds the tree, we mirror this by
    loading L1 with TypeM IN (1,2,3) and L2/L3 with TypeM IN (1,2), combined
    with an OR condition.

    VB sort: SortM ASC (with IDM as tiebreaker for NULLs).
    """
    from sqlalchemy import and_, or_

    return (
        db.session.execute(
            select(Menu)
            .where(
                Menu.lang == _LANG,
                or_(
                    and_(Menu.levels == 1, Menu.type_m.in_([1, 2, 3])),
                    and_(Menu.levels != 1, Menu.type_m.in_([1, 2])),
                ),
            )
            .order_by(Menu.sort_order.asc(), Menu.IDM.asc())
        )
        .scalars()
        .all()
    )


def _build_tree(menus: list[Menu]) -> list[dict]:
    """
    Build a 3-level nested list from flat tblMenu rows.

    Returns list of level-1 dicts, each with 'children' list of level-2 dicts,
    each with 'children' list of level-3 dicts.

    IDM hierarchy (zero-padded 6 chars):
      L1: XX0000   L2: XXYY00   L3: XXYYZZ
    Parent of L2 = IDM[:2]+'0000'; parent of L3 = IDM[:4]+'00'
    """
    l1: dict[str, dict] = {}
    l2: dict[str, dict] = {}

    for m in menus:
        node = {"menu": m, "children": []}
        lvl = m.levels or 1
        if lvl == 1:
            l1[m.IDM] = node
        elif lvl == 2:
            l2[m.IDM] = node
            parent_key = m.IDM[:2] + "0000"
            if parent_key in l1:
                l1[parent_key]["children"].append(node)
        elif lvl == 3:
            parent_key = m.IDM[:4] + "00"
            if parent_key in l2:
                l2[parent_key]["children"].append(node)

    return list(l1.values())


# ------------------------------------------------------------------ #
# Main view
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """
    GET  ?user_id=N  — show permission tree for the selected admin user.
    POST             — save (DELETE + INSERT) permissions for user_id.

    VB: Page_Load (dropdown + tree) + btnPQ_Click (save).
    """
    admin_users = _get_admin_users()

    # Resolve selected user_id from POST or GET
    if request.method == "POST":
        try:
            sel_user_id = int(request.form.get("user_id", 0))
        except (ValueError, TypeError):
            sel_user_id = 0
    else:
        try:
            sel_user_id = int(request.args.get("user_id", 0))
        except (ValueError, TypeError):
            sel_user_id = 0

    sel_user = db.session.get(User, sel_user_id) if sel_user_id else None

    # Validate: must be an admin user, not IDU=1
    if sel_user and (sel_user.IDU == 1 or not sel_user.is_admin):
        flash("Không thể quản lý quyền cho tài khoản này.", "warning")
        return redirect(url_for("permissions.index"))

    # ── POST: save permissions ───────────────────────────────────────
    if request.method == "POST":
        if sel_user is None:
            flash("Vui lòng chọn người dùng.", "warning")
            return redirect(url_for("permissions.index"))

        menus = _get_menus()

        # VB: DELETE FROM tblPermissions WHERE UserID=<id>
        delete_user_permissions(sel_user_id)

        # INSERT a row per menu that has at least one flag checked
        inserted = 0
        for m in menus:
            mid = m.IDM
            can_add  = 1 if request.form.get(f"add_{mid}")  else 0
            can_edit = 1 if request.form.get(f"edit_{mid}") else 0
            can_del  = 1 if request.form.get(f"del_{mid}")  else 0
            can_chk  = 1 if request.form.get(f"chk_{mid}")  else 0
            can_up   = 1 if request.form.get(f"up_{mid}")   else 0

            if any([can_add, can_edit, can_del, can_chk, can_up]):
                perm = Permission(
                    user_id=sel_user_id,
                    menu_id=mid,
                    can_add=can_add,
                    can_edit=can_edit,
                    can_del=can_del,
                    can_chk=can_chk,
                    can_up=can_up,
                )
                db.session.add(perm)
                inserted += 1

        commit_or_flash("Lưu quyền thành công!", action="save_permissions")
        return redirect(url_for("permissions.index", user_id=sel_user_id))

    # ── GET: render tree ─────────────────────────────────────────────
    menus = _get_menus()
    tree = _build_tree(menus)
    perm_map: dict[str, Permission] = {}
    if sel_user:
        perm_map = load_user_permissions(sel_user_id)

    return render_template(
        "permissions/index.html",
        admin_users=admin_users,
        sel_user_id=sel_user_id,
        sel_user=sel_user,
        tree=tree,
        perm_map=perm_map,
    )
