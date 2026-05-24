"""Unit tests for upload validation and save helpers."""
import io
import os
import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def _make_image(fmt="PNG", w=50, h=50) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h)).save(buf, format=fmt)
    return buf.getvalue()


class FakeFile:
    def __init__(self, filename, content=b""):
        self.filename = filename
        self.stream = io.BytesIO(content)
        self.content_length = len(content)

    def read(self, n=-1):
        return self.stream.read(n)

    def seek(self, pos):
        self.stream.seek(pos)


# ── validate_upload_file ──────────────────────────────────────────────

class TestValidateUploadFile:
    def test_no_file_is_ok(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        assert validate_upload_file(None) is None

    def test_empty_filename_is_ok(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("")
        assert validate_upload_file(f) is None

    def test_valid_jpg(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("photo.jpg", _make_image("JPEG"))
        assert validate_upload_file(f) is None

    def test_valid_png(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("photo.png", _make_image("PNG"))
        assert validate_upload_file(f) is None

    def test_valid_webp(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("img.webp", _make_image("WEBP"))
        assert validate_upload_file(f) is None

    def test_disallowed_extension_returns_error(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("virus.exe", b"MZ\x90\x00")
        err = validate_upload_file(f)
        assert err is not None
        assert isinstance(err, str)

    def test_svg_disallowed(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("icon.svg", b"<svg/>")
        err = validate_upload_file(f)
        assert err is not None

    def test_pdf_disallowed(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("doc.pdf", b"%PDF-1.4")
        err = validate_upload_file(f)
        assert err is not None

    def test_oversized_file_returns_error(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        # 6 MB > 5 MB limit
        big_content = b"x" * (6 * 1024 * 1024)
        f = FakeFile("big.jpg", big_content)
        f.content_length = len(big_content)
        err = validate_upload_file(f)
        assert err is not None

    def test_exactly_at_limit_is_ok(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        # 5 MB exactly — should pass
        content = b"x" * (5 * 1024 * 1024)
        f = FakeFile("ok.jpg", content)
        assert validate_upload_file(f) is None

    def test_error_message_mentions_extension(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        f = FakeFile("bad.bmp", b"BM")
        err = validate_upload_file(f)
        assert err is not None
        assert "jpg" in err.lower() or "png" in err.lower() or "chấp nhận" in err

    def test_error_message_mentions_size(self, app_ctx):
        from admin.utils.upload import validate_upload_file
        big = b"x" * (6 * 1024 * 1024)
        f = FakeFile("big.png", big)
        err = validate_upload_file(f)
        assert err is not None
        assert "mb" in err.lower() or "lớn" in err.lower()


# ── save_news_image ───────────────────────────────────────────────────

class TestSaveNewsImage:
    def test_valid_png_saved_to_disk(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("photo.png", _make_image("PNG", w=100, h=100))
        result = save_news_image(f, record_id=99)
        assert result == "news_99.png"
        assert os.path.exists(tmp_path / "news" / "news_99.png")

    def test_valid_jpg_saved_to_disk(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("photo.jpg", _make_image("JPEG", w=100, h=100))
        result = save_news_image(f, record_id=42)
        assert result == "news_42.jpg"
        assert os.path.exists(tmp_path / "news" / "news_42.jpg")

    def test_wide_image_gets_resized(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        # 1200px wide — above 600px news limit
        f = FakeFile("wide.png", _make_image("PNG", w=1200, h=400))
        save_news_image(f, record_id=55)
        saved = Image.open(tmp_path / "news" / "news_55.png")
        assert saved.width <= 600

    def test_narrow_image_not_resized(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("small.png", _make_image("PNG", w=300, h=200))
        save_news_image(f, record_id=77)
        saved = Image.open(tmp_path / "news" / "news_77.png")
        assert saved.width == 300

    def test_no_file_returns_none(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        assert save_news_image(None, record_id=1) is None

    def test_invalid_extension_returns_none(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("doc.pdf", b"%PDF-1.4")
        assert save_news_image(f, record_id=1) is None

    def test_corrupt_image_returns_none(self, app_ctx, tmp_path):
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("fake.jpg", b"not-image-bytes")
        assert save_news_image(f, record_id=1) is None

    def test_old_file_removed_on_replace(self, app_ctx, tmp_path):
        """Uploading a new image for the same ID removes the old file."""
        from admin.utils.upload import save_news_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        news_dir = tmp_path / "news"
        news_dir.mkdir(parents=True, exist_ok=True)
        # Plant a stale old file with a different ext
        old_file = news_dir / "news_10.gif"
        old_file.write_bytes(b"old")
        f = FakeFile("new.png", _make_image("PNG", w=50, h=50))
        save_news_image(f, record_id=10)
        assert not old_file.exists(), "Old file should have been deleted"
        assert os.path.exists(news_dir / "news_10.png")


# ── save_pro_image ────────────────────────────────────────────────────

class TestSaveProImage:
    def test_thumbnail_saved_with_sm_prefix(self, app_ctx, tmp_path):
        from admin.utils.upload import save_pro_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("thumb.png", _make_image("PNG", w=100, h=100))
        result = save_pro_image(f, record_id=5, prefix="sm-", max_width=200)
        assert result == "sm-5.png"
        assert os.path.exists(tmp_path / "pro" / "sm-5.png")

    def test_large_saved_with_lg_prefix(self, app_ctx, tmp_path):
        from admin.utils.upload import save_pro_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("large.jpg", _make_image("JPEG", w=100, h=100))
        result = save_pro_image(f, record_id=5, prefix="lg_", max_width=800)
        assert result == "lg_5.jpg"

    def test_oversized_thumbnail_resized(self, app_ctx, tmp_path):
        from admin.utils.upload import save_pro_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("big.png", _make_image("PNG", w=500, h=500))
        save_pro_image(f, record_id=7, prefix="sm-", max_width=200)
        saved = Image.open(tmp_path / "pro" / "sm-7.png")
        assert saved.width <= 200

    def test_no_file_returns_none(self, app_ctx, tmp_path):
        from admin.utils.upload import save_pro_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        assert save_pro_image(None, record_id=1, prefix="sm-", max_width=200) is None

    def test_invalid_extension_returns_none(self, app_ctx, tmp_path):
        from admin.utils.upload import save_pro_image
        app_ctx.config["UPLOAD_FOLDER"] = str(tmp_path)
        f = FakeFile("virus.exe", b"MZ\x90")
        assert save_pro_image(f, record_id=1, prefix="sm-", max_width=200) is None
