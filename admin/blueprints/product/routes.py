"""
Product blueprint — CRUD for tblPro + tblLink sync.

VB equivalents:
  pro.aspx / pro.aspx.vb

VB list query:
  SELECT IDP as ID, NameP as Name, TimeP, AcP, ImgP, MenuIDP
  FROM tblPro WHERE 1=1 ORDER BY TimeP DESC

VB insert/update columns:
  MenuIDP('070000'), NameP, Name1P, TitleP, KeyP, DecripP, ScriptP,
  HomeP, LocaleP, StyleP, SourceP, ContentP, DescP, FooterP, AcP, uID

Flask extension (not in VB):
  TabIDP — optional FK to tblTab.ID, mapped when migration has been run.
  Requires: migrations/add_tab_id_to_tblpro.sql

VB tblLink sync (on every save):
  DELETE tblLink WHERE RowID=id AND RowType=3 AND RowLang=lang
  INSERT tblLink ... SELECT IDP,LocaleP,3,TypeM,Levels,IDM,TitleP,KeyP,
    DecripP,NameM,Lang FROM tblMenu,tblPro WHERE MenuIDp=IDM AND IDP=id

VB image upload:
  ImgP  → "sm-<id>.<ext>", /images/pro, max 600px
  Img1P → "lg_<id>.<ext>", /images/pro, max 1920px

VB eTop command:
  UPDATE tblPro SET TimeP=getdate() WHERE IDP=id

VB delete:
  DellImg (read ImgP/Img1P, delete files)
  DELETE tblLink WHERE RowID=id AND RowType=3
  DELETE tblPro WHERE IDP=id
  (single-row delete also deletes tblAdvert WHERE MenuID=id)
"""

import logging
import os
import re
from datetime import datetime, timezone

from flask import (
    current_app, redirect, render_template, request, flash, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select, text

from admin.blueprints.product import bp
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.lang import Lang, get_active_langs


@bp.before_request
def _guard():
    return super_admin_redirect()
from models.product import Product, tab_column_ready
from models.tab import Tab, TAB_TYPE_PRODUCT
from admin.utils.crud import CrudController
from admin.utils.html import sanitize_html
from admin.utils.text import slugify_vi
from admin.utils.upload import (
    delete_pro_image_file,
    save_pro_image,
    validate_upload_file,
)

log = logging.getLogger(__name__)

_THUMB_MAX_WIDTH = 600
_GAME_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "theme", "static", "game")
)
_LARGE_MAX_WIDTH = 1920
_DEFAULT_MENU_ID = "070000"


# ------------------------------------------------------------------ #
# Tab helpers
# ------------------------------------------------------------------ #

def _load_product_tabs() -> list:
    """
    Load active product tabs (Type=1) ordered by Sort.
    Returns empty list if tblTab is unavailable.
    """
    try:
        return (
            db.session.execute(
                select(Tab)
                .where(Tab.tab_type == TAB_TYPE_PRODUCT)
                .where(Tab.is_active == 1)
                .order_by(Tab.sort.asc())
            )
            .scalars()
            .all()
        )
    except Exception:
        return []


def _current_tab_id() -> "int | None":
    """
    Read the active tab filter from GET ?tab= or POST _tab_id.
    Returns None when no filter is active (show all products).
    """
    raw = request.form.get("_tab_id") or request.args.get("tab")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ #
# Form helpers
# ------------------------------------------------------------------ #

def _parse_form(product: Product) -> None:
    """
    Write all form fields onto a Product instance.
    VB: btnAddU1_Click field mapping.
    """
    product.name = request.form.get("name", "").strip()
    raw_slug = request.form.get("slug", "").strip()
    product.slug = raw_slug if raw_slug else slugify_vi(product.name)
    product.title = (
        request.form.get("title", "").strip()
        or product.name
    )
    product.keywords = request.form.get("keywords", "").strip()
    product.description = request.form.get("description", "").strip()
    product.script = request.form.get("script", "").strip()
    product.is_home = 1 if request.form.get("is_home") else 0
    raw_locale = request.form.get("locale", "").strip()
    product.locale = raw_locale if raw_locale else product.slug
    product.style = request.form.get("style", "").strip()
    product.source = sanitize_html(request.form.get("source", ""))
    product.content = sanitize_html(request.form.get("content", ""))
    product.is_active = 1 if request.form.get("is_active") else 0
    product.menu_id = _DEFAULT_MENU_ID

    desc = request.form.get("desc", "")
    if desc:
        desc = desc.replace("<h1", "<h2").replace("</h1>", "</h2>")
        desc = desc.replace(' alt=""', f' alt="{product.name}"')
    product.desc = sanitize_html(desc)

    product.footer = sanitize_html(request.form.get("footer", ""))

    raw_lang = request.form.get("lang_id", "").strip()
    product.lang = raw_lang if raw_lang else "1"

    # Tab assignment — only when column exists in DB
    if tab_column_ready():
        raw = request.form.get("tab_id", "")
        try:
            product.tab_id = int(raw) if raw else None
        except (ValueError, TypeError):
            product.tab_id = None


