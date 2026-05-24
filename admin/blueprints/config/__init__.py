from flask import Blueprint

bp = Blueprint(
    "config",
    __name__,
    url_prefix="/config",
    template_folder="templates",
)

from admin.blueprints.config import routes  # noqa
