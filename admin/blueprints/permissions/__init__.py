from flask import Blueprint

bp = Blueprint("permissions", __name__, url_prefix="/permissions")

from admin.blueprints.permissions import routes  # noqa: E402, F401
