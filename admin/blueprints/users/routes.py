"""
Users blueprint — CRUD for tblUser (admin accounts).

VB equivalent: user.aspx / user.aspx.vb

VB access control:
  - Checks __tkad_id cookie decrypts to Type=1; else redirect to news.aspx.
  Flask: @login_required + is_admin check (abort 403).

VB BindData SQL (exact):
  SELECT IDU as ID, Users as Name, Email, TimeU, Name as FullName, AcU, ImgU,
    (SELECT count(IDN) FROM tblNews WHERE uID=tblUser.IDU
     AND Month(TimeN)=Month(getdate()) AND Year(TimeN)=Year(getdate())) as Total,
    (SELECT count(IDN) FROM tblNews WHERE uID=tblUser.IDU
     AND Month(TimeN)=Month(DATEADD(month,-1,getdate())) AND Year(TimeN)=Year(getdate())) as Total1
  FROM tblUser WHERE Type=1
  ORDER BY TimeU DESC

VB btnSearch SQL: WHERE IDU<>1 AND Users LIKE '%<term>%' (no Type filter, no stats).
  Flask: always include stats in search results for UI consistency.

VB insert/update fields: Users, Pass(encrypted), Email, Name, FbL, WebL, DescU, AtU, Type, AcU, ImgU.
  FbL/WebL/DescU accessed with Try/Catch in VB — may not exist in all DB schemas.
  Flask: only uses verified columns from models/user.py (IDU, Users, Pass, AcU, Type, Email, Name, TimeU, ImgU).

VB eTop command: UPDATE tblUser SET TimeU=getdate() WHERE IDU=<id> — bumps to list top.

Security (Flask additions, not in VB):
  - IDU=1 (super-admin) cannot be deleted or deactivated.
  - Current user cannot delete themselves.
  - Password is never decrypted/shown in edit form (VB does this unsafely).
"""

import logging
from datetime import datetime, date

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select, text

from admin.blueprints.users import bp
from extensions import db, limiter
from werkzeug.security import generate_password_hash
from models.user import User
from admin.utils.access import super_admin_redirect
from admin.utils.auth import kill_chars
from admin.utils.db import commit_or_flash
from admin.utils.permissions import delete_user_permissions
from admin.utils.upload import delete_user_image, save_user_image, validate_upload_file

log = logging.getLogger(__name__)

_PAGE_SIZE = 15  # VB: dtgrView.PageSize = 15


@bp.before_request
def _guard():
    return super_admin_redirect()


def _stats_rows(search: str = "") -> list:
    """
    Run the VB BindData / btnSearch SQL equivalent with post statistics.

    Default (no search): WHERE Type=1, includes all admins (even IDU=1).
    Search mode: WHERE IDU<>1 AND Users LIKE '%q%' (VB btnSearch_Click).
    Both variants include this-month / last-month post counts from tblNews.
    """
    today = date.today()
    cur_month, cur_year = today.month, today.year
    if cur_month == 1:
        last_month, last_year = 12, cur_year - 1
    else:
        last_month, last_year = cur_month - 1, cur_year

    stats_cols = """
        (SELECT COUNT("IDN") FROM "tblNews"
         WHERE "uID" = "tblUser"."IDU"
           AND EXTRACT(MONTH FROM "TimeN") = :cm AND EXTRACT(YEAR FROM "TimeN") = :cy) AS posts_this_month,
        (SELECT COUNT("IDN") FROM "tblNews"
         WHERE "uID" = "tblUser"."IDU"
           AND EXTRACT(MONTH FROM "TimeN") = :lm AND EXTRACT(YEAR FROM "TimeN") = :ly) AS posts_last_month
    """
    base_cols = """"IDU", "Users", "Email", "TimeU", "Name" AS "FullName", "AcU", "ImgU", "Type" """

    if search:
        sql = text(f"""
            SELECT {base_cols}, {stats_cols}
            FROM "tblUser"
            WHERE "IDU" <> 1 AND "Users" ILIKE :q
            ORDER BY "TimeU" DESC
        """)
        params = {"cm": cur_month, "cy": cur_year, "lm": last_month, "ly": last_year,
                  "q": f"%{search}%"}
    else:
        sql = text(f"""
            SELECT {base_cols}, {stats_cols}
            FROM "tblUser"
            WHERE "Type" = 1
            ORDER BY "TimeU" DESC
        """)
        params = {"cm": cur_month, "cy": cur_year, "lm": last_month, "ly": last_year}

    return db.session.execute(sql, params).fetchall()