def _sync_tbl_link(product_id: int, lang: int = 1) -> None:
    """
    Regenerate the tblLink SEO-URL row for this product + language.

    VB btnAddU1_Click (exact SQL):
      DELETE tblLink WHERE RowID='<id>' AND RowType=3 AND RowLang='<lang>'
      INSERT tblLink (..., RowLang)
        SELECT IDP, LocaleP, 3, TypeM, Levels, IDM,
               TitleP, KeyP, DecripP, NameM, Lang
        FROM tblMenu, tblPro
        WHERE MenuIDp = IDM AND IDP = '<id>'
    """
    from sqlalchemy import text
    try:
        db.session.execute(
            text(
                'DELETE FROM "tblLink" '
                'WHERE "RowID" = :id AND "RowType" = 3 AND "RowLang" = :lang'
            ),
            {"id": str(product_id), "lang": lang},
        )
        db.session.execute(
            text("""
                INSERT INTO "tblLink"
                    ("RowID", "RowUrl", "RowType", "RowTypeM", "RowLevels",
                     "RowIDM", "title", "keywords", "description", "RowName", "RowLang")
                SELECT
                    p."IDP", p."LocaleP", 3, m."TypeM", m."Levels",
                    m."IDM", p."TitleP", p."KeyP", p."DecripP", m."NameM",
                    CAST(p."LangP" AS INTEGER)
                FROM "tblMenu" m, "tblPro" p
                WHERE p."MenuIDP" = m."IDM" AND p."IDP" = :id
            """),
            {"id": product_id},
        )
    except Exception as exc:
        db.session.rollback()
        log.warning("tblLink sync failed for product %s: %s", product_id, exc)


def _delete_product_images(product: Product) -> None:
    delete_pro_image_file(product.img)
    delete_pro_image_file(product.img1)


def _handle_images(record: Product, is_new: bool) -> None:
    if not is_new:
        if request.form.get("delete_img") == "1":
            delete_pro_image_file(record.img)
            record.img = "null.gif"
        if request.form.get("delete_img1") == "1":
            delete_pro_image_file(record.img1)
            record.img1 = "null.gif"

    thumb = save_pro_image(
        request.files.get("img_file"),
        record.ID, "sm-", _THUMB_MAX_WIDTH,
    )
    if thumb:
        record.img = thumb

    large = save_pro_image(
        request.files.get("img1_file"),
        record.ID, "lg_", _LARGE_MAX_WIDTH,
    )
    if large:
        record.img1 = large


# ------------------------------------------------------------------ #
# Product controller
# ------------------------------------------------------------------ #

