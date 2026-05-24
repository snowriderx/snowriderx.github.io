"""
Config blueprint — singleton website settings (tblTotal).

VB equivalent: website.aspx / website.aspx.vb

VB load:  SELECT * FROM tblTotal WHERE ID = {lang_cookie}   (always 1)
VB save:  o.UpdateRecord("tblTotal", f, v, True) WHERE ID = 1

Flask: always uses ID=1.  Super-admin only (IDU=1).
Script/HTML fields are admin-trusted input — intentionally NOT sanitized.
"""

import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from admin.blueprints.config import bp
from extensions import db, limiter
from models.config import SiteConfig
from admin.utils.access import super_admin_redirect
from admin.utils.db import commit_or_flash
from admin.utils.upload import get_icon_filename, save_icon_image, validate_upload_file

log = logging.getLogger(__name__)

_CONFIG_ID = 1


@bp.before_request
def _guard():
    return super_admin_redirect()


def _get_or_create() -> SiteConfig:
    cfg = db.session.get(SiteConfig, _CONFIG_ID)
    if cfg is None:
        cfg = SiteConfig(ID=_CONFIG_ID, lang=1)
        db.session.add(cfg)
        db.session.flush()
    return cfg


def _parse_form(cfg: SiteConfig) -> None:
    # Contact
    cfg.email   = request.form.get("email",   "").strip()[:100]
    cfg.hotline = request.form.get("hotline", "").strip()[:50]
    cfg.slogan  = request.form.get("slogan",  "").strip()[:200]

    # SEO
    cfg.meta_title       = request.form.get("meta_title",       "").strip()[:200]
    cfg.meta_keyword     = request.form.get("meta_keyword",     "").strip()[:300]
    cfg.meta_description = request.form.get("meta_description", "").strip()[:500]
    cfg.ads              = request.form.get("ads",              "").strip()[:1000]
    cfg.robots           = request.form.get("robots",           "").strip()[:1000]
    cfg.script_verify    = request.form.get("script_verify",    "").strip()[:2000]

    # Raw HTML/script fields — admin-only, NOT sanitized (mirrors VB ValidateRequestMode=Disabled)
    cfg.script_head  = request.form.get("script_head",  "")
    cfg.script_body  = request.form.get("script_body",  "")
    # CKEditor fields (VB: CKEditorControl) — sanitize trusted rich HTML
    cfg.content_home = request.form.get("content_home", "")
    cfg.footer       = request.form.get("footer",       "")
    cfg.script_home  = request.form.get("script_home",  "")


def _handle_icon_uploads() -> list[str]:
    """
    Save logo/favicon/share uploads.
    VB: o.UploadFile(FileLogo, "logo", "/images/icon/", 5000000, "", "", 1024)
    Returns a list of error messages (empty = all OK).
    """
    errors = []
    for name in ("logo", "favicon", "share"):
        f = request.files.get(f"file_{name}")
        err = validate_upload_file(f)
        if err:
            errors.append(f"{name}: {err}")
            continue
        save_icon_image(f, name)
    return errors


@bp.route("/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    cfg = _get_or_create()

    if request.method == "POST":
        _parse_form(cfg)
        upload_errors = _handle_icon_uploads()
        for ue in upload_errors:
            flash(ue, "warning")
        if commit_or_flash("Cấu hình website đã được lưu thành công.", action="update SiteConfig"):
            from models.config import invalidate_site_config_cache
            invalidate_site_config_cache()
        return redirect(url_for("config.index"))

    icons = {
        name: get_icon_filename(name)
        for name in ("logo", "favicon", "share")
    }
    return render_template("config/form.html", cfg=cfg, icons=icons)
