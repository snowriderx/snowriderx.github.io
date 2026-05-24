"""
Generic CRUD controller base for admin blueprints.

Subclasses declare what they own (model, templates, endpoint) and
implement the domain-specific hooks (parse_form, validate, after_flush,
before_delete).  The base class owns the route lifecycle so each new
module only writes what differs.

Minimal subclass example:

    class NewsController(CrudController):
        model         = News
        endpoint      = "news"
        list_template = "news/index.html"
        form_template = "news/form.html"

        def new_instance(self):
            return News(is_active=1, lang=1)

        def parse_form(self, record):
            record.title = request.form.get("title", "").strip()
            ...

        def validate(self, record):
            if not record.title:
                return "Tiêu đề là trường bắt buộc."

        def render_list(self, records):
            return render_template(self.list_template, news_list=records)

        def render_form(self, record):
            return render_template(self.form_template, news=record)

        def batch_update_record(self, record):
            try:
                record.is_active = int(
                    request.form.get(f"ac_{record.ID}", record.is_active)
                )
            except ValueError:
                pass

    _ctrl = NewsController()

    @bp.route("/", methods=["GET", "POST"])
    @login_required
    def index(): return _ctrl.index()

    @bp.route("/new", methods=["GET", "POST"])
    @login_required
    def create(): return _ctrl.create()

    @bp.route("/<int:news_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit(news_id): return _ctrl.edit(news_id)

    @bp.route("/<int:news_id>/delete", methods=["POST"])
    @login_required
    def delete(news_id): return _ctrl.delete(news_id)
"""

import logging
from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from extensions import db
from admin.utils.db import commit_or_flash

log = logging.getLogger(__name__)