# ------------------------------------------------------------------ #
# List + batch operations
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    """
    List admin users with post statistics.

    POST _action=update → batch update AcU dropdown per row  (VB: btnUpdate1_Click)
    POST _action=delete → delete checked users + avatar files (VB: btnDel1_Click)
    """
    if request.method == "POST":
        action = request.form.get("_action", "update")
        if action == "delete":
            _batch_delete(request.form.getlist("item_id"))
        else:
            _batch_update(request.form.getlist("row_id"))
        search_q = request.form.get("search_q", "")
        return redirect(url_for("users.index", q=search_q) if search_q
                        else url_for("users.index"))

    search = request.args.get("q", "").strip()
    rows = _stats_rows(search)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    total = len(rows)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * _PAGE_SIZE
    paged_rows = rows[offset: offset + _PAGE_SIZE]

    return render_template(
        "users/index.html",
        rows=paged_rows,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total,
    )


def _batch_update(row_ids: list[str]) -> None:
    """
    VB btnUpdate1_Click: update AcU (active status) dropdown for all visible rows.
    Super-admin (IDU=1) AcU is always forced back to 1.
    """
    for raw_id in row_ids:
        try:
            rid = int(raw_id)
        except ValueError:
            continue
        user = db.session.get(User, rid)
        if user is None:
            continue
        if user.IDU == 1:
            continue  # never deactivate super-admin
        try:
            new_ac = int(request.form.get(f"ac_{rid}", user.is_active_flag))
        except (ValueError, TypeError):
            continue
        user.is_active_flag = new_ac
    commit_or_flash("Cập nhật thành công!", action="batch_update User")


def _batch_delete(item_ids: list[str]) -> None:
    """VB btnDel1_Click: delete checked users + their avatar files."""
    if not item_ids:
        flash("Chọn ít nhất một thành viên để xóa.", "warning")
        return
    deleted = 0
    for raw_id in item_ids:
        try:
            rid = int(raw_id)
        except ValueError:
            continue
        if rid == 1:
            flash("Không thể xóa tài khoản quản trị viên gốc.", "warning")
            continue
        if rid == current_user.IDU:
            flash("Không thể xóa tài khoản của chính bạn.", "warning")
            continue
        user = db.session.get(User, rid)
        if user is None:
            continue
        delete_user_image(rid)
        delete_user_permissions(rid)
        db.session.delete(user)
        deleted += 1
    if deleted:
        commit_or_flash(f"Đã xóa {deleted} thành viên thành công!", action="batch_delete User")
    else:
        db.session.rollback()


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
    """VB: btnAdd1_Click (show form) + btnAddU1_Click (save, lblID.Text=0 branch)."""
    form_data: dict = {}
    form_errors: dict = {}

    if request.method == "POST":
        username = kill_chars(request.form.get("username", "").strip())
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        fb_link = request.form.get("fb_link", "").strip()
        web_link = request.form.get("web_link", "").strip()
        bio = request.form.get("bio", "").strip()
        role = 1 if request.form.get("role") else 0
        is_active = 1 if request.form.get("is_active") else 0

        form_data = {
            "username": username, "email": email, "full_name": full_name,
            "fb_link": fb_link, "web_link": web_link, "bio": bio,
            "role": role, "is_active": is_active,
        }

        # VB: Select Users from tblUser WHERE Users=<name> AND IDU<>0 → duplicate check
        if not username:
            form_errors["username"] = "Tên đăng nhập là bắt buộc."
        else:
            dup = db.session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if dup:
                form_errors["username"] = (
                    "Tài khoản này đã được sử dụng. Vui lòng chọn tên khác."
                )

        if not password:
            form_errors["password"] = "Mật khẩu là bắt buộc."
        elif len(password) < 6:
            form_errors["password"] = "Mật khẩu phải có ít nhất 6 ký tự."

        img_err = validate_upload_file(request.files.get("avatar_file"))
        if img_err:
            form_errors["avatar_file"] = img_err

        if form_errors:
            return render_template(
                "users/form.html",
                form_data=form_data, form_errors=form_errors,
                is_edit=False, user=None,
            )

        user = User(
            username=username,
            bcrypt_hash=generate_password_hash(password),
            email=email or None,
            full_name=full_name or None,
            fb_link=fb_link or None,
            web_link=web_link or None,
            bio=bio or None,
            role=role,
            is_active_flag=is_active,
            at_u=0,  # VB: f.Add("AtU,0,1,4") : v.Add(0) — hardcoded
            time_updated=datetime.now(),
            avatar="null.gif",
        )
        db.session.add(user)
        db.session.flush()  # populate IDU before image upload

        filename = save_user_image(request.files.get("avatar_file"), user.IDU)
        if filename:
            user.avatar = filename

        if commit_or_flash("Thêm thành viên thành công!", action=f"create User {user.IDU}"):
            return redirect(url_for("users.index"))
        return redirect(url_for("users.index"))

    return render_template(
        "users/form.html",
        form_data={"is_active": 1, "role": 1},
        form_errors={}, is_edit=False, user=None,
    )


