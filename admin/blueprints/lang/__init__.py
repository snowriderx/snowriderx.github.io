from flask import Blueprint

lang_bp = Blueprint("lang", __name__, url_prefix="/lang")

from admin.blueprints.lang import routes  # noqa: E402, F401
