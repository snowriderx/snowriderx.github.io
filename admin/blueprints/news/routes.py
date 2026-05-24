"""
News blueprint — CRUD for tblNews + tblLink sync.

VB equivalents:
  news.aspx / news.aspx.vb

VB list query (loadNews):
  SELECT IDN as ID, NameN as Name, Name1N, TimeN, AcN, ImgN, TypeN
  FROM tblNews, tblMenu
  WHERE MenuIDN = IDM [AND MenuIDN = '<menu_id>'] [AND NameN LIKE '%s%']
  AND Lang = '<lang>'
  ORDER BY TimeN DESC

VB insert/update columns:
  MenuIDN, NameN, Name1N, URL, TitleN, KeyN, DecripN, ContentN, DescN,
  TypeN, ScriptCode, AcN, uID (insert only), TimeN (update only)

VB tblLink sync (on every save):
  DELETE tblLink WHERE RowID='<id>' AND RowType=2 AND RowLang='<lang>'
  INSERT INTO tblLink (...) SELECT IDN, Name1N, 2, TypeM, Levels, IDM,
    TitleN, KeyN, DecripN, NameM, Lang FROM tblMenu, tblNews
    WHERE MenuIDN = IDM AND IDN = '<id>'

VB image upload (DellImg / UploadPic):
  Reads ImgN, deletes file at /images/news/<ImgN>
  Saves new file as <slug>_<id>.<ext> in /images/news/
  Python: saves as news_<id>.<ext> in /static/uploads/news/

VB eTop command:
  UPDATE tblNews SET TimeN=getdate() WHERE IDN=id

VB delete:
  DellImg (reads ImgN, deletes file)
  DELETE tblLink WHERE RowID=id AND RowType=2 AND RowLang=lang
  DELETE tblNews WHERE IDN=id

AcN values: 1=Hiển thị, 3=Ẩn khỏi danh mục, 0=Ẩn
TypeN values: 1=Tin bài (CKEditor body), 2=Landing page (raw HTML)
"""

import logging
import re
from datetime import datetime, timezone

