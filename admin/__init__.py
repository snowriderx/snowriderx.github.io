import logging
import os
import sys
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, url_for
from flask_wtf.csrf import CSRFProtect

from config import AdminConfig
from extensions import db, login_manager, limiter

csrf = CSRFProtect()


def create_admin_app() -> Flask:
    app = Flask(
        __name__,
        static_url_path="/admin/static",
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(AdminConfig)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Import models so SQLAlchemy registers them with this app's metadata
    from models.user import User  # noqa: F401
    from models.banner import Advert  # noqa: F401
    from models.product import Product  # noqa: F401
    from models.menu import Menu, init_optional_menu_columns  # noqa: F401
    from models.product import init_optional_product_columns  # noqa: F401
    from models.news import News  # noqa: F401
    from models.permission import Permission  # noqa: F401
    from models.config import SiteConfig  # noqa: F401
    from models.tab import Tab  # noqa: F401
    from models.intro import Intro  # noqa: F401
    from models.tag import Tag  # noqa: F401
    from models.lang import LangMenu, init_optional_langmenu_columns  # noqa: F401
    from models.url_redirect import UrlRedirect  # noqa: F401
    from models.link import Link  # noqa: F401
    from models.contact import Contact  # noqa: F401
    from models.comment import Comment  # noqa: F401

    with app.app_context():
        try:
            init_optional_menu_columns(db.engine)
        except Exception as _e:
            app.logger.warning("Could not map optional Menu columns: %s", _e)
        try:
            init_optional_product_columns(db.engine)
        except Exception as _e:
            app.logger.warning("Could not map optional Product columns: %s", _e)
        try:
            init_optional_langmenu_columns(db.engine)
        except Exception as _e:
            app.logger.warning("Could not map optional LangMenu columns: %s", _e)

    from admin.blueprints.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from admin.blueprints.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from admin.blueprints.banner import bp as banner_bp
    app.register_blueprint(banner_bp)

    from admin.blueprints.product import bp as product_bp
    app.register_blueprint(product_bp)

    from admin.blueprints.news import bp as news_bp
    app.register_blueprint(news_bp)

    from admin.blueprints.menu import bp as menu_bp
    app.register_blueprint(menu_bp)

    from admin.blueprints.advertc import bp as advertc_bp
    app.register_blueprint(advertc_bp)

    from admin.blueprints.users import bp as users_bp
    app.register_blueprint(users_bp)

    from admin.blueprints.permissions import bp as permissions_bp
    app.register_blueprint(permissions_bp)

    from admin.blueprints.config import bp as config_bp
    app.register_blueprint(config_bp)

    from admin.blueprints.tab import bp as tab_bp
    app.register_blueprint(tab_bp)

    from admin.blueprints.template import bp as template_bp
    app.register_blueprint(template_bp)

    from admin.blueprints.layout import bp as layout_bp
    app.register_blueprint(layout_bp)

    from admin.blueprints.tag import bp as tag_bp
    app.register_blueprint(tag_bp)

    from admin.blueprints.lang import lang_bp
    app.register_blueprint(lang_bp)

    from admin.blueprints.urlredirect import bp as urlredirect_bp
    app.register_blueprint(urlredirect_bp)

    from admin.blueprints.urlmgmt import bp as urlmgmt_bp
    app.register_blueprint(urlmgmt_bp)

    from admin.blueprints.contact import bp as contact_bp
    app.register_blueprint(contact_bp)

    from admin.blueprints.comment import bp as comment_bp
    app.register_blueprint(comment_bp)

    from admin.blueprints.api import bp as api_bp
    app.register_blueprint(api_bp)
    csrf.exempt(api_bp)

    from admin.utils.middleware import register_middleware
    register_middleware(app)

    @app.context_processor
    def inject_globals():
        from models.config import get_site_config
        site_cfg = get_site_config()
        site_name = (
            (site_cfg.slogan if site_cfg and site_cfg.slogan else None)
            or app.config.get("SITE_NAME")
            or "Admin"
        )

        def img_url(subfolder: str, filename: str) -> str:
            if not filename or filename == "null.gif":
                return url_for("static", filename="img/no-image.gif")
            base = app.config.get("IMAGE_BASE_URL", "").rstrip("/")
            if base:
                return f"{base}/{subfolder}/{filename}"
            return url_for("static", filename=f"uploads/{subfolder}/{filename}")

        return {
            "site_name": site_name,
            "site_config": site_cfg,
            "img_url": img_url,
            "IMAGE_BASE_URL": app.config.get("IMAGE_BASE_URL", ""),
        }

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        return response

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html", error=e), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html", error=e), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html", error=e), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("errors/429.html", error=e), 429

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("500 error: %s", e, exc_info=True)
        return render_template("errors/500.html", error=e), 500

    log_dir = os.path.join(os.path.dirname(app.root_path), "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "admin.log"), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    if app.debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        root_logger.addHandler(stream_handler)

    return app
