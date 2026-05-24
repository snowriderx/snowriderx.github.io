from flask import Blueprint

bp = Blueprint(
    "product",
    __name__,
    url_prefix="/product",
    template_folder="templates",
)

from admin.blueprints.product import routes  # noqa: E402, F401
