from flask import Blueprint

bp = Blueprint(
    "news",
    __name__,
    url_prefix="/news",
    template_folder="templates",
)

from admin.blueprints.news import routes  # noqa: E402, F401
