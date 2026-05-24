from flask import Blueprint

bp = Blueprint("layout", __name__, url_prefix="/layout")

from admin.blueprints.layout import routes  # noqa: E402, F401
