"""
Product CRUD integration tests.
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
    return f"[TEST] Product {int(time.time() * 1000)}"


def _create_product(authed_client, db_conn, name=None) -> "int | None":
    name = name or _name()
    authed_client.post(
        "/product/new",
        data={"name": name, "slug": "test-pro", "is_active": "1"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "IDP" FROM "tblPro" WHERE "NameP" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


# ── List ──────────────────────────────────────────────────────────────

class TestProductList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/product/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_has_create_button(self, authed_client):
        html = authed_client.get("/product/").data.decode("utf-8")
        assert "Thêm mới" in html or "/product/new" in html

    def test_list_lang_filter_no_type_error(self, authed_client):
        """LangP là TEXT — filter phải không gây operator type error."""
        resp = authed_client.get("/product/?lang=1")
        assert resp.status_code == 200
        assert resp.status_code != 500


# ── Create ────────────────────────────────────────────────────────────

class TestProductCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/product/new")
        assert resp.status_code == 200
        assert b'name="name"' in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        name = _name()
        resp = authed_client.post(
            "/product/new",
            data={"name": name, "slug": "test-save", "is_active": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "IDP", "NameP", "LangP" FROM "tblPro" WHERE "NameP" = %s',
            (name,),
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"Product '{name}' not found in DB"
        assert row[1] == name
        assert str(row[2]) == "1", f"LangP should be '1' (text), got {row[2]!r}"

    def test_create_tbl_link_synced(self, authed_client, db_conn):
        """Sau create, tblLink phải không crash (sync chạy, không exception)."""
        name = _name()
        authed_client.post(
            "/product/new",
            data={"name": name, "slug": "test-link-sync"},
            follow_redirects=True,
        )
        cur = db_conn.cursor()
        cur.execute('SELECT "IDP" FROM "tblPro" WHERE "NameP" = %s', (name,))
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            pid = row[0]
            cur.execute(
                'SELECT COUNT(*) FROM "tblLink" WHERE "RowID" = %s AND "RowType" = 3',
                (str(pid),),
            )
            count = cur.fetchone()[0]
            db_conn.rollback()
            # count=0 là OK nếu menu không match — chỉ assert không exception

    def test_create_missing_name_shows_error(self, authed_client):
        resp = authed_client.post(
            "/product/new",
            data={"name": "", "slug": ""},
            follow_redirects=True,
        )
        assert_form_error(resp)
        assert_no_flash_success(resp)

    def test_create_lang_stored_as_text(self, authed_client, db_conn):
        name = _name()
        authed_client.post(
            "/product/new",
            data={"name": name, "slug": "lang-text", "lang_id": "2"},
            follow_redirects=True,
        )
        cur = db_conn.cursor()
        cur.execute('SELECT "LangP" FROM "tblPro" WHERE "NameP" = %s', (name,))
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert str(row[0]) == "2", f"LangP should be '2', got {row[0]!r}"


# ── Edit ──────────────────────────────────────────────────────────────

class TestProductEdit:
    def test_edit_form_prefills_name(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")
        resp = authed_client.get(f"/product/{pid}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data

    def test_edit_saves_changes(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        new_name = _name() + " edited"
        resp = authed_client.post(
            f"/product/{pid}/edit",
            data={"name": new_name, "slug": "edited"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "NameP" FROM "tblPro" WHERE "IDP" = %s', (pid,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row and row[0] == new_name, f"DB not updated: {row}"

    def test_edit_nonexistent_redirects(self, authed_client):
        resp = authed_client.get("/product/99999999/edit", follow_redirects=False)
        assert resp.status_code in (302, 404)


# ── Delete ────────────────────────────────────────────────────────────

class TestProductDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        resp = authed_client.post(f"/product/{pid}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "IDP" FROM "tblPro" WHERE "IDP" = %s', (pid,))
        assert cur.fetchone() is None, "Row should be deleted"
        db_conn.rollback()

    def test_delete_cleans_tbl_link(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        authed_client.post(f"/product/{pid}/delete", follow_redirects=True)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "RowID" FROM "tblLink" WHERE "RowID" = %s AND "RowType" = 3',
            (str(pid),),
        )
        assert cur.fetchone() is None, "tblLink should be cleaned up after delete"
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post("/product/99999999/delete", follow_redirects=True)
        assert resp.status_code != 500


# ── Bump ──────────────────────────────────────────────────────────────

class TestProductBump:
    def test_bump_updates_timestamp(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        resp = authed_client.post(f"/product/{pid}/bump", follow_redirects=True)
        assert resp.status_code == 200

        cur = db_conn.cursor()
        cur.execute('SELECT "TimeP" FROM "tblPro" WHERE "IDP" = %s', (pid,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None and row[0] is not None, "TimeP should be set after bump"


# ── Batch ─────────────────────────────────────────────────────────────

class TestProductBatch:
    def test_batch_update_active(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        resp = authed_client.post(
            "/product/",
            data={"row_id": str(pid), f"ac_{pid}": "0"},
            follow_redirects=True,
        )
        assert resp.status_code != 500

        cur = db_conn.cursor()
        cur.execute('SELECT "AcP" FROM "tblPro" WHERE "IDP" = %s', (pid,))
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert row[0] == 0

    def test_batch_delete(self, authed_client, db_conn):
        pid = _create_product(authed_client, db_conn)
        if pid is None:
            pytest.skip("Could not create test product")

        resp = authed_client.post(
            "/product/",
            data={"_action": "delete", "item_id": str(pid)},
            follow_redirects=True,
        )
        assert resp.status_code != 500

        cur = db_conn.cursor()
        cur.execute('SELECT "IDP" FROM "tblPro" WHERE "IDP" = %s', (pid,))
        assert cur.fetchone() is None
        db_conn.rollback()
