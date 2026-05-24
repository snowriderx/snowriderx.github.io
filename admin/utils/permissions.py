"""
Permission helpers for tblPermissions.

VB phanquyen.aspx.vb pattern:
  - Per user, per menu entry with 5 flags (AddNews, EditNews, DelNews, ChkNews, Upfile).
  - Super-admin (IDU=1) always has full access — excluded from permission UI.
  - Regular admins (Type=1) can manage permissions for other admins.
  - Non-admins (Type=0) are not exposed in the VB permission UI.

Usage:
    perms = load_user_permissions(user_id)       # dict[menu_id, Permission]
    allowed = check_permission(user_id, menu_id, 'add')
"""

from __future__ import annotations

import logging
from functools import wraps

from flask import abort
from flask_login import current_user
from sqlalchemy import select

from extensions import db
from models.permission import Permission

log = logging.getLogger(__name__)

# Maps action name → Permission column attribute
_ACTION_ATTR: dict[str, str] = {
    "add":  "can_add",
    "edit": "can_edit",
    "del":  "can_del",
    "chk":  "can_chk",
    "up":   "can_up",
}


def load_user_permissions(user_id: int) -> dict[str, Permission]:
    """
    Load all permission rows for a user in a single query.

    Returns a dict keyed by menu_id (nvarchar 6) → Permission object.
    VB queries one row per menu item (N+1). Flask loads all at once.
    """
    rows = db.session.execute(
        select(Permission).where(Permission.user_id == user_id)
    ).scalars().all()
    return {row.menu_id: row for row in rows if row.menu_id}


def delete_user_permissions(user_id: int) -> None:
    """
    Delete all tblPermissions rows for a user.

    Call this before deleting a user or when demoting them from admin (Type=1→0).
    VB has no equivalent — it leaves orphaned permission rows. Flask cleans up.
    """
    db.session.execute(
        db.text('DELETE FROM "tblPermissions" WHERE "UserID" = :uid'),
        {"uid": user_id},
    )


def check_permission(user_id: int, menu_id: str, action: str) -> bool:
    """
    Check if user has permission to perform action on menu_id.

    action: 'add' | 'edit' | 'del' | 'chk' | 'up'

    Super-admin (IDU=1) always returns True — no DB query needed.
    All other users must have an explicit tblPermissions row with the flag set.

    VB check (phanquyen.aspx.vb): reads tblPermissions WHERE UserID=u AND MenuID=m,
    checks the specific flag column.
    """
    # IDU=1 check is a pure integer compare — avoids a User DB fetch
    if user_id == 1:
        return True

    attr = _ACTION_ATTR.get(action)
    if not attr:
        return False

    perm = db.session.execute(
        select(Permission).where(
            Permission.user_id == user_id,
            Permission.menu_id == menu_id,
        )
    ).scalar_one_or_none()

    if perm is None:
        return False

    return bool(getattr(perm, attr, 0))


def require_permission(action: str, menu_id_arg: str = "menu_id"):
    """
    Decorator that enforces a permission check before a route runs.

    action:       'add' | 'edit' | 'del' | 'chk' | 'up'
    menu_id_arg:  name of the POST/GET param that carries the menu_id.

    Super-admin (IDU=1) always passes.
    Aborts 403 if permission denied.

    Usage:
        @bp.route('/new', methods=['GET', 'POST'])
        @login_required
        @require_permission('add')
        def create(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request as _req

            # Super-admin bypass
            if current_user.is_authenticated and current_user.IDU == 1:
                return f(*args, **kwargs)

            # Determine menu_id: try form POST, then query string
            menu_id = (
                _req.form.get(menu_id_arg, "").strip()
                or _req.args.get(menu_id_arg, "").strip()
                or kwargs.get(menu_id_arg, "")
            )

            if not menu_id:
                # Cannot determine menu context — allow GET (form display),
                # block POST mutations without a valid menu_id
                if _req.method == "POST":
                    log.warning(
                        "permission_denied action=%s user=%s no_menu_id",
                        action, current_user.get_id(),
                    )
                    abort(403)
                return f(*args, **kwargs)

            if not check_permission(current_user.IDU, menu_id, action):
                log.warning(
                    "permission_denied action=%s user=%s menu=%s",
                    action, current_user.get_id(), menu_id,
                )
                abort(403)

            return f(*args, **kwargs)
        return wrapper
    return decorator
