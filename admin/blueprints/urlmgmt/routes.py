"""
URL Management blueprint — read-only view of tblLink (URL routing index).

VB equivalent: url.aspx — SELECT * FROM tblLink, displayed in GridView.
No editing — this is a diagnostic/view-only page.
"""

from flask import render_template, request

from admin.blueprints.urlmgmt import bp
from extensions import db
from models.link import Link, ROW_TYPE_LABELS
from admin.utils.access import super_admin_redirect
from sqlalchemy import select


@bp.before_request
def _guard():
    return super_admin_redirect()


@bp.route("/", methods=["GET"])
def index():
    type_filter = request.args.get("row_type", "")
    search = request.args.get("q", "").strip()

    q = select(Link).order_by(Link.ID.desc())
    if type_filter.isdigit():
        q = q.where(Link.row_type == int(type_filter))
    if search:
        q = q.where(
            Link.row_url.ilike(f"%{search}%") | Link.row_name.ilike(f"%{search}%")
        )

    records = db.session.execute(q).scalars().all()

    return render_template(
        "urlmgmt/index.html",
        records=records,
        total=len(records),
        type_filter=type_filter,
        search=search,
        row_type_labels=ROW_TYPE_LABELS,
    )
