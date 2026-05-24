from flask import Blueprint

bp = Blueprint("template", __name__, url_prefix="/template")

from admin.blueprints.template import routes  # noqa: E402, F401
