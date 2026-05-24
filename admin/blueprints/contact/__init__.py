from flask import Blueprint

bp = Blueprint("contact", __name__, url_prefix="/contact")
from admin.blueprints.contact import routes  # noqa
