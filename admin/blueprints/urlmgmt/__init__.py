from flask import Blueprint

bp = Blueprint("urlmgmt", __name__, url_prefix="/urlmgmt")
from admin.blueprints.urlmgmt import routes  # noqa
