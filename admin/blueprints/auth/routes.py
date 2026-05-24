"""
Auth blueprint — login / logout.

Password storage strategy (lazy bcrypt migration):
  - New/changed passwords → stored as werkzeug bcrypt hash in BcryptHash column.
  - Legacy passwords → still in Pass column as DES+Base64 (from VB migration).
  - Login tries bcrypt first; if no hash yet, falls back to DES and upgrades on success.
  - Once all users have logged in at least once, Pass column and DES code can be dropped.
"""

import logging
from urllib.parse import urlsplit

from flask import (
    current_app, render_template, redirect, url_for, request, flash,
    make_response,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from sqlalchemy import select

from admin.blueprints.auth import bp
from extensions import db, limiter
from admin.utils.db import commit_or_flash
from models.user import User
from admin.utils.auth import encrypt, kill_chars, make_auth_cookie

log = logging.getLogger(__name__)


def _is_safe_redirect(url: str) -> bool:
    """
    Reject open-redirect attempts in the ?next= parameter.
    Only allow relative paths on the same host.
    """
    if not url:
        return False
    parsed = urlsplit(url)
    # Safe: no scheme, no netloc (i.e. relative path like /admin/dashboard)
    return not parsed.scheme and not parsed.netloc


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_LOGIN"],
    methods=["POST"],
)
def login():
    if current_user.is_authenticated:
        dest = url_for("dashboard.index") if current_user.IDU == 1 else url_for("news.index")
        return redirect(dest)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        # NOTE: do NOT strip password — a password with leading/trailing
        # spaces would encrypt differently after stripping.
        password = request.form.get("password", "")

        if not username or not password:
            flash("Vui lòng nhập tên đăng nhập và mật khẩu.", "danger")
            return render_template("auth/login.html")

        safe_username = kill_chars(username)

        # Look up by username only — verify password in Python
        candidate = db.session.execute(
            select(User)
            .where(
                User.username == safe_username,
                User.is_active_flag == 1,
                User.role == 1,
            )
            .limit(1)
        ).scalar_one_or_none()

        user = None
        if candidate:
            if candidate.bcrypt_hash:
                # Modern path: bcrypt verify
                if check_password_hash(candidate.bcrypt_hash, password):
                    user = candidate
            else:
                # Legacy path: DES verify, then upgrade to bcrypt
                if candidate.password == encrypt(password):
                    candidate.bcrypt_hash = generate_password_hash(password)
                    db.session.commit()
                    log.info("action=bcrypt_upgrade user=%s", candidate.username)
                    user = candidate

        if user:
            login_user(user, remember=True)
            log.info(
                "action=login user=%s ip=%s",
                user.username, request.remote_addr,
            )

            # Set VB-compatible __tkad_id cookie using our DES value.
            # This is separate from Flask-Login's __fl_remember token.
            next_url = request.args.get("next", "")
            default_url = (
                url_for("news.index") if user.IDU != 1
                else url_for("dashboard.index")
            )
            safe_next = (
                next_url if _is_safe_redirect(next_url)
                else default_url
            )

            resp = make_response(redirect(safe_next))
            resp.set_cookie(
                "__tkad_id",
                make_auth_cookie(user.IDU),
                max_age=86400,
                httponly=True,
                samesite="Lax",
            )
            return resp

        log.warning(
            "action=login_failed user=%s ip=%s",
            username, request.remote_addr,
        )
        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "danger")

    return render_template("auth/login.html")


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_CHANGE_PW"],
    methods=["POST"],
)
def change_password():
    """
    Change password for the currently logged-in user.

    VB equivalent: pass.aspx (btnAddU1_Click)
    VB SQL: UPDATE tblUser SET Pass='<Encrypt(new_pw)>' WHERE IDU='<idu>'

    Difference from VB: we verify the current password server-side.
    VB only does a client-side CompareValidator against a hidden plaintext
    field — no server-side check. DB update logic is identical.
    """
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        form_errors = {}

        if not current_pw:
            form_errors["current_password"] = (
                "Vui lòng nhập mật khẩu hiện tại."
            )
        if not new_pw:
            form_errors["new_password"] = "Vui lòng nhập mật khẩu mới."
        if not confirm_pw:
            form_errors["confirm_password"] = (
                "Vui lòng xác nhận mật khẩu mới."
            )

        if not form_errors:
            # Verify current password — bcrypt first, fallback DES
            if current_user.bcrypt_hash:
                pw_ok = check_password_hash(current_user.bcrypt_hash, current_pw)
            else:
                pw_ok = (encrypt(current_pw) == current_user.password)
            if not pw_ok:
                form_errors["current_password"] = (
                    "Mật khẩu hiện tại không đúng."
                )
            elif len(new_pw) < 8:
                form_errors["new_password"] = (
                    "Mật khẩu mới phải có ít nhất 8 ký tự."
                )
            elif new_pw == current_pw:
                form_errors["new_password"] = (
                    "Mật khẩu mới phải khác mật khẩu hiện tại."
                )
            elif new_pw != confirm_pw:
                form_errors["confirm_password"] = (
                    "Xác nhận mật khẩu không khớp."
                )

        if form_errors:
            return render_template("auth/change_password.html",
                                   form_errors=form_errors)

        current_user.bcrypt_hash = generate_password_hash(new_pw)
        current_user.password = None  # clear DES hash once bcrypt is set
        if not commit_or_flash("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.", action="password_changed"):
            return render_template("auth/change_password.html", form_errors={})

        # Invalidate the current session so the user must re-authenticate
        # with the new password. Also clear the VB-compatible cookie.
        logout_user()
        resp = make_response(redirect(url_for("auth.login")))
        resp.set_cookie(
            "__tkad_id", "", max_age=0, httponly=True, samesite="Lax",
        )
        return resp

    return render_template("auth/change_password.html", form_errors={})


@bp.route("/logout")
def logout():
    """
    Replicate VB index.aspx?do=logout.
    No @login_required — calling logout on an unauthenticated request
    should simply redirect to login without a loop.
    """
    username = current_user.username if current_user.is_authenticated else "-"
    logout_user()
    log.info("action=logout user=%s", username)
    resp = make_response(redirect(url_for("auth.login")))
    resp.set_cookie("__tkad_id", "", max_age=0, httponly=True, samesite="Lax")
    return resp
