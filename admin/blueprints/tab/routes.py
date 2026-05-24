"""
Tab blueprint — CRUD for tblTab.

VB equivalents:
  tab.aspx / tab.aspx.vb

VB list query:
  SELECT ID, Name, Ac, Sort, Type, Total, Hot FROM tblTab
  WHERE Type = '<type>' ORDER BY Sort ASC

VB insert columns:
  Type, Name, Name1 (VNtoEn slug), Sort, Ac, Total, Hot (default 0)

VB batch update columns:
  Name, Name1 (VNtoEn slug), Sort, Total, Ac, Hot — per row inline

VB delete:
  DELETE tblTab WHERE ID = <id>   (single and batch)

Type values:
  1 = Tab sản phẩm
  2 = Tab tin tức
  3 = Tab menu
"""

import logging

from flask import (
    current_app, redirect, render_template, request, flash, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from admin.blueprints.tab import bp
from extensions import db, limiter
from models.tab import Tab, TAB_TYPE_LABELS
from admin.utils.access import super_admin_redirect
from admin.utils.crud import CrudController
from admin.utils.text import slugify_vi

log = logging.getLogger(__name__)


@bp.before_request
def _guard():
    return super_admin_redirect()


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _current_type() -> int:
    """Read ?type= from GET args or _type from POST form, default 1."""
    try:
        return int(request.form.get("_type") or request.args.get("type", 1))
    except (TypeError, ValueError):
        return 1


def _parse_form(tab: Tab) -> None:
    """
    Map form fields onto a Tab instance.
    VB: btnInsert_Click / btnUpdate1_Click field mapping.
    Name1 is auto-generated via VNtoEn (slugify_vi).
    Sort defaults to "00" when blank (mirrors VB IIf(txtSort="", "00", ...)).
    """
    tab.name = request.form.get("name", "").strip() or "-"
    tab.slug = slugify_vi(tab.name)
    sort = request.form.get("sort", "").strip()
    tab.sort = sort if sort else "00"
    try:
        tab.total = int(request.form.get("total", 0) or 0)
    except ValueError:
        tab.total = 0
    try:
        tab.is_active = int(request.form.get("is_active", 1))
    except ValueError:
        tab.is_active = 1
    try:
        tab.hot = int(request.form.get("hot", 0))
    except ValueError:
        tab.hot = 0
    try:
        tab.tab_type = int(request.form.get("tab_type", 1))
    except ValueError:
        tab.tab_type = 1


# ------------------------------------------------------------------ #
# Tab controller
# ------------------------------------------------------------------ #

class TabController(CrudController):
    """
    CRUD controller for tblTab.

    Overrides:
    - get_list_query: filter by Type, ORDER BY Sort ASC
    - get_list_redirect_url: preserve ?type= filter after POST
    - batch_update_record: update Name, Name1, Sort, Total, Ac, Hot inline
    - render_list / render_form: pass tab-specific vars to templates
    """

    model = Tab
    endpoint = "tab"
    list_template = "tab/index.html"
    form_template = "tab/form.html"

    def new_instance(self):
        return Tab(
            is_active=1,
            tab_type=_current_type(),
            sort="00",
            total=0,
            hot=0,
        )

    def parse_form(self, record):
        _parse_form(record)

    def validate(self, record):
        if not record.name or record.name == "-":
            return "Tên tab là trường bắt buộc."
        if len(record.name) > 200:
            return "Tên tab không được vượt quá 200 ký tự."

    def render_list(self, records):
        current_type = _current_type()
        return render_template(
            self.list_template,
            tabs=records,
            current_type=current_type,
            tab_type_labels=TAB_TYPE_LABELS,
        )

    def render_form(self, record, form_errors=None):
        return render_template(
            self.form_template,
            tab=record,
            form_errors=form_errors or {},
            tab_type_labels=TAB_TYPE_LABELS,
        )

    def batch_update_record(self, record):
        """
        VB btnUpdate1_Click: update Name, Name1, Sort, Total, Ac, Hot per row.
        Form fields are keyed by row ID: name_<id>, sort_<id>, etc.
        """
        name = request.form.get(f"name_{record.ID}", record.name or "").strip()
        record.name = name or "-"
        record.slug = slugify_vi(record.name)
        sort = request.form.get(f"sort_{record.ID}", record.sort or "00").strip()
        record.sort = sort if sort else "00"
        try:
            record.total = int(request.form.get(f"total_{record.ID}", record.total or 0) or 0)
        except ValueError:
            pass
        try:
            record.is_active = int(request.form.get(f"ac_{record.ID}", record.is_active))
        except ValueError:
            pass
        try:
            record.hot = int(request.form.get(f"hot_{record.ID}", record.hot))
        except ValueError:
            pass

    def get_list_query(self):
        """VB: SELECT ... FROM tblTab WHERE Type=<type> ORDER BY Sort ASC"""
        tab_type = _current_type()
        return (
            db.session.execute(
                select(Tab)
                .where(Tab.tab_type == tab_type)
                .order_by(Tab.sort.asc())
            )
            .scalars()
            .all()
        )

    def get_list_redirect_url(self) -> str:
        """Preserve ?type= filter when redirecting after any POST action."""
        tab_type = (
            request.form.get("_type")
            or request.form.get("tab_type")
            or request.args.get("type", "1")
        )
        try:
            tab_type = int(tab_type)
        except (TypeError, ValueError):
            tab_type = 1
        return url_for("tab.index", type=tab_type)


_ctrl = TabController()


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


@bp.route("/<int:tab_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit(
    lambda: current_app.config["RATELIMIT_MUTATION"],
    methods=["POST"],
)
def edit(tab_id: int):
    return _ctrl.edit(tab_id)


@bp.route("/<int:tab_id>/delete", methods=["POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_MUTATION"])
def delete(tab_id: int):
    return _ctrl.delete(tab_id)
