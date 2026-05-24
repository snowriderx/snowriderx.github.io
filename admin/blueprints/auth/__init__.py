from flask import Blueprint

bp = Blueprint("auth", __name__, url_prefix="", template_folder="templates")

from admin.blueprints.auth import routes  # noqa: E402, F401
