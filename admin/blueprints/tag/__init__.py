from flask import Blueprint

bp = Blueprint("tag", __name__, url_prefix="/tag")

from admin.blueprints.tag import routes  # noqa: E402, F401
