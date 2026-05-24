"""
Template blueprint — CRUD for tblIntro (template/content blocks).

VB equivalents:
  template.aspx / template.aspx.vb

VB list query:
  SELECT ID, Name, Ac, Img, Sort FROM tblIntro WHERE Ac <> 99 ORDER BY Sort ASC

VB insert/update columns:
  Name, Descs (h1→h2 replacement), Type (always 80), Ac, Sort, Img

VB soft delete:
  UPDATE tblIntro SET Ac=99 WHERE ID=<id>
  (never hard-deleted)

VB image upload:
  /images/teamplate/ directory (typo in original), max 100px wide
  Flask: /static/uploads/intro/  stem: intro_<ID>.<ext>

Access: super-admin only (IDU=1).
"""

import logging
import re

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from admin.blueprints.template import bp
from admin.utils.db import commit_or_flash
from extensions import db, limiter
from models.intro import Intro, INTRO_STATUS
from admin.utils.access import super_admin_redirect
from admin.utils.crud import CrudController
from admin.utils.html import sanitize_html
from admin.utils.upload import (
    delete_intro_image_file,
    save_intro_image,
    validate_upload_file,
)

log = logging.getLogger(__name__)


@bp.before_request
def _guard():
    return super_admin_redirect()


# ------------------------------------------------------------------ #
# Form helpers
# ------------------------------------------------------------------ #

def _parse_form(record: Intro) -> None:
    record.name = request.form.get("name", "").strip() or "-"

    # VB: Replace(txtDescs.Text, "<h1", "<h2") / Replace(..., "</h1>", "</h2>")
    descs_raw = request.form.get("descs", "")
    descs_raw = re.sub(r"<h1([^>]*)>", r"<h2\1>", descs_raw)
    descs_raw = descs_raw.replace("</h1>", "</h2>")
    record.descs = sanitize_html(descs_raw)

    record.sort = request.form.get("sort", "50").strip() or "50"

    try:
        record.is_active = int(request.form.get("is_active", 1))
    except (ValueError, TypeError):
        record.is_active = 1

    record.intro_type = 80  # always 80 — not exposed in UI


def _handle_image(record: Intro, is_new: bool) -> None:
    if not is_new and request.form.get("delete_img") == "1":
        delete_intro_image_file(record.img)
        record.img = "null.gif"

    new_img = save_intro_image(request.files.get("img_file"), record.ID)
    if new_img:
        record.img = new_img


# ------------------------------------------------------------------ #
# Template controller
# ------------------------------------------------------------------ #

class TemplateController(CrudController):
    model = Intro
    endpoint = "template"
    list_template = "template/index.html"
    form_template = "template/form.html"

    def new_instance(self):
        return Intro(img="null.gif", is_active=1, intro_type=80, sort="50")

    def parse_form(self, record):
        _parse_form(record)

    def validate(self, record):
        return None  # VB allows empty name (defaults to "-")

    def field_errors(self, record):
        errors = {}
        img_err = validate_upload_file(request.files.get("img_file"))
        if img_err:
            errors["img_file"] = img_err
        return errors

    def get_list_query(self):
        # VB: WHERE Ac <> 99 ORDER BY Sort ASC
        q = (
            select(Intro)
            .where(Intro.is_active != 99)
            .order_by(Intro.sort.asc())
        )
        return db.session.execute(q).scalars().all()

    def render_list(self, records):
        return render_template(
            self.list_template,
            intros=records,
            intro_status=INTRO_STATUS,
        )

    def render_form(self, record, form_errors=None):
        return render_template(
            self.form_template,
            intro=record,
            form_errors=form_errors or {},
            intro_status=INTRO_STATUS,
        )

    def batch_update_record(self, record):
        # VB btnUpdate1: inline Sort + Ac only
        record.sort = (
            request.form.get(f"sort_{record.ID}", record.sort or "50").strip() or "50"
        )
        try:
            record.is_active = int(
                request.form.get(f"ac_{record.ID}", record.is_active)
            )
        except (ValueError, TypeError):
            pass

    def after_flush(self, record, is_new: bool):
        _handle_image(record, is_new)

    def delete(self, record_id: int):
        """
        Soft delete: SET Ac=99 instead of removing the row.
        VB: UPDATE tblIntro SET Ac=99 WHERE ID=<id>
        """
        record = db.session.get(self.model, record_id)
        if record is None:
            flash("Không tìm thấy bản ghi.", "danger")
            return redirect(self.get_list_redirect_url())

        record.is_active = 99
        commit_or_flash(f'Đã xóa "{record.name}".', action=f"soft_delete Intro {record_id}")
        return redirect(self.get_list_redirect_url())

    def get_list_redirect_url(self) -> str:
        return url_for("template.index")


_ctrl = TemplateController()


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@bp.route("/", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def index():
    return _ctrl.index()


@bp.route("/new", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def create():
    return _ctrl.create()


@bp.route("/<int:intro_id>/edit", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(intro_id: int):
    return _ctrl.edit(intro_id)


@bp.route("/<int:intro_id>/delete", methods=["POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(intro_id: int):
    return _ctrl.delete(intro_id)
