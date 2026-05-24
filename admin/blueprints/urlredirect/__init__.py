from flask import Blueprint

bp = Blueprint("urlredirect", __name__, url_prefix="/urlredirect")
from admin.blueprints.urlredirect import routes  # noqa
