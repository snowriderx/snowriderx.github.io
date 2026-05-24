from flask import Blueprint

bp = Blueprint(
    "tab",
    __name__,
    url_prefix="/tab",
    template_folder="templates",
)

from admin.blueprints.tab import routes  # noqa: E402, F401
