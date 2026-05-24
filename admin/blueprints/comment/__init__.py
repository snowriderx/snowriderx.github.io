from flask import Blueprint

bp = Blueprint("comment", __name__, url_prefix="/comment")
from admin.blueprints.comment import routes  # noqa
