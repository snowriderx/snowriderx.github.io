import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    DEBUG = os.getenv("FLASK_ENV") == "development"

    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]  # postgresql://...
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }


class AdminConfig(Config):
    SESSION_COOKIE_NAME = "__sr_appid"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    REMEMBER_COOKIE_NAME = "__sr_remember"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_DURATION = 86400
    REMEMBER_COOKIE_PATH = "/admin"
    SESSION_COOKIE_PATH = "/admin"

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "theme/static/uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024
    UPLOAD_MAX_FILE_MB = int(os.getenv("UPLOAD_MAX_FILE_MB", "5"))
    UPLOAD_ALLOWED_EXTENSIONS = frozenset(
        os.getenv("UPLOAD_ALLOWED_EXTENSIONS", "jpg,jpeg,gif,png,webp").split(",")
    )

    IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "")
    UPLOAD_API_URL = os.getenv("UPLOAD_API_URL", "")
    UPLOAD_API_KEY = os.getenv("UPLOAD_API_KEY", "")

    SITE_NAME = os.getenv("SITE_NAME", "Admin Panel")

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_LOGIN = os.getenv("RATELIMIT_LOGIN", "5 per minute;20 per hour")
    RATELIMIT_CHANGE_PW = os.getenv("RATELIMIT_CHANGE_PW", "5 per minute")
    RATELIMIT_MUTATION = os.getenv("RATELIMIT_MUTATION", "30 per minute")


class ClientConfig(Config):
    SESSION_COOKIE_NAME = "__client_id"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
