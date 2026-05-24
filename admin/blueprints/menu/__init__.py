from flask import Blueprint

bp = Blueprint(
    "menu",
    __name__,
    url_prefix="/menu",
    template_folder="templates",
)

from admin.blueprints.menu import routes  # noqa: E402, F401
