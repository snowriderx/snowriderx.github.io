"""
Advertc (tblAdvert Type=1) CRUD integration tests.
"""
import time
import pytest

from tests.integration.helpers import assert_flash_success, assert_no_flash_success

pytestmark = pytest.mark.integration


def _title():
    return f"[TEST] Advertc {int(time.time() * 1000)}"


def _create_advertc(authed_client, db_conn) -> "int | None":
    title = _title()
    authed_client.post(
        "/advertc/new",
        data={"title": title, "name": "test", "sort": "0"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "ID" FROM "tblAdvert" WHERE "Title" = %s', (title,)
    )
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestAdvertcList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/advertc/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_menu_filter_no_500(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDM" FROM "tblMenu" LIMIT 1')
        row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No menu rows in DB")
        resp = authed_client.get(f"/advertc/?menu_id={row[0]}")
        assert resp.status_code == 200


class TestAdvertcCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/advertc/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        title = _title()
        resp = authed_client.post(
            "/advertc/new",
            data={"title": title, "name": "test-code", "sort": "0"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "ID", "Title" FROM "tblAdvert" WHERE "Title" = %s',
            (title,),
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"Advertc '{title}' not found in DB"

    def test_create_missing_title_no_success(self, authed_client):
        resp = authed_client.post(
            "/advertc/new",
            data={"title": "", "name": ""},
            follow_redirects=True,
        )
        assert_no_flash_success(resp)


class TestAdvertcEdit:
    def test_edit_form_prefills(self, authed_client, db_conn):
        aid = _create_advertc(authed_client, db_conn)
        if aid is None:
            pytest.skip("Could not create test advertc")
        resp = authed_client.get(f"/advertc/{aid}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data

    def test_edit_saves_changes(self, authed_client, db_conn):
        aid = _create_advertc(authed_client, db_conn)
        if aid is None:
            pytest.skip("Could not create test advertc")

        new_title = _title() + " edited"
        resp = authed_client.post(
            f"/advertc/{aid}/edit",
            data={"title": new_title, "name": "edited", "sort": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Title" FROM "tblAdvert" WHERE "ID" = %s', (aid,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row and row[0] == new_title

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/advertc/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestAdvertcDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        aid = _create_advertc(authed_client, db_conn)
        if aid is None:
            pytest.skip("Could not create test advertc")

        resp = authed_client.post(
            f"/advertc/{aid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID" FROM "tblAdvert" WHERE "ID" = %s', (aid,))
        assert cur.fetchone() is None
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/advertc/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