class ProductController(CrudController):
    """
    CRUD controller for tblPro.

    Tab integration:
    - get_list_query: filters by ?tab=<id> when TabIDP column is ready
    - get_list_redirect_url: preserves ?tab= filter after every POST
    - render_list: passes tabs list + current_tab_id to template
    - render_form: passes tabs list + tab_column_ready flag to template
    """

    model = Product
    endpoint = "product"
    list_template = "product/index.html"
    form_template = "product/form.html"

    def new_instance(self):
        return Product(
            img="null.gif",
            img1="null.gif",
            is_active=1,
            menu_id=_DEFAULT_MENU_ID,
            lang="1",
        )

    def parse_form(self, record):
        _parse_form(record)

    def validate(self, record):
        if not record.name:
            return "Tên sản phẩm là trường bắt buộc."
        if len(record.name) > 150:
            return "Tên sản phẩm không được vượt quá 150 ký tự."

    def field_errors(self, record):
        errors = {}
        if not (record.name or "").strip():
            errors["name"] = "Tên sản phẩm là trường bắt buộc."
        elif len(record.name) > 150:
            errors["name"] = "Không được vượt quá 150 ký tự."
        slug = (record.slug or "").strip()
        if slug and not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
            errors["slug"] = (
                "Slug chỉ được chứa chữ thường không dấu, "
                "số và dấu gạch ngang."
            )
        elif slug:
            # Check via LocaleP (the field written to tblLink.RowUrl for products)
            locale = (record.locale or "").strip().lower() or slug.lower()
            conflict = db.session.execute(
                text(
                    'SELECT "RowID" FROM "tblLink"'
                    ' WHERE LOWER("RowUrl") = :slug AND "RowType" = 3'
                    ' AND "RowID" != :id LIMIT 1'
                ),
                {"slug": locale, "id": record.ID or 0},
            ).scalar_one_or_none()
            if conflict is not None:
                errors["slug"] = (
                    f"Slug '{slug}' đã được dùng bởi sản phẩm khác. "
                    "Vui lòng chọn slug khác."
                )
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            errors["img_file"] = img_err
        img1_err = validate_upload_file(request.files.get("img1_file"))
        if img1_err:
            errors["img1_file"] = img1_err
        return errors

    def render_list(self, records):
        tabs = _load_product_tabs()
        current_tab_id = _current_tab_id()
        lang_filter = request.args.get("lang", "").strip()
        langs = get_active_langs()
        return render_template(
            self.list_template,
            products=records,
            tabs=tabs,
            current_tab_id=current_tab_id,
            tab_ready=tab_column_ready(),
            langs=langs,
            lang_filter=lang_filter,
        )

    def render_form(self, record, form_errors=None):
        tabs = _load_product_tabs()
        langs = get_active_langs()
        locale = (record.locale or record.slug or "").strip()
        locale_warning = ""
        if locale and not os.path.isdir(os.path.join(_GAME_DIR, locale)):
            existing = sorted(
                d for d in os.listdir(_GAME_DIR)
                if os.path.isdir(os.path.join(_GAME_DIR, d))
            )
            locale_warning = (
                f"Chưa có folder game '{locale}' tại theme/static/game/. "
                f"Các folder hiện có: {', '.join(existing)}."
            )
        return render_template(
            self.form_template,
            product=record,
            form_errors=form_errors or {},
            tabs=tabs,
            tab_ready=tab_column_ready(),
            langs=langs,
            locale_warning=locale_warning,
        )

    def batch_update_record(self, record):
        try:
            record.is_active = int(
                request.form.get(f"ac_{record.ID}", record.is_active)
            )
        except ValueError:
            pass

    def after_flush(self, record, is_new: bool):
        _sync_tbl_link(record.ID, lang=record.lang)
        _handle_images(record, is_new)

    def before_delete(self, record):
        from sqlalchemy import text
        _delete_product_images(record)
        for tbl, where in (
            ('"tblLink"',   '"RowID" = :id AND "RowType" = 3'),
            ('"tblAdvert"', '"MenuID" = :id'),
        ):
            try:
                db.session.execute(
                    text(f"DELETE FROM {tbl} WHERE {where}"),
                    {"id": str(record.ID)},
                )
            except Exception as exc:
                db.session.rollback()
                log.warning("cascade delete failed for product %s %s: %s", tbl, record.ID, exc)

    def on_before_batch_delete(self, record):
        from sqlalchemy import text
        _delete_product_images(record)
        try:
            db.session.execute(
                text('DELETE FROM "tblLink" WHERE "RowID" = :id AND "RowType" = 3'),
                {"id": str(record.ID)},
            )
        except Exception as exc:
            db.session.rollback()
            log.warning("tblLink batch delete failed for product %s: %s", record.ID, exc)

    def get_list_query(self):
        """
        VB: SELECT ... FROM tblPro ORDER BY TimeP DESC
        Flask extension: if ?tab= and TabIDP mapped, filter by tab_id.
        """
        stmt = select(Product).order_by(Product.created_at.desc())

        if tab_column_ready():
            tab_id = _current_tab_id()
            if tab_id is not None:
                stmt = stmt.where(Product.tab_id == tab_id)

        # Language filter — LangP is TEXT in DB, compare as string
        lang_filter = request.args.get("lang", "").strip()
        if lang_filter:
            stmt = stmt.where(Product.lang == lang_filter)

        return db.session.execute(stmt).scalars().all()

    def get_list_redirect_url(self) -> str:
        """Preserve ?tab= filter after any POST (batch update, batch delete)."""
        raw = (
            request.form.get("_tab_id")
            or request.args.get("tab")
        )
        if raw:
            try:
                return url_for("product.index", tab=int(raw))
            except (TypeError, ValueError):
                pass
        return url_for("product.index")


_ctrl = ProductController()


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
    return _ctrl.index()


@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    return _ctrl.create()


@bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(product_id: int):
    return _ctrl.edit(product_id)


@bp.route("/<int:product_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(product_id: int):
    return _ctrl.delete(product_id)


@bp.route("/<int:product_id>/bump", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def bump(product_id: int):
    """
    Push product to top of list by setting TimeP = now().
    VB: e.CommandName = "eTop" → UPDATE tblPro SET TimeP=getdate().
    """
    product = db.session.get(Product, product_id)
    if product is None:
        flash("Sản phẩm không tồn tại.", "danger")
        return redirect(url_for("product.index"))

    product.created_at = datetime.now(timezone.utc)
    commit_or_flash(f'Đã đẩy "{product.name}" lên đầu danh sách.', action=f"bump Product {product_id}")

    # Preserve tab filter when redirecting after bump
    tab_id = _current_tab_id()
    if tab_id is not None:
        return redirect(url_for("product.index", tab=tab_id))
    return redirect(url_for("product.index"))
