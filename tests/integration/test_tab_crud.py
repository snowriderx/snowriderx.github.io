"""
Tab (tblTab) CRUD integration tests.
"""
import time
import pytest

from tests.integration.helpers import assert_flash_success, assert_no_flash_success

pytestmark = pytest.mark.integration


def _name():
    return f"[TEST] Tab {int(time.time() * 1000)}"


def _create_tab(authed_client, db_conn) -> "int | None":
    name = _name()
    authed_client.post(
        "/tab/new",
        data={"name": name, "sort": "0", "tab_type": "1", "is_active": "1"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "ID" FROM "tblTab" WHERE "Name" = %s', (name,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestTabList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/tab/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_has_create_button(self, authed_client):
        html = authed_client.get("/tab/").data.decode("utf-8")
        assert "Thêm mới" in html or "/tab/new" in html


class TestTabCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/tab/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        name = _name()
        resp = authed_client.post(
            "/tab/new",
            data={"name": name, "sort": "0", "tab_type": "1", "is_active": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID", "Name" FROM "tblTab" WHERE "Name" = %s', (name,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"Tab '{name}' not found in DB"

        # Cleanup
        cur.execute('DELETE FROM "tblTab" WHERE "ID" = %s', (row[0],))
        db_conn.commit()

    def test_create_missing_name_no_success(self, authed_client):
        resp = authed_client.post(
            "/tab/new",
            data={"name": "", "sort": "0"},
            follow_redirects=True,
        )
        assert_no_flash_success(resp)


class TestTabEdit:
    def test_edit_form_prefills(self, authed_client, db_conn):
        tid = _create_tab(authed_client, db_conn)
        if tid is None:
            pytest.skip("Could not create test tab")
        resp = authed_client.get(f"/tab/{tid}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data
        # Cleanup
        cur = db_conn.cursor()
        cur.execute('DELETE FROM "tblTab" WHERE "ID" = %s', (tid,))
        db_conn.commit()

    def test_edit_saves_changes(self, authed_client, db_conn):
        tid = _create_tab(authed_client, db_conn)
        if tid is None:
            pytest.skip("Could not create test tab")

        new_name = _name() + " edited"
        resp = authed_client.post(
            f"/tab/{tid}/edit",
            data={"name": new_name, "sort": "1", "tab_type": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "Name" FROM "tblTab" WHERE "ID" = %s', (tid,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row and row[0] == new_name

        # Cleanup
        cur.execute('DELETE FROM "tblTab" WHERE "ID" = %s', (tid,))
        db_conn.commit()

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/tab/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestTabDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        tid = _create_tab(authed_client, db_conn)
        if tid is None:
            pytest.skip("Could not create test tab")

        resp = authed_client.post(f"/tab/{tid}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID" FROM "tblTab" WHERE "ID" = %s', (tid,))
        assert cur.fetchone() is None
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/tab/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
