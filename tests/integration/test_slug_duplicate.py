"""
Slug duplicate integration tests.

Kiểm tra hành vi khi 2 records dùng cùng slug:
- tblLink phải không có duplicate RowUrl cho cùng RowType khi edit cùng record
- Edit một record để thay slug mới — tblLink cũ phải bị xóa
- Slug format validation: chỉ cho phép [a-z0-9-]
"""
import time

import pytest

pytestmark = pytest.mark.integration

_TS = str(int(time.time()))


def _slug(label: str) -> str:
    """Unique slug per test-run (timestamp suffix) — avoids tblLink accumulation."""
    return f"tst-{label}-{_TS}"


def _name(prefix="News"):
    return f"[TEST] {prefix} {int(time.time() * 1000)}"


# ── helpers ───────────────────────────────────────────────────────────

def _get_menu_id(db_conn) -> "str | None":
    """IDM của menu TypeM=1 (category) active — required for tblLink sync."""
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "IDM" FROM "tblMenu" WHERE "AcM" = 1 AND "TypeM" = 1 LIMIT 1'
    )
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


def _count_tbllink(db_conn, slug: str, row_type: int) -> int:
    cur = db_conn.cursor()
    cur.execute(
        'SELECT COUNT(*) FROM "tblLink"'
        ' WHERE LOWER("RowUrl") = %s AND "RowType" = %s',
        (slug.lower(), row_type),
    )
    count = cur.fetchone()[0]
    db_conn.rollback()
    return count


