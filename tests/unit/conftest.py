"""
Unit test fixtures — no DB, no HTTP server needed.
Boots a Flask app context so helpers that read current_app.config work.
"""
import io
from pathlib import Path

import pytest
from PIL import Image

import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Load .env so SECRET_KEY and DATABASE_URL are set before app creation.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@pytest.fixture(scope="session")
def _flask_app():
    from admin import create_admin_app
    return create_admin_app()


@pytest.fixture
def app(_flask_app, tmp_path: Path):
    saved = {k: _flask_app.config.get(k) for k in (
        "UPLOAD_FOLDER", "UPLOAD_ALLOWED_EXTENSIONS",
        "UPLOAD_MAX_FILE_MB", "IMAGE_BASE_URL",
        "UPLOAD_API_URL", "UPLOAD_API_KEY",
    )}
    _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
    _flask_app.config["UPLOAD_ALLOWED_EXTENSIONS"] = frozenset(
        {"jpg", "jpeg", "gif", "png", "webp"}
    )
    _flask_app.config["UPLOAD_MAX_FILE_MB"] = 5
    _flask_app.config["IMAGE_BASE_URL"] = ""
    _flask_app.config["UPLOAD_API_URL"] = ""
    _flask_app.config["UPLOAD_API_KEY"] = ""
    yield _flask_app
    for k, v in saved.items():
        _flask_app.config[k] = v


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


def _make_image(fmt="PNG", w=50, h=50) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="red").save(buf, format=fmt)
    return buf.getvalue()


class FakeFile:
    """Minimal werkzeug FileStorage shim."""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)

    def save(self, dst: str) -> None:
        self.stream.seek(0)
        Path(dst).write_bytes(self.stream.read())


@pytest.fixture
def png_file():
    return FakeFile("sample.png", _make_image("PNG"))

@pytest.fixture
def jpg_file():
    return FakeFile("sample.jpg", _make_image("JPEG"))

@pytest.fixture
def wide_png():
    return FakeFile("wide.png", _make_image("PNG", w=3000, h=1000))

@pytest.fixture
def make_file():
    return FakeFile