from flask import (
    current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_, select, text

from admin.blueprints.news import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.lang import Lang, get_active_langs
from models.menu import Menu
from models.news import News, NEWS_STATUS, NEWS_TYPES
from admin.utils.crud import CrudController
from admin.utils.html import sanitize_html
from admin.utils.permissions import check_permission
from admin.utils.text import slugify_vi
from admin.utils.upload import (
    delete_news_image_file,
    save_news_image,
    validate_upload_file,
)

log = logging.getLogger(__name__)

# Language used for all menu queries (single-language site)
_LANG = 1


# ------------------------------------------------------------------ #
# Menu helpers
# ------------------------------------------------------------------ #

def _get_menus() -> list[Menu]:
    """
    Return news-category menu items (TypeM=1) ordered by IDM.

    VB LoadEditNews / LoadInsert:
      - IDU=1 (super-admin): SELECT IDM,... FROM tblMenu WHERE TypeM IN (1) AND Lang=1
      - Other users: JOIN tblPermissions WHERE IDM=MenuID AND UserID=<uid> AND TypeM IN (1)
        — only shows menus the user has ANY permission row for.

    Flask: super-admin sees all; other users see only permitted menus.
    """
    from models.permission import Permission

    base_q = (
        select(Menu)
        .where(Menu.type_m == 1, Menu.lang == _LANG)
        .order_by(Menu.IDM.asc())
    )

    if current_user.IDU == 1:
        return db.session.execute(base_q).scalars().all()

    # Non-super-admin: filter to menus with a tblPermissions row for this user
    permitted_menu_ids = (
        db.session.execute(
            select(Permission.menu_id)
            .where(Permission.user_id == current_user.IDU)
        )
        .scalars()
        .all()
    )
    if not permitted_menu_ids:
        return []

    return (
        db.session.execute(
            base_q.where(Menu.IDM.in_(permitted_menu_ids))
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ #
# Form helpers
# ------------------------------------------------------------------ #

def _parse_form(record: News) -> None:
    """
    Write all POST form fields onto a News instance.
    VB: btnAddU1_Click field mapping.
    """
    record.name = request.form.get("name", "").strip()

    # Slug: use submitted value or auto-generate from name
    raw_slug = request.form.get("slug", "").strip()
    record.slug = raw_slug if raw_slug else slugify_vi(record.name)

    record.title = (
        request.form.get("title", "").strip()
        or record.name  # VB: IIf(TitleN="", NameP, TitleN)
    )
    record.keywords = request.form.get("keywords", "").strip()
    record.description = request.form.get("description", "").strip()

    # ContentN: short description / excerpt — plain text, max 500 chars
    # VB: Left(Change2(txtContent.Text), 500)
    content = request.form.get("content", "").strip()
    record.content = content[:500]

    record.menu_id = request.form.get("menu_id", "").strip()

    try:
        record.news_type = int(request.form.get("news_type", 1))
    except (ValueError, TypeError):
        record.news_type = 1

    # DescN: full body HTML from CKEditor (type=1) or raw textarea (type=2)
    # VB: IIf(Val(rbType)=2, txtHTML.Text, Change(txtDescs.Text, txtName))
    # Change() fills empty alt="" attributes with the news name — mirror that.
    desc = request.form.get("desc", "")
    if record.news_type != 2 and desc and record.name:
        desc = desc.replace(' alt=""', f' alt="{record.name}"')
    record.desc = sanitize_html(desc)

    # ScriptCode: raw embed (Adsense, etc.) — intentionally NOT sanitized
    # VB: txtScriptCode — ValidateRequestMode="Disabled"
    record.script_code = request.form.get("script_code", "").strip()

    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1

    # tblNews has no Lang column — language is inferred from its menu.


def _sync_tbl_link(news_id: int) -> None:
    """
    Regenerate the tblLink SEO-URL row for this news item.

    VB btnAddU1_Click (exact SQL):
      DELETE tblLink WHERE RowID='<id>' AND RowType=2 AND RowLang='<lang>'
      INSERT INTO tblLink (..., RowLang)
        SELECT IDN, Name1N, 2, TypeM, Levels, IDM,
               TitleN, KeyN, DecripN, NameM, Lang
        FROM tblMenu, tblNews
        WHERE MenuIDN = IDM AND IDN = '<id>'

    RowType=2 identifies news rows (vs RowType=3 for products).
    Lang comes from tblMenu — tblNews has no Lang column.
    The caller must flush the session first so the INSERT SELECT
    reads the current tblNews values.
    """
    try:
        db.session.execute(
            text(
                'DELETE FROM "tblLink" '
                'WHERE "RowID" = :id AND "RowType" = 2 AND "RowLang" = :lang'
            ),
            {"id": str(news_id), "lang": _LANG},
        )
        db.session.execute(
            text("""
                INSERT INTO "tblLink"
                    ("RowID", "RowUrl", "RowType", "RowTypeM", "RowLevels",
                     "RowIDM", "title", "keywords", "description", "RowName", "RowLang")
                SELECT
                    n."IDN", n."Name1N", 2, m."TypeM", m."Levels",
                    m."IDM", n."TitleN", n."KeyN", n."DecripN", m."NameM", m."Lang"
                FROM "tblMenu" m, "tblNews" n
                WHERE n."MenuIDN" = m."IDM" AND n."IDN" = :id
            """),
            {"id": news_id},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink sync failed for news %s: %s", news_id, exc)


def _handle_image(record: News, is_new: bool) -> None:
    """
    Process deferred-delete flag and file upload for the news thumbnail.
    Called from after_flush() so record.ID is always resolved.
    """
    if not is_new and request.form.get("delete_img") == "1":
        delete_news_image_file(record.img)
        record.img = "null.gif"

    new_img = save_news_image(request.files.get("img_file"), record.ID)
    if new_img:
        record.img = new_img


# ------------------------------------------------------------------ #
# News controller
# ------------------------------------------------------------------ #

class NewsController(CrudController):
    """
    CRUD controller for tblNews.

    Extra behaviour vs base CrudController:
    - get_list_query:  filter by menu_id (?id=) and search (?s=)
    - render_list:     pass menus + filter state to template
    - render_form:     pass menus to template for category dropdown
    - after_flush:     tblLink sync + image handling
    - before_delete:   delete image + tblLink rows
    - get_list_redirect_url: preserve menu_id filter after batch ops
    """

    model = News
    endpoint = "news"
    list_template = "news/index.html"
    form_template = "news/form.html"

    def new_instance(self):
        return News(
            img="null.gif",
            is_active=1,
            news_type=1,
        )

    def parse_form(self, record):
        _parse_form(record)

    def validate(self, record):
        if not record.name:
            return "Tiêu đề là trường bắt buộc."
        if len(record.name) > 200:
            return "Tiêu đề không được vượt quá 200 ký tự."
        return None

    def field_errors(self, record):
        errors = {}
        if not (record.name or "").strip():
            errors["name"] = "Tiêu đề là trường bắt buộc."
        elif len(record.name) > 200:
            errors["name"] = "Không được vượt quá 200 ký tự."
        slug = (record.slug or "").strip()
        if slug and not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
            errors["slug"] = (
                "Slug chỉ được chứa chữ thường không dấu, "
                "số và dấu gạch ngang."
            )
        elif slug:
            conflict = db.session.execute(
                text(
                    'SELECT "RowID" FROM "tblLink"'
                    ' WHERE LOWER("RowUrl") = :slug AND "RowType" = 2'
                    ' AND "RowID" != :id LIMIT 1'
                ),
                {"slug": slug.lower(), "id": record.ID or 0},
            ).scalar_one_or_none()
            if conflict is not None:
                errors["slug"] = (
                    f"Slug '{slug}' đã được dùng bởi bài viết khác. "
                    "Vui lòng chọn slug khác."
                )
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            errors["img_file"] = img_err
        return errors

    def get_list_query(self):
        menu_id = request.args.get("id", "").strip()
        search_q = request.args.get("s", "").strip()

        q = select(News).order_by(News.created_at.desc())

        # VB loadNews line 194: non-super-admin only sees their own articles
        if current_user.IDU != 1:
            q = q.where(News.user_id == current_user.IDU)

        if menu_id:
            # VB hierarchical filter (admin path):
            #   strSQL = "Select Levels from tblMenu where IDM = '<id>'"
            #   iw &= " and Left(MenuIDN, Levels*2) = Left(IDM, Levels*2)"
            # A top-level menu (Levels=1, IDM='01') shows ALL sub-items
            # ('010000', '010100', etc.) not just exact MenuIDN matches.
            menu_obj = db.session.get(Menu, menu_id)
            if menu_obj and menu_obj.levels:
                prefix_len = menu_obj.levels * 2
                prefix = menu_id[:prefix_len]
                # LIKE 'prefix%' is equivalent to Left(MenuIDN, n) = prefix
                q = q.where(News.menu_id.like(f"{prefix}%"))
            else:
                q = q.where(News.menu_id == menu_id)

        if search_q:
            # VB: NameN+' '+Replace(Name1N,'-',' ') LIKE N'%s%'
            # Search in name, and also match slug with hyphens as spaces.
            pattern = f"%{search_q}%"
            slug_pattern = f"%{search_q.replace(' ', '-')}%"
            q = q.where(
                or_(
                    News.name.ilike(pattern),
                    News.slug.ilike(pattern),
                    News.slug.ilike(slug_pattern),
                )
            )

        lang_filter = request.args.get("lang", "").strip()

        return db.session.execute(q).scalars().all()

    def render_list(self, records):
        from admin.utils.permissions import load_user_permissions

        menus = _get_menus()
        current_id = request.args.get("id", "").strip()
        search_q = request.args.get("s", "").strip()
        lang_filter = request.args.get("lang", "").strip()
        langs = get_active_langs()

        # Compute permission flags for the currently-selected menu so the
        # template can show/hide buttons — mirrors VB dtgrView_ItemDataBound.
        # IDU=1: all flags True. Others: look up tblPermissions for current menu.
        if current_user.IDU == 1:
            can_add = can_edit = can_chk = can_del = True
        else:
            perm_map = load_user_permissions(current_user.IDU)
            if current_id:
                p = perm_map.get(current_id)
                can_add  = bool(p and p.can_add)
                can_edit = bool(p and p.can_edit)
                can_chk  = bool(p and p.can_chk)
                can_del  = bool(p and p.can_del)
            else:
                # No menu selected — derive flags from union of all permitted menus
                perms = list(perm_map.values())
                can_add  = any(p.can_add  for p in perms)
                can_edit = any(p.can_edit for p in perms)
                can_chk  = any(p.can_chk  for p in perms)
                can_del  = any(p.can_del  for p in perms)

        return render_template(
            self.list_template,
            news_list=records,
            menus=menus,
            current_menu_id=current_id,
            search_q=search_q,
            news_status=NEWS_STATUS,
            can_add=can_add,
            can_edit=can_edit,
            can_chk=can_chk,
            can_del=can_del,
            langs=langs,
            lang_filter=lang_filter,
        )

    def render_form(self, record, form_errors=None):
        from admin.utils.permissions import load_user_permissions
        menus = _get_menus()
        langs = get_active_langs()

        if current_user.IDU == 1:
            can_chk = True
        else:
            menu_id = (record.menu_id or "").strip()
            if menu_id:
                perm_map = load_user_permissions(current_user.IDU)
                p = perm_map.get(menu_id)
                can_chk = bool(p and p.can_chk)
            else:
                can_chk = False

        return render_template(
            self.form_template,
            news=record,
            menus=menus,
            form_errors=form_errors or {},
            news_status=NEWS_STATUS,
            news_types=NEWS_TYPES,
            can_chk=can_chk,
            langs=langs,
        )

    def check_create_permission(self, record) -> bool:
        if current_user.IDU == 1:
            return True
        menu_id = (record.menu_id or "").strip()
        if not menu_id:
            return True  # no menu yet — validated elsewhere
        return check_permission(current_user.IDU, menu_id, "add")

    def check_edit_permission(self, record) -> bool:
        if current_user.IDU == 1:
            return True
        menu_id = (record.menu_id or "").strip()
        if not menu_id:
            return True
        return check_permission(current_user.IDU, menu_id, "edit")

    def check_delete_permission(self, record) -> bool:
        if current_user.IDU == 1:
            return True
        menu_id = (record.menu_id or "").strip()
        if not menu_id:
            return True
        return check_permission(current_user.IDU, menu_id, "del")

    def batch_update_record(self, record):
        # VB btnUpdate1: ChkNews controls button visibility (server-side mirror)
        if current_user.IDU != 1:
            if not check_permission(current_user.IDU, record.menu_id or "", "chk"):
                return  # silently skip records the user cannot approve
        try:
            record.is_active = int(
                request.form.get(f"ac_{record.ID}", record.is_active)
            )
        except (ValueError, TypeError):
            pass

    def after_flush(self, record, is_new: bool):
        _sync_tbl_link(record.ID)
        _handle_image(record, is_new)

    def before_delete(self, record):
        """
        Single-row delete: delete image file + tblLink rows.
        VB dtgrView_DeleteCommand: DellImg → delete tblLink → delete tblNews.
        """
        delete_news_image_file(record.img)
        try:
            db.session.execute(
                text(
                    'DELETE FROM "tblLink" '
                    'WHERE "RowID" = :id AND "RowType" = 2 AND "RowLang" = :lang'
                ),
                {"id": str(record.ID), "lang": _LANG},
            )
        except Exception as exc:
            db.session.rollback()
            log.warning("tblLink delete failed for news %s: %s", record.ID, exc)

    def on_before_batch_delete(self, record):
        """
        Batch delete: same as single-row (image + tblLink).
        VB btnDel1_Click: same DellImg + tblLink cleanup per item.
        """
        self.before_delete(record)

    def get_list_redirect_url(self) -> str:
        """
        Redirect back to the same filtered list after batch ops.
        The hidden fields current_menu_id / current_search are submitted
        inside the batch form so the filter state survives the POST-redirect.
        """
        menu_id = request.form.get("current_menu_id", "").strip()
        search_q = request.form.get("current_search", "").strip()
        params = {}
        if menu_id:
            params["id"] = menu_id
        if search_q:
            params["s"] = search_q
        base = url_for("news.index")
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            return f"{base}?{qs}"
        return base


_ctrl = NewsController()


# ------------------------------------------------------------------ #
# Routes — thin wrappers delegating to the controller
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    return _ctrl.index()


@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    return _ctrl.create()


@bp.route("/<int:news_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(news_id: int):
    return _ctrl.edit(news_id)


@bp.route("/<int:news_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(news_id: int):
    return _ctrl.delete(news_id)


# ------------------------------------------------------------------ #
# Bump to top (eTop) — news-specific, not in base CRUD
# ------------------------------------------------------------------ #

@bp.route("/<int:news_id>/bump", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def bump(news_id: int):
    """
    Push news to top of list by setting TimeN = now().
    VB: e.CommandName = "eTop" → UPDATE tblNews SET TimeN=getdate().
    """
    record = db.session.get(News, news_id)
    if record is None:
        flash("Tin tức không tồn tại.", "danger")
        return redirect(url_for("news.index"))

    record.created_at = datetime.now(timezone.utc)
    commit_or_flash(
        f'Đã đẩy "{record.name}" lên đầu danh sách.',
        action=f"bump News {news_id}",
    )

    # Redirect back preserving filter
    menu_id = request.form.get("current_menu_id", "").strip()
    target = url_for("news.index")
    if menu_id:
        target += f"?id={menu_id}"
    return redirect(target)