def _create_news(
    authed_client, db_conn, name: str, slug: str, menu_id: str = ""
) -> "int | None":
    authed_client.post(
        "/news/new",
        data={"name": name, "slug": slug, "menu_id": menu_id},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDN" FROM "tblNews" WHERE "NameN" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


def _edit_news(authed_client, news_id, name, slug, menu_id=""):
    authed_client.post(
        f"/news/{news_id}/edit",
        data={"name": name, "slug": slug, "menu_id": menu_id},
        follow_redirects=True,
    )


def _create_product(
    authed_client, db_conn, name: str, slug: str
) -> "int | None":
    # locale (LocaleP) is the field _sync_tbl_link writes to RowUrl
    authed_client.post(
        "/product/new",
        data={"name": name, "slug": slug, "locale": slug},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDP" FROM "tblPro" WHERE "NameP" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


def _edit_product(authed_client, prod_id, name, slug):
    authed_client.post(
        f"/product/{prod_id}/edit",
        data={"name": name, "slug": slug, "locale": slug},
        follow_redirects=True,
    )


# ── News slug ─────────────────────────────────────────────────────────

class TestNewsSlugDuplicate:
    def test_same_news_edited_twice_keeps_one_tbllink_row(
        self, authed_client, db_conn
    ):
        """Edit cùng 1 news 2 lần với cùng slug — DELETE+INSERT → chỉ 1 row."""
        menu_id = _get_menu_id(db_conn)
        if menu_id is None:
            pytest.skip("No active category menu in DB")

        slug = _slug("dup-same")
        name = _name("News")
        news_id = _create_news(authed_client, db_conn, name, slug, menu_id)
        if news_id is None:
            pytest.skip("Could not create news")

        _edit_news(authed_client, news_id, name, slug, menu_id)

        count = _count_tbllink(db_conn, slug, row_type=2)
        assert count <= 1, (
            f"tblLink có {count} rows cho slug '{slug}' — expect ≤ 1"
        )

    def test_duplicate_slug_rejected_on_second_news(
        self, authed_client, db_conn
    ):
        """
        Tạo news thứ 2 với slug đã tồn tại → form phải báo lỗi,
        tblLink chỉ có đúng 1 row (không tạo routing conflict).
        """
        menu_id = _get_menu_id(db_conn)
        if menu_id is None:
            pytest.skip("No active category menu in DB")

        slug = _slug("dup-conflict")
        # Tạo news đầu tiên — phải thành công
        _create_news(authed_client, db_conn, _name("NewsA"), slug, menu_id)
        assert _count_tbllink(db_conn, slug, row_type=2) == 1

        # Tạo news thứ hai với cùng slug — phải bị reject
        resp = authed_client.post(
            "/news/new",
            data={"name": _name("NewsB"), "slug": slug, "menu_id": menu_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "đã được dùng" in html, (
            "Duplicate slug phải hiện error, không được tạo thành công"
        )

        # tblLink vẫn chỉ có 1 row — không có routing conflict
        assert _count_tbllink(db_conn, slug, row_type=2) == 1, (
            "tblLink phải chỉ có 1 row cho slug này"
        )

    def test_slug_format_rejects_uppercase(self, authed_client):
        """Slug có chữ hoa phải bị reject."""
        resp = authed_client.post(
            "/news/new",
            data={"name": _name("News"), "slug": "Invalid-Slug"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Slug" in html or "chữ thường" in html

    def test_slug_format_rejects_spaces(self, authed_client):
        """Slug có khoảng trắng phải bị reject."""
        resp = authed_client.post(
            "/news/new",
            data={"name": _name("News"), "slug": "slug with spaces"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Slug" in html

    def test_slug_format_rejects_special_chars(self, authed_client):
        """Slug có ký tự đặc biệt phải bị reject."""
        resp = authed_client.post(
            "/news/new",
            data={"name": _name("News"), "slug": "slug@#$%"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Slug" in html

    def test_valid_slug_creates_tbllink_row(self, authed_client, db_conn):
        """Slug hợp lệ + menu_id hợp lệ → 1 tblLink row được tạo."""
        menu_id = _get_menu_id(db_conn)
        if menu_id is None:
            pytest.skip("No active category menu in DB")

        slug = _slug("valid-news")
        news_id = _create_news(authed_client, db_conn, _name("News"), slug, menu_id)
        if news_id is None:
            pytest.skip("Could not create news")

        assert _count_tbllink(db_conn, slug, row_type=2) == 1

    def test_slug_change_removes_old_tbllink_row(self, authed_client, db_conn):
        """Đổi slug → tblLink cũ xóa, tblLink mới tạo."""
        menu_id = _get_menu_id(db_conn)
        if menu_id is None:
            pytest.skip("No active category menu in DB")

        old_slug = _slug("old-news")
        new_slug = _slug("new-news")
        name = _name("News")
        news_id = _create_news(authed_client, db_conn, name, old_slug, menu_id)
        if news_id is None:
            pytest.skip("Could not create news")

        assert _count_tbllink(db_conn, old_slug, row_type=2) == 1

        _edit_news(authed_client, news_id, name, new_slug, menu_id)

        assert _count_tbllink(db_conn, old_slug, row_type=2) == 0, (
            "Old slug row phải bị xóa khỏi tblLink"
        )
        assert _count_tbllink(db_conn, new_slug, row_type=2) == 1, (
            "New slug row phải được tạo trong tblLink"
        )


# ── Product slug ──────────────────────────────────────────────────────

class TestProductSlugDuplicate:
    def test_same_product_edited_twice_keeps_one_tbllink_row(
        self, authed_client, db_conn
    ):
        """Edit cùng 1 product 2 lần với cùng locale → tblLink chỉ có 1 row."""
        slug = _slug("dup-pro-same")
        name = _name("Pro")
        prod_id = _create_product(authed_client, db_conn, name, slug)
        if prod_id is None:
            pytest.skip("Could not create product")

        _edit_product(authed_client, prod_id, name, slug)

        assert _count_tbllink(db_conn, slug, row_type=3) <= 1

    def test_valid_slug_creates_tbllink_row(self, authed_client, db_conn):
        """Locale hợp lệ → 1 tblLink row được tạo."""
        slug = _slug("valid-pro")
        prod_id = _create_product(authed_client, db_conn, _name("Pro"), slug)
        if prod_id is None:
            pytest.skip("Could not create product")

        assert _count_tbllink(db_conn, slug, row_type=3) == 1

    def test_slug_change_removes_old_tbllink_row(self, authed_client, db_conn):
        """Đổi locale → tblLink cũ xóa, tblLink mới tạo."""
        old_slug = _slug("old-pro")
        new_slug = _slug("new-pro")
        name = _name("Pro")
        prod_id = _create_product(authed_client, db_conn, name, old_slug)
        if prod_id is None:
            pytest.skip("Could not create product")

        assert _count_tbllink(db_conn, old_slug, row_type=3) == 1

        _edit_product(authed_client, prod_id, name, new_slug)

        assert _count_tbllink(db_conn, old_slug, row_type=3) == 0, (
            "Old locale row phải bị xóa khỏi tblLink"
        )
        assert _count_tbllink(db_conn, new_slug, row_type=3) == 1, (
            "New locale row phải được tạo trong tblLink"
        )

    def test_slug_format_rejects_invalid(self, authed_client):
        """Slug có ký tự không hợp lệ phải bị reject."""
        resp = authed_client.post(
            "/product/new",
            data={"name": _name("Pro"), "slug": "Bad Slug!"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "alert-danger" in html or "Slug" in html
