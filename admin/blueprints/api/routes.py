"""
CKEditor image upload / orphan-delete API.

POST /api/ck-upload/<subfolder>
    Multipart file upload from CKEditor's custom adapter.
    Returns {"url": "<absolute or local url>"} on success.

POST /api/ck-delete
    JSON body: {"urls": ["...", ...]}  — absolute URLs removed from editor.
    Converts each absolute URL back to a relative path and calls _remote_delete
    (or removes the local file), then returns {"ok": true}.
"""

import logging
import os
import re
import time

from flask import current_app, jsonify, request, url_for
from flask_login import login_required

from admin.blueprints.api import bp
from PIL import Image
from admin.utils.upload import (
    _allowed_extensions,
    _max_file_bytes,
    _remote_delete,
    _remote_upload,
    _safe_open,
    _save_to_buf,
    _use_remote,
    MAX_IMAGE_WIDTH,
)

log = logging.getLogger(__name__)

_VALID_SUBFOLDERS = frozenset({"pro", "news", "media", "menu", "user", "icon", "intro"})


@bp.post("/ck-upload/<subfolder>")
@login_required
def ck_upload(subfolder: str):
    if subfolder not in _VALID_SUBFOLDERS:
        return jsonify({"error": {"message": "Invalid subfolder"}}), 400

    f = request.files.get("upload")
    if not f or not f.filename:
        return jsonify({"error": {"message": "No file"}}), 400

    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in _allowed_extensions():
        return jsonify({"error": {"message": f"Extension .{ext} not allowed"}}), 400

    f.stream.seek(0, 2)
    size = f.stream.tell()
    f.stream.seek(0)
    if size > _max_file_bytes():
        mb = _max_file_bytes() // (1024 * 1024)
        return jsonify({"error": {"message": f"File too large (max {mb} MB)"}}), 400

    img = _safe_open(f)
    if img is None:
        return jsonify({"error": {"message": "Invalid image"}}), 400

    if img.width > MAX_IMAGE_WIDTH:
        ratio = MAX_IMAGE_WIDTH / img.width
        img = img.resize((MAX_IMAGE_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    if ext in ("jpg", "jpeg") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # original name (no path) + timestamp suffix to avoid collisions
    base_name = os.path.splitext(os.path.basename(f.filename))[0]
    ts = int(time.time())
    filename = f"{base_name}_{ts}.{ext}"
    remote_path = f"{subfolder}/{filename}"

    if _use_remote():
        buf = _save_to_buf(img, ext)
        log.info("ck_upload: sending %s bytes to remote, path=%s", buf.getbuffer().nbytes, remote_path)
        if not _remote_upload(buf, remote_path, f"image/{ext}"):
            return jsonify({"error": {"message": "Upload to remote server failed"}}), 502

        base_url = current_app.config.get("IMAGE_BASE_URL", "").rstrip("/")
        url = f"{base_url}/{remote_path}"
    else:
        upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
        os.makedirs(upload_dir, exist_ok=True)
        img.save(os.path.join(upload_dir, filename))
        url = url_for("static", filename=f"uploads/{remote_path}")

    return jsonify({"url": url})


@bp.post("/ck-delete")
@login_required
def ck_delete():
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])
    if not isinstance(urls, list):
        return jsonify({"ok": False, "error": "urls must be a list"}), 400

    base_url = current_app.config.get("IMAGE_BASE_URL", "").rstrip("/")
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "")
    origin_match = re.match(r'^(https?://[^/]+)', base_url)
    origin = origin_match.group(1) if origin_match else base_url

    for url in urls:
        if not isinstance(url, str):
            continue

        # Derive relative path from the URL.
        # After toView, the browser sends absolute URLs like:
        #   https://domain.com/images/pro/file.jpg  → managed, delete it
        #   https://domain.com/Uploads/images/...   → legacy VB content, skip
        if origin and url.startswith(origin + "/"):
            rel = url[len(origin) + 1:]  # e.g. "images/pro/file.jpg" or "Uploads/images/Banner/f.png"
        elif url.startswith("/"):
            rel = url[1:]
        else:
            log.debug("ck-delete: unrecognised URL pattern, skipping: %s", url)
            continue

        # Only delete files under managed subfolders — skip legacy /Uploads/ paths
        parts = rel.split("/")
        if not parts or parts[0] not in ("images",):
            log.debug("ck-delete: not a managed path, skipping: %s", rel)
            continue
        # Strip leading "images/" to get subfolder/filename
        rel = "/".join(parts[1:])

        # Reject anything that looks like path traversal
        if ".." in rel or rel.startswith("/"):
            log.warning("ck-delete: suspicious path rejected: %s", rel)
            continue

        if _use_remote():
            _remote_delete(rel)
        else:
            path = os.path.join(upload_folder, rel)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError as e:
                    log.warning("ck-delete local remove failed for %s: %s", path, e)

    return jsonify({"ok": True})
