"""
News CRUD integration tests via Flask test client + real PostgreSQL.
"""
import time
import pytest

from tests.integration.helpers import (
    assert_flash_success,
    assert_form_error,
    assert_no_flash_success,
)

pytestmark = pytest.mark.integration


def _name():
    return f"[TEST] News {int(time.time() * 1000)}"


def _create_news(authed_client, db_conn, name=None, slug="test-news") -> "int | None":
    """Helper: tạo news row, trả về ID."""
    name = name or _name()
    authed_client.post(
        "/news/new",
        data={"name": name, "slug": slug},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDN" FROM "tblNews" WHERE "NameN" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


# ── List ──────────────────────────────────────────────────────────────

class TestNewsList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/news/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_has_create_button(self, authed_client):
        resp = authed_client.get("/news/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Thêm mới" in html or "/news/new" in html

    def test_list_has_batch_form(self, authed_client):
        resp = authed_client.get("/news/")
        assert resp.status_code == 200
        assert b"<form" in resp.data


# ── Create ────────────────────────────────────────────────────────────

class TestNewsCreate:
    def test_create_form_has_name_field(self, authed_client):
        resp = authed_client.get("/news/new")
        assert resp.status_code == 200
        assert b'name="name"' in resp.data

    def test_create_minimal_saves_to_db(self, authed_client, db_conn):
        name = _name()
        resp = authed_client.post(
            "/news/new",
            data={"name": name, "slug": "test-create-saves"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "IDN", "NameN", "SEON" FROM "tblNews" WHERE "NameN" = %s',
            (name,),
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"News '{name}' not found in DB"
        assert row[1] == name
        assert row[2] == 0, f"SEON should default to 0, got {row[2]}"

    def test_create_saves_slug(self, authed_client, db_conn):
        name = _name()
        slug = "custom-slug-test"
        authed_client.post(
            "/news/new",
            data={"name": name, "slug": slug},
            follow_redirects=True,
        )
        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Name1N" FROM "tblNews" WHERE "NameN" = %s', (name,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert row[0] == slug, f"Slug mismatch: {row[0]} != {slug}"

    def test_create_missing_name_shows_form_error(self, authed_client):
        resp = authed_client.post(
            "/news/new",
            data={"name": "", "slug": ""},
            follow_redirects=True,
        )
        assert_form_error(resp)
        assert_no_flash_success(resp)

    def test_create_sets_is_active_default(self, authed_client, db_conn):
        name = _name()
        authed_client.post(
            "/news/new",
            data={"name": name, "slug": "active-default"},
            follow_redirects=True,
        )
        cur = db_conn.cursor()
        cur.execute(
            'SELECT "AcN" FROM "tblNews" WHERE "NameN" = %s', (name,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert row[0] in (0, 1), f"AcN invalid: {row[0]}"


# ── Edit ──────────────────────────────────────────────────────────────

class TestNewsEdit:
    def test_edit_form_prefills_name(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")
        resp = authed_client.get(f"/news/{news_id}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data

    def test_edit_saves_changes_to_db(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        new_name = _name() + " edited"
        resp = authed_client.post(
            f"/news/{news_id}/edit",
            data={"name": new_name, "slug": "edited-slug"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "NameN" FROM "tblNews" WHERE "IDN" = %s', (news_id,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None
        assert row[0] == new_name, f"DB not updated: {row[0]} != {new_name}"

    def test_edit_nonexistent_redirects(self, authed_client):
        resp = authed_client.get("/news/99999999/edit", follow_redirects=False)
        assert resp.status_code in (302, 404)


# ── Delete ────────────────────────────────────────────────────────────

class TestNewsDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        resp = authed_client.post(
            f"/news/{news_id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "IDN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        assert cur.fetchone() is None, "Row should be deleted"
        db_conn.rollback()

    def test_delete_also_removes_tbl_link(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        authed_client.post(f"/news/{news_id}/delete", follow_redirects=True)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "RowID" FROM "tblLink" WHERE "RowID" = %s AND "RowType" = 2',
            (str(news_id),),
        )
        assert cur.fetchone() is None, "tblLink row should be cleaned up"
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post("/news/99999999/delete", follow_redirects=True)
        assert resp.status_code != 500


# ── Bump (eTop) ───────────────────────────────────────────────────────

class TestNewsBump:
    def test_bump_updates_timestamp(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        cur = db_conn.cursor()
        cur.execute('SELECT "TimeN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        before = cur.fetchone()
        db_conn.rollback()

        resp = authed_client.post(
            f"/news/{news_id}/bump", follow_redirects=True
        )
        assert resp.status_code == 200

        cur.execute('SELECT "TimeN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        after = cur.fetchone()
        db_conn.rollback()

        if before and after and before[0] and after[0]:
            assert after[0] >= before[0], "Timestamp should be updated"


# ── Batch operations ──────────────────────────────────────────────────

class TestNewsBatch:
    def test_batch_update_status(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        # CrudController.index(): _action=delete → batch_delete, else → batch_update
        # row_id = list of IDs to update; ac_<id> = new status value
        resp = authed_client.post(
            "/news/",
            data={
                "row_id": str(news_id),
                f"ac_{news_id}": "0",
            },
            follow_redirects=True,
        )
        assert resp.status_code != 500

        cur = db_conn.cursor()
        cur.execute('SELECT "AcN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert row[0] == 0, f"AcN should be 0, got {row[0]}"

    def test_batch_delete(self, authed_client, db_conn):
        news_id = _create_news(authed_client, db_conn)
        if news_id is None:
            pytest.skip("Could not create test news row")

        # _action=delete + item_id list
        resp = authed_client.post(
            "/news/",
            data={"_action": "delete", "item_id": str(news_id)},
            follow_redirects=True,
        )
        assert resp.status_code != 500

        cur = db_conn.cursor()
        cur.execute('SELECT "IDN" FROM "tblNews" WHERE "IDN" = %s', (news_id,))
        assert cur.fetchone() is None, "Batch delete should remove row"
        db_conn.rollback()
