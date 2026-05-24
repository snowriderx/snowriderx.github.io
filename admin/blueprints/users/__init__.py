from flask import Blueprint

bp = Blueprint("users", __name__, url_prefix="/users")

from admin.blueprints.users import routes  # noqa: E402, F401
