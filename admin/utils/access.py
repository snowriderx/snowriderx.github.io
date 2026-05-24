"""
Access control helpers.

VB pattern (all pages except news.aspx / pro.aspx / pass.aspx):
  If Val(Decrypt(cookie)) <> 1 Then Response.Redirect("news.aspx")

Flask equivalent: authenticated non-super-admin users are redirected to
news.index, not shown a 403, so the experience matches VB.
"""

from flask import redirect, url_for
from flask_login import current_user


def super_admin_redirect():
    """
    Guard for super-admin-only blueprints.

    - Unauthenticated → redirect to login page.
    - Authenticated non-super-admin → redirect to news.index (mirrors VB behaviour).
    - IDU=1 → return None (let the request continue).

    Usage inside a @bp.before_request hook:
        @bp.before_request
        def _guard():
            return super_admin_redirect()
    """
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.IDU != 1:
        return redirect(url_for("news.index"))
    return None
