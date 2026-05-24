from flask import Blueprint

bp = Blueprint(
    "advertc",
    __name__,
    url_prefix="/advertc",
    template_folder="templates",
)

from admin.blueprints.advertc import routes  # noqa: E402, F401
