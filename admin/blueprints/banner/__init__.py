from flask import Blueprint

bp = Blueprint(
    "banner",
    __name__,
    url_prefix="/banner",
    template_folder="templates",
)

from admin.blueprints.banner import routes  # noqa: E402, F401
