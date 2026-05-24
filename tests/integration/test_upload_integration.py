"""
Integration tests for image upload via HTTP (Flask test client + real DB).

Covers:
- News: valid upload → ImgN updated in DB, file written to disk
- News: invalid extension → flash error, ImgN NOT changed
- News: oversized file → flash error, ImgN NOT changed
- Product: valid thumbnail upload → ImgP updated
- Product: invalid extension → flash error shown
"""
import io
import os
import time

import pytest
from PIL import Image

pytestmark = pytest.mark.integration


def _make_png(w=100, h=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="blue").save(buf, format="PNG")
    return buf.getvalue()


def _make_jpg(w=100, h=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _name():
    return f"[TEST] Upload {int(time.time() * 1000)}"


# ── helpers ───────────────────────────────────────────────────────────

def _create_news(authed_client, db_conn, name=None):
    name = name or _name()
    authed_client.post(
        "/news/new",
        data={"name": name, "slug": "test-upload-news"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDN" FROM "tblNews" WHERE "NameN" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return (row[0] if row else None), name


def _create_product(authed_client, db_conn, name=None):
    name = name or _name()
    authed_client.post(
        "/product/new",
        data={"name": name, "slug": "test-upload-pro"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDP" FROM "tblPro" WHERE "NameP" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return (row[0] if row else None), name


# ── News upload ───────────────────────────────────────────────────────

class TestNewsUpload:
    def test_valid_png_updates_img_in_db(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        news_id, name = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create news row")

        resp = authed_client.post(
            f"/news/{news_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-news",
                "img_file": (io.BytesIO(_make_png()), "cover.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200

        cur = db_conn.cursor()
        cur.execute('SELECT "ImgN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None
        assert row[0] == f"news_{news_id}.png"
        assert os.path.exists(tmp_path / "news" / f"news_{news_id}.png")

    def test_invalid_extension_shows_error_and_does_not_change_db(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        news_id, name = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create news row")

        resp = authed_client.post(
            f"/news/{news_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-news",
                "img_file": (io.BytesIO(b"fake"), "malware.exe"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Định dạng" in html or "chấp nhận" in html

        cur = db_conn.cursor()
        cur.execute('SELECT "ImgN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None
        assert row[0] == "null.gif", "ImgN should remain unchanged after bad upload"

    def test_oversized_file_shows_error(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        news_id, name = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create news row")

        big = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
        resp = authed_client.post(
            f"/news/{news_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-news",
                "img_file": (io.BytesIO(big), "huge.jpg"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "lớn" in html or "MB" in html

    def test_no_file_upload_does_not_change_img(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        """Editing without selecting a file must leave ImgN alone."""
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        news_id, name = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create news row")

        # First upload a real image to set ImgN
        authed_client.post(
            f"/news/{news_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-news",
                "img_file": (io.BytesIO(_make_png()), "first.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        # Now edit without any file — ImgN must not be reset to null.gif
        authed_client.post(
            f"/news/{news_id}/edit",
            data={"name": name, "slug": "test-upload-news"},
            follow_redirects=True,
        )

        cur = db_conn.cursor()
        cur.execute('SELECT "ImgN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row[0] == f"news_{news_id}.png", "ImgN must not reset when no file sent"


# ── Product upload ────────────────────────────────────────────────────

class TestProductUpload:
    def test_valid_thumbnail_updates_img_in_db(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        prod_id, name = _create_product(authed_client, db_conn)
        if prod_id is None:
            pytest.skip("Could not create product row")

        resp = authed_client.post(
            f"/product/{prod_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-pro",
                "img_file": (io.BytesIO(_make_jpg()), "thumb.jpg"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200

        cur = db_conn.cursor()
        cur.execute('SELECT "ImgP" FROM "tblPro" WHERE "IDP" = %s', (prod_id,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None
        assert row[0] == f"sm-{prod_id}.jpg"
        assert os.path.exists(tmp_path / "pro" / f"sm-{prod_id}.jpg")

    def test_invalid_extension_shows_error(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        prod_id, name = _create_product(authed_client, db_conn)
        if prod_id is None:
            pytest.skip("Could not create product row")

        resp = authed_client.post(
            f"/product/{prod_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-pro",
                "img_file": (io.BytesIO(b"fake"), "bad.bmp"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Định dạng" in html or "chấp nhận" in html

        cur = db_conn.cursor()
        cur.execute('SELECT "ImgP" FROM "tblPro" WHERE "IDP" = %s', (prod_id,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row[0] == "null.gif", "ImgP should remain null.gif after bad upload"

    def test_large_image_upload_updates_img1_in_db(
        self, authed_client, db_conn, _flask_app, tmp_path
    ):
        _flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        prod_id, name = _create_product(authed_client, db_conn)
        if prod_id is None:
            pytest.skip("Could not create product row")

        resp = authed_client.post(
            f"/product/{prod_id}/edit",
            data={
                "name": name,
                "slug": "test-upload-pro",
                "img1_file": (io.BytesIO(_make_png(w=200, h=200)), "large.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Img1P" FROM "tblPro" WHERE "IDP" = %s', (prod_id,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None
        assert row[0] == f"lg_{prod_id}.png"
