"""
Image upload helper for banner/media assets.

VB equivalent: Bambu.oData.UploadFile(FilePro, lblID.Text, "/images/media", …)
The VB helper renames the file to <ID>.<ext> and updates the DB column.
save_media_image() replicates that contract: returns filename to store in DB.

Storage layout (mirrors VB /images/media/):
  UPLOAD_FOLDER/media/<record_id>.<ext>         (local mode)
  <UPLOAD_API_URL> POST  media/<record_id>.<ext> (remote mode)
Served at:
  /static/uploads/media/<record_id>.<ext>       (local mode)
  <IMAGE_BASE_URL>/media/<record_id>.<ext>       (remote mode)
"""

import io
import json
import logging
import os

import requests as _requests
from flask import current_app
from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

# VB UploadFile iW parameter — max width in pixels before resizing
MAX_IMAGE_WIDTH = 1920

# Hard cap: reject images larger than 50 MP to prevent decompression bombs.
_MAX_PIXELS = 50_000_000

_DEFAULT_EXTENSIONS = frozenset({"jpg", "jpeg", "gif", "png", "webp"})
_DEFAULT_MAX_FILE_MB = 5

_PILLOW_FORMAT = {
    "jpg": "JPEG", "jpeg": "JPEG",
    "png": "PNG", "gif": "GIF", "webp": "WEBP",
}


# ------------------------------------------------------------------ #
# Config helpers
# ------------------------------------------------------------------ #

def _allowed_extensions() -> frozenset:
    try:
        return current_app.config["UPLOAD_ALLOWED_EXTENSIONS"]
    except RuntimeError:
        return _DEFAULT_EXTENSIONS


def _max_file_bytes() -> int:
    try:
        mb = current_app.config["UPLOAD_MAX_FILE_MB"]
    except RuntimeError:
        mb = _DEFAULT_MAX_FILE_MB
    return mb * 1024 * 1024


def _use_remote() -> bool:
    """True when UPLOAD_API_URL is configured — use remote HTTP upload."""
    try:
        return bool(current_app.config.get("UPLOAD_API_URL", ""))
    except RuntimeError:
        return False


# ------------------------------------------------------------------ #
# Remote upload / delete
# ------------------------------------------------------------------ #

def _remote_upload(buf: io.BytesIO, remote_path: str, content_type: str) -> bool:
    """POST image bytes to the client upload API. Returns True on success."""
    api_url = current_app.config.get("UPLOAD_API_URL", "").rstrip("/")
    api_key = current_app.config.get("UPLOAD_API_KEY", "")
    try:
        buf.seek(0)
        # Use a fresh session per call — avoids stale keep-alive connections
        # which cause IIS to return 404 with empty body on reused TLS sockets.
        with _requests.Session() as s:
            s.max_redirects = 3
            resp = s.post(
                api_url,
                headers={"X-API-Key": api_key, "Connection": "close"},
                files={"file": (remote_path, buf, content_type)},
                data={"path": remote_path},
                timeout=20,
            )
        if resp.status_code == 200:
            return True
        log.warning(
            "Remote upload failed (%s): %s — body: %s",
            resp.status_code, remote_path, resp.text[:200],
        )
        return False
    except Exception as e:
        log.error("Remote upload error for %s: %s", remote_path, e, exc_info=True)
        return False


def _remote_delete(remote_path: str) -> None:
    """Ask client API to delete a file. Errors are logged and ignored."""
    if not remote_path:
        return
    api_url = current_app.config.get("UPLOAD_API_URL", "").rstrip("/")
    api_key = current_app.config.get("UPLOAD_API_KEY", "")
    if not api_url:
        return
    try:
        with _requests.Session() as s:
            s.post(
                f"{api_url}?action=delete",
                headers={"X-API-Key": api_key, "Connection": "close"},
                json={"path": remote_path},
                timeout=10,
            )
    except Exception as e:
        log.warning("Remote delete error for %s: %s", remote_path, e)


