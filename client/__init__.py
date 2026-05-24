import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template

from config import ClientConfig
from extensions import db


def create_client_app() -> Flask:
    app = Flask(
        __name__,
        static_url_path="/static",
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "theme", "static"),
        template_folder="templates",
    )
    app.config.from_object(ClientConfig)
    db.init_app(app)

    # Import models so SQLAlchemy mapper registers all tables
    from models.menu import Menu, init_optional_menu_columns  # noqa: F401
    from models.news import News  # noqa: F401
    from models.product import Product, init_optional_product_columns  # noqa: F401
    from models.config import SiteConfig  # noqa: F401
    from models.banner import Advert  # noqa: F401
    from models.link import Link  # noqa: F401
    from models.contact import Contact  # noqa: F401
    from models.url_redirect import UrlRedirect  # noqa: F401

    with app.app_context():
        try:
            init_optional_menu_columns(db.engine)
        except Exception as e:
            app.logger.warning("Optional menu columns: %s", e)
        try:
            init_optional_product_columns(db.engine)
        except Exception as e:
            app.logger.warning("Optional product columns: %s", e)

    from client.routes import bp as client_bp
    app.register_blueprint(client_bp)

    from client.context_processors import register_context_processors, init_game_folder_cache
    init_game_folder_cache()
    register_context_processors(app)

    from client.helpers import get_ads_for_template
    app.jinja_env.globals["get_ads"] = get_ads_for_template

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("500: %s", e, exc_info=True)
        return render_template("500.html"), 500

    return app