class CrudController:
    """
    Base controller for standard admin CRUD blueprints.

    Route entry points (index, create, edit, delete) are called from
    thin blueprint route functions — the controller never registers
    routes itself, so Flask's endpoint/url_for machinery is unaffected.

    Create/edit lifecycle:
        parse_form() → validate() → _set_audit_fields() [create only]
        → flush → after_flush() → commit

    Subclasses MUST implement:
        model, endpoint, list_template, form_template,
        new_instance(), parse_form(), batch_update_record(),
        render_list(), render_form()

    Subclasses MAY override:
        validate(), after_flush(), before_delete(),
        on_before_batch_delete(), get_list_query(),
        get_list_redirect_url()
    """

    # ── Class-level configuration (set in subclass) ───────────────── #

    model = None           # SQLAlchemy model class
    endpoint = None        # Blueprint name, e.g. "product"
    list_template = None   # e.g. "product/index.html"
    form_template = None   # e.g. "product/form.html"

    # ── Hooks — implement / override in subclass ──────────────────── #

    def new_instance(self):
        """Return a bare model instance with sane defaults for create."""
        raise NotImplementedError

    def parse_form(self, record) -> None:
        """Map request.form fields onto record. Called for create and edit."""
        raise NotImplementedError

    def validate(self, record) -> "str | None":
        """
        Return a general error message if validation fails, None if valid.
        Flashed as a banner at the top of the form.
        """
        return None

    def field_errors(self, record) -> dict:
        """
        Return per-field errors as {field_name: message}.
        Called on every POST before validate(); returning a non-empty dict
        re-renders the form with inline highlights.  Default: no errors.
        """
        return {}

    def batch_update_record(self, record) -> None:
        """Update batch-editable fields on one record during bulk update."""
        raise NotImplementedError

    def render_list(self, records):
        """
        Render the list template.
        Override to pass module-specific template variables.
        """
        return render_template(self.list_template, records=records)

    def render_form(self, record, form_errors=None):
        """
        Render the form template.
        Override to pass module-specific template variables.
        form_errors is a dict {field_name: message} for inline highlights.
        """
        return render_template(
            self.form_template, record=record,
            form_errors=form_errors or {},
        )

    def after_flush(self, record, is_new: bool) -> None:
        """
        Called after db.session.flush() (PK resolved) but before commit.
        Use for: image uploads, SEO-link table sync, etc.
        Default: no-op.
        """

    def before_delete(self, record) -> None:
        """
        Called before db.session.delete(record).
        Use for: file deletion, cascade-delete related rows, etc.
        Default: no-op.
        """

    def on_before_batch_delete(self, record) -> None:
        """
        Called per-record in _batch_delete().
        Defaults to before_delete() — override when batch cleanup differs
        from single-row cleanup (e.g. fewer related-table deletes).
        """
        self.before_delete(record)

    def can_batch_delete_record(self, record) -> bool:
        """
        Return False to skip a record during batch delete.
        Delegates to check_delete_permission() by default so subclasses
        only need to override one method.
        """
        return self.check_delete_permission(record)

    def get_list_query(self):
        """Return the list of records for the index view."""
        return db.session.execute(select(self.model)).scalars().all()

    def get_list_redirect_url(self) -> str:
        """URL to redirect to after a successful create / edit / delete."""
        return url_for(f"{self.endpoint}.index")

    def check_create_permission(self, record) -> bool:
        """
        Return False to abort create with 403.
        Called after parse_form() so record fields are populated.
        Default: allow all authenticated users.
        Override in subclass for permission enforcement.
        """
        return True

    def check_edit_permission(self, record) -> bool:
        """
        Return False to abort edit with 403.
        Called after parse_form() on POST, or before render on GET.
        Default: allow all authenticated users.
        """
        return True

    def check_delete_permission(self, record) -> bool:
        """
        Return False to abort delete with 403.
        Called before_delete().
        Default: allow all authenticated users.
        """
        return True

    # ── Route entry points ────────────────────────────────────────── #

    def index(self):
        """
        GET  → render list
        POST → dispatch batch update or batch delete, then redirect
        """
        if request.method == "POST":
            if request.form.get("_action") == "delete":
                self._batch_delete(request.form.getlist("item_id"))
            else:
                self._batch_update(request.form.getlist("row_id"))
            return redirect(self.get_list_redirect_url())
        return self.render_list(self.get_list_query())

    def create(self):
        """
        GET  → render empty form
        POST → validate, persist, redirect
        """
        if request.method == "POST":
            record = self.new_instance()
            self.parse_form(record)

            if not self.check_create_permission(record):
                from flask import abort
                abort(403)

            form_errors = self.field_errors(record)
            err = self.validate(record)
            if err:
                flash(err, "danger")
                return self.render_form(record, form_errors=form_errors)
            if form_errors:
                return self.render_form(record, form_errors=form_errors)

            self._set_audit_fields(record, is_new=True)
            db.session.add(record)
            db.session.flush()
            self.after_flush(record, is_new=True)
            if commit_or_flash(
                "Thêm mới thành công!",
                action=f"create {self.model.__name__}",
            ):
                return redirect(self.get_list_redirect_url())
            return self.render_form(record)

        return self.render_form(self.new_instance())

    def edit(self, record_id: int):
        """
        GET  → render form pre-filled with existing data
        POST → validate, persist changes, redirect
        """
        record = db.session.get(self.model, record_id)
        if record is None:
            flash("Không tìm thấy bản ghi.", "danger")
            return redirect(self.get_list_redirect_url())

        if request.method == "POST":
            self.parse_form(record)

            if not self.check_edit_permission(record):
                from flask import abort
                abort(403)

            form_errors = self.field_errors(record)
            err = self.validate(record)
            if err:
                flash(err, "danger")
                return self.render_form(record, form_errors=form_errors)
            if form_errors:
                return self.render_form(record, form_errors=form_errors)

            db.session.flush()
            self.after_flush(record, is_new=False)
            if commit_or_flash(
                "Cập nhật thành công!",
                action=f"update {self.model.__name__} {record.ID}",
            ):
                return redirect(self.get_list_redirect_url())
            return self.render_form(record)

        return self.render_form(record)

    def delete(self, record_id: int):
        """POST → cleanup, delete, redirect."""
        record = db.session.get(self.model, record_id)
        if record is None:
            flash("Không tìm thấy bản ghi.", "danger")
            return redirect(self.get_list_redirect_url())

        if not self.check_delete_permission(record):
            from flask import abort
            abort(403)

        self.before_delete(record)
        db.session.delete(record)
        commit_or_flash(
            "Xóa thành công!",
            action=f"delete {self.model.__name__} {record_id}",
        )
        return redirect(self.get_list_redirect_url())

    # ── Batch helpers ─────────────────────────────────────────────── #

    def _batch_update(self, row_ids: list) -> None:
        valid_ids = []
        for raw_id in row_ids:
            try:
                rid = int(raw_id)
            except ValueError:
                continue
            record = db.session.get(self.model, rid)
            if record is None:
                continue
            self.batch_update_record(record)
            valid_ids.append(rid)
        commit_or_flash(
            "Cập nhật thành công!",
            action=f"batch_update {self.model.__name__} ids={valid_ids}",
        )

    def _batch_delete(self, item_ids: list) -> None:
        if not item_ids:
            flash("Chọn ít nhất một mục để xóa.", "warning")
            return
        deleted_ids = []
        for raw_id in item_ids:
            try:
                rid = int(raw_id)
            except ValueError:
                continue
            record = db.session.get(self.model, rid)
            if record is None:
                continue
            if not self.can_batch_delete_record(record):
                continue
            self.on_before_batch_delete(record)
            db.session.delete(record)
            deleted_ids.append(rid)
        commit_or_flash(
            "Xóa thành công!",
            action=f"batch_delete {self.model.__name__} ids={deleted_ids}",
        )

    # ── Private ───────────────────────────────────────────────────── #

    @staticmethod
    def _set_audit_fields(record, is_new: bool) -> None:
        """Stamp created_at / user_id on models that carry those columns."""
        if is_new:
            if hasattr(record, "created_at"):
                record.created_at = datetime.now(timezone.utc)
            if hasattr(record, "user_id"):
                record.user_id = current_user.IDU