def _save_to_buf(img: "Image.Image", ext: str) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format=_PILLOW_FORMAT.get(ext, ext.upper()))
    buf.seek(0)
    return buf


# ------------------------------------------------------------------ #
# Validation / image open
# ------------------------------------------------------------------ #

def validate_upload_file(file_storage) -> str | None:
    """
    Check extension and file size of an uploaded file.

    Returns an error message string if the file is invalid, or None if it
    passes (or if no file was supplied — callers that require a file must
    check for presence separately).
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    allowed = _allowed_extensions()
    if ext not in allowed:
        return (
            f"Định dạng không được hỗ trợ. "
            f"Chỉ chấp nhận: {', '.join(sorted(allowed))}."
        )

    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    max_bytes = _max_file_bytes()
    if size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return f"File quá lớn. Kích thước tối đa là {mb} MB."

    return None


def _safe_open(file_storage) -> "Image.Image | None":
    """
    Open and verify an uploaded image through Pillow.

    Returns the Image object or None on any validation failure.
    """
    old_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = _MAX_PIXELS
        img = Image.open(file_storage.stream)
        img.load()
        return img
    except (Image.DecompressionBombError, UnidentifiedImageError, Exception) as e:
        log.warning("_safe_open failed for %s: %s", getattr(file_storage, "filename", "?"), e)
        return None
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit


# ------------------------------------------------------------------ #
# Local directory helpers
# ------------------------------------------------------------------ #

def _media_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "media")
    os.makedirs(path, exist_ok=True)
    return path


def _pro_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "pro")
    os.makedirs(path, exist_ok=True)
    return path


def _news_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "news")
    os.makedirs(path, exist_ok=True)
    return path


def _menu_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "menu")
    os.makedirs(path, exist_ok=True)
    return path


def _user_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "user")
    os.makedirs(path, exist_ok=True)
    return path


def _icon_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "icon")
    os.makedirs(path, exist_ok=True)
    return path


def _intro_dir() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "intro")
    os.makedirs(path, exist_ok=True)
    return path


# ------------------------------------------------------------------ #
# Icon filename registry (remote mode only)
# Icons are not stored in DB, so we keep a local JSON file on the admin
# server that maps name → filename (e.g. "logo" → "logo.png").
# ------------------------------------------------------------------ #

def _icon_registry_path() -> str:
    base = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "icon_registry.json")


def _read_icon_registry() -> dict:
    try:
        with open(_icon_registry_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_icon_registry(name: str, filename: str) -> None:
    try:
        data = _read_icon_registry()
        data[name] = filename
        with open(_icon_registry_path(), "w") as f:
            json.dump(data, f)
    except Exception as e:
        log.warning("Could not write icon registry: %s", e)


# ------------------------------------------------------------------ #
# Media image helpers  (/uploads/media/)
# ------------------------------------------------------------------ #

def save_media_image(file_storage, record_id: int) -> str | None:
    """
    Save uploaded file as <record_id>.<ext> in media/.
    Returns the bare filename (e.g. '55.jpg') to persist in tblAdvert.Img,
    or None if no valid file was supplied.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    filename = f"{record_id}.{ext}"

    if img.width > MAX_IMAGE_WIDTH:
        ratio = MAX_IMAGE_WIDTH / img.width
        img = img.resize((MAX_IMAGE_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"media/{filename}", f"image/{ext}"):
            return None
    else:
        media_dir = _media_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(media_dir, f"{record_id}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(media_dir, filename))

    return filename


def delete_media_image(record_id: int) -> None:
    """Delete all image files for a given record ID."""
    if _use_remote():
        for ext in _allowed_extensions():
            _remote_delete(f"media/{record_id}.{ext}")
        return
    try:
        media_dir = _media_dir()
    except RuntimeError:
        return
    for ext in _allowed_extensions() | {"swf"}:
        path = os.path.join(media_dir, f"{record_id}.{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ------------------------------------------------------------------ #
# Product image helpers  (/uploads/pro/)
# ------------------------------------------------------------------ #

def save_pro_image(
    file_storage,
    record_id: int,
    prefix: str,
    max_width: int,
) -> str | None:
    """
    Save a product image as <prefix><record_id>.<ext> in pro/.
    prefix is 'sm-' for thumbnail or 'lg_' for the large image.
    Returns the bare filename to persist in tblPro, or None if no valid file.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    stem = f"{prefix}{record_id}"
    filename = f"{stem}.{ext}"

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"pro/{filename}", f"image/{ext}"):
            return None
    else:
        pro_dir = _pro_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(pro_dir, f"{stem}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(pro_dir, filename))

    return filename


def delete_pro_image_file(filename: str | None) -> None:
    """Delete a single product image by its stored filename."""
    if not filename or filename == "null.gif":
        return
    if _use_remote():
        _remote_delete(f"pro/{filename}")
        return
    try:
        pro_dir = _pro_dir()
    except RuntimeError:
        return
    path = os.path.join(pro_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------------------ #
# News image helpers  (/uploads/news/)
# ------------------------------------------------------------------ #

_NEWS_MAX_WIDTH = 600


def save_news_image(file_storage, record_id: int) -> str | None:
    """
    Save uploaded file as news_<record_id>.<ext> in news/.
    Returns the bare filename (e.g. 'news_42.jpg') to persist in tblNews.ImgN,
    or None if no valid file was supplied.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    stem = f"news_{record_id}"
    filename = f"{stem}.{ext}"

    if img.width > _NEWS_MAX_WIDTH:
        ratio = _NEWS_MAX_WIDTH / img.width
        img = img.resize((_NEWS_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"news/{filename}", f"image/{ext}"):
            return None
    else:
        news_dir = _news_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(news_dir, f"{stem}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(news_dir, filename))

    return filename


def delete_news_image_file(filename: str | None) -> None:
    """Delete a single news image by its stored filename."""
    if not filename or filename == "null.gif":
        return
    if _use_remote():
        _remote_delete(f"news/{filename}")
        return
    try:
        news_dir = _news_dir()
    except RuntimeError:
        return
    path = os.path.join(news_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------------------ #
# Menu image helpers  (/uploads/menu/)
# ------------------------------------------------------------------ #

_MENU_ICON_MAX_WIDTH   = 200
_MENU_BANNER_MAX_WIDTH = 500


def save_menu_image(
    file_storage,
    slug: str,
    auto_m: "int | None",
    slot: str,
) -> "str | None":
    """
    Save a menu image file.
    slot must be 'icon' (max 200px) or 'banner' (max 500px).
    Returns the bare filename to store in DB, or None if no valid file.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    max_width = _MENU_ICON_MAX_WIDTH if slot == "icon" else _MENU_BANNER_MAX_WIDTH
    stem = f"{slug}{auto_m}_{slot}" if auto_m else f"menu_{slug}_{slot}"
    filename = f"{stem}.{ext}"

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"menu/{filename}", f"image/{ext}"):
            return None
    else:
        menu_dir = _menu_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(menu_dir, f"{stem}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(menu_dir, filename))

    return filename


def delete_menu_image_file(filename: "str | None") -> None:
    """Delete a single menu image file by its stored filename."""
    if not filename or filename == "null.gif":
        return
    if _use_remote():
        _remote_delete(f"menu/{filename}")
        return
    try:
        menu_dir = _menu_dir()
    except RuntimeError:
        return
    path = os.path.join(menu_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------------------ #
# User avatar helpers  (/uploads/user/)
# ------------------------------------------------------------------ #

_USER_AVATAR_MAX_WIDTH = 400


def save_user_image(file_storage, record_id: int) -> "str | None":
    """
    Save uploaded avatar as user_<IDU>.<ext> in user/.
    Returns the bare filename to persist in tblUser.ImgU, or None.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    stem = f"user_{record_id}"
    filename = f"{stem}.{ext}"

    if img.width > _USER_AVATAR_MAX_WIDTH:
        ratio = _USER_AVATAR_MAX_WIDTH / img.width
        img = img.resize((_USER_AVATAR_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"user/{filename}", f"image/{ext}"):
            return None
    else:
        user_dir = _user_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(user_dir, f"{stem}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(user_dir, filename))

    return filename


def delete_user_image(record_id: int) -> None:
    """Delete all avatar files for a given user IDU."""
    if _use_remote():
        stem = f"user_{record_id}"
        for ext in _allowed_extensions():
            _remote_delete(f"user/{stem}.{ext}")
        return
    try:
        user_dir = _user_dir()
    except RuntimeError:
        return
    stem = f"user_{record_id}"
    for ext in _allowed_extensions() | {"swf"}:
        path = os.path.join(user_dir, f"{stem}.{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ------------------------------------------------------------------ #
# Site icon helpers  (/uploads/icon/)
# Fixed filenames (logo, favicon, share) — not stored in DB.
# In remote mode, filenames are tracked in a local JSON registry file.
# ------------------------------------------------------------------ #

_ICON_MAX_WIDTH = 1024


def save_icon_image(file_storage, name: str) -> str | None:
    """
    Save a fixed-name site icon (logo, favicon, share).
    Returns the bare filename (e.g. 'logo.png') or None if no valid file.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    filename = f"{name}.{ext}"

    if img.width > _ICON_MAX_WIDTH:
        ratio = _ICON_MAX_WIDTH / img.width
        img = img.resize((_ICON_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"icon/{filename}", f"image/{ext}"):
            return None
        _write_icon_registry(name, filename)
    else:
        icon_dir = _icon_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(icon_dir, f"{name}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(icon_dir, filename))

    return filename


def get_icon_filename(name: str) -> str | None:
    """
    Return the current filename for a site icon (e.g. 'logo.png'), or None.
    In remote mode, reads from the local icon registry JSON.
    """
    if _use_remote():
        return _read_icon_registry().get(name)
    try:
        icon_dir = _icon_dir()
    except RuntimeError:
        return None
    for ext in _allowed_extensions():
        path = os.path.join(icon_dir, f"{name}.{ext}")
        if os.path.exists(path):
            return f"{name}.{ext}"
    return None


# ------------------------------------------------------------------ #
# Intro image helpers  (/uploads/intro/)
# ------------------------------------------------------------------ #

_INTRO_MAX_WIDTH = 100


def save_intro_image(file_storage, record_id: int) -> "str | None":
    """
    Save uploaded file as intro_<record_id>.<ext> in intro/.
    Returns the bare filename (e.g. 'intro_7.jpg') to persist in tblIntro.Img,
    or None if no valid file was supplied.
    """
    if not file_storage or not file_storage.filename:
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return None

    img = _safe_open(file_storage)
    if img is None:
        return None

    stem = f"intro_{record_id}"
    filename = f"{stem}.{ext}"

    if img.width > _INTRO_MAX_WIDTH:
        ratio = _INTRO_MAX_WIDTH / img.width
        img = img.resize((_INTRO_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if _use_remote():
        buf = _save_to_buf(img, ext)
        if not _remote_upload(buf, f"intro/{filename}", f"image/{ext}"):
            return None
    else:
        intro_dir = _intro_dir()
        for old_ext in _allowed_extensions() | {"swf"}:
            old_path = os.path.join(intro_dir, f"{stem}.{old_ext}")
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        img.save(os.path.join(intro_dir, filename))

    return filename


def delete_intro_image_file(filename: "str | None") -> None:
    """Delete a single intro image file by its stored filename."""
    if not filename or filename == "null.gif":
        return
    if _use_remote():
        _remote_delete(f"intro/{filename}")
        return
    try:
        intro_dir = _intro_dir()
    except RuntimeError:
        return
    path = os.path.join(intro_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