# ------------------------------------------------------------------ #
# Edit
# ------------------------------------------------------------------ #

@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(user_id: int):
    """VB: dtgrView_ItemCommand (edit) + btnAddU1_Click (save, lblID.Text<>0 branch)."""
    user = db.session.get(User, user_id)
    if user is None:
        flash("Thành viên không tồn tại.", "danger")
        return redirect(url_for("users.index"))

    form_errors: dict = {}

    if request.method == "POST":
        username = kill_chars(request.form.get("username", "").strip())
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        fb_link = request.form.get("fb_link", "").strip()
        web_link = request.form.get("web_link", "").strip()
        bio = request.form.get("bio", "").strip()
        old_role = user.role  # snapshot before form values overwrite
        # Protect super-admin: lock role and active status at 1
        role = 1 if (user_id == 1 or request.form.get("role")) else 0
        is_active = 1 if (user_id == 1 or request.form.get("is_active")) else 0

        form_data = {
            "username": username, "email": email, "full_name": full_name,
            "fb_link": fb_link, "web_link": web_link, "bio": bio,
            "role": role, "is_active": is_active,
        }

        if not username:
            form_errors["username"] = "Tên đăng nhập là bắt buộc."
        else:
            # VB: Select Users WHERE Users=<name> AND IDU<>lblID (duplicate check on update)
            dup = db.session.execute(
                select(User).where(User.username == username, User.IDU != user_id)
            ).scalar_one_or_none()
            if dup:
                form_errors["username"] = "Tài khoản này đã được sử dụng."

        if password and len(password) < 6:
            form_errors["password"] = "Mật khẩu phải có ít nhất 6 ký tự."

        img_err = validate_upload_file(request.files.get("avatar_file"))
        if img_err:
            form_errors["avatar_file"] = img_err

        if form_errors:
            return render_template(
                "users/form.html",
                form_data=form_data, form_errors=form_errors,
                is_edit=True, user=user,
            )

        user.username = username
        user.email = email or None
        user.full_name = full_name or None
        user.fb_link = fb_link or None
        user.web_link = web_link or None
        user.bio = bio or None
        user.role = role
        user.is_active_flag = is_active
        user.time_updated = datetime.now()

        # Revoke all menu permissions when an admin is demoted to editor
        if old_role == 1 and role == 0:
            delete_user_permissions(user_id)

        if password:
            user.bcrypt_hash = generate_password_hash(password)
            user.password = None  # clear DES hash once bcrypt is set

        if request.form.get("delete_avatar") == "1":
            delete_user_image(user_id)
            user.avatar = "null.gif"

        filename = save_user_image(request.files.get("avatar_file"), user_id)
        if filename:
            user.avatar = filename

        if commit_or_flash("Cập nhật thành viên thành công!", action=f"update User {user_id}"):
            return redirect(url_for("users.index"))
        return redirect(url_for("users.index"))

    form_data = {
        "username": user.username or "",
        "email": user.email or "",
        "full_name": user.full_name or "",
        "fb_link": user.fb_link or "",
        "web_link": user.web_link or "",
        "bio": user.bio or "",
        "role": user.role,
        "is_active": user.is_active_flag,
    }
    return render_template(
        "users/form.html",
        form_data=form_data, form_errors={},
        is_edit=True, user=user,
    )


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@bp.route("/<int:user_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(user_id: int):
    """VB: dtgrView_DeleteCommand — delete single user."""
    if user_id == 1:
        flash("Không thể xóa tài khoản quản trị viên gốc.", "danger")
        return redirect(url_for("users.index"))
    if user_id == current_user.IDU:
        flash("Không thể xóa tài khoản của chính bạn.", "danger")
        return redirect(url_for("users.index"))

    user = db.session.get(User, user_id)
    if user is None:
        flash("Thành viên không tồn tại.", "danger")
        return redirect(url_for("users.index"))

    delete_user_image(user_id)
    delete_user_permissions(user_id)
    db.session.delete(user)
    commit_or_flash("Xóa thành viên thành công!", action=f"delete User {user_id}")
    return redirect(url_for("users.index"))


# ------------------------------------------------------------------ #
# Bump to top (eTop)
# ------------------------------------------------------------------ #

@bp.route("/<int:user_id>/bump", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def bump(user_id: int):
    """
    VB: dtgrView_ItemCommand eTop command.
    UPDATE tblUser SET TimeU=getdate() WHERE IDU=<id>
    Moves user to top of the TimeU DESC sorted list.
    """
    user = db.session.get(User, user_id)
    if user is None:
        flash("Thành viên không tồn tại.", "danger")
        return redirect(url_for("users.index"))

    user.time_updated = datetime.now()
    commit_or_flash("Đã đưa thành viên lên đầu danh sách.", action=f"bump User {user_id}")
    return redirect(url_for("users.index"))
