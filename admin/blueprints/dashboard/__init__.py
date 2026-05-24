from flask import Blueprint

bp = Blueprint("dashboard", __name__, url_prefix="", template_folder="templates")

from admin.blueprints.dashboard import routes  # noqa: E402, F401
