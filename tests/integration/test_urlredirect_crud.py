"""
URL Redirect (tblURL) CRUD integration tests.
"""
import time
import pytest

from tests.integration.helpers import assert_flash_success, assert_no_flash_success

pytestmark = pytest.mark.integration


def _old_url():
    return f"/test-{int(time.time() * 1000)}-old"


def _create_redirect(authed_client, db_conn) -> "int | None":
    old = _old_url()
    authed_client.post(
        "/urlredirect/new",
        data={"old_url": old, "new_url": "/new-dest", "is_active": "1"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "Url_ID" FROM "tblURL" WHERE "Url_Old" = %s', (old,)
    )
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestUrlRedirectList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/urlredirect/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_has_create_button(self, authed_client):
        html = authed_client.get("/urlredirect/").data.decode("utf-8")
        assert "Thêm mới" in html or "/urlredirect/new" in html


class TestUrlRedirectCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/urlredirect/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        old = _old_url()
        resp = authed_client.post(
            "/urlredirect/new",
            data={"old_url": old, "new_url": "/new-dest", "is_active": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Url_ID", "Url_Old" FROM "tblURL" WHERE "Url_Old" = %s',
            (old,),
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"Redirect '{old}' not found in DB"

        # Cleanup
        cur.execute('DELETE FROM "tblURL" WHERE "Url_Old" = %s', (old,))
        db_conn.commit()

    def test_create_missing_url_no_success(self, authed_client):
        resp = authed_client.post(
            "/urlredirect/new",
            data={"old_url": "", "new_url": ""},
            follow_redirects=True,
        )
        assert_no_flash_success(resp)


class TestUrlRedirectEdit:
    def test_edit_form_prefills(self, authed_client, db_conn):
        rid = _create_redirect(authed_client, db_conn)
        if rid is None:
            pytest.skip("Could not create test redirect")
        resp = authed_client.get(f"/urlredirect/{rid}/edit")
        assert resp.status_code == 200
        assert b"<form" in resp.data
        # Cleanup
        cur = db_conn.cursor()
        cur.execute('DELETE FROM "tblURL" WHERE "Url_ID" = %s', (rid,))
        db_conn.commit()

    def test_edit_saves_changes(self, authed_client, db_conn):
        rid = _create_redirect(authed_client, db_conn)
        if rid is None:
            pytest.skip("Could not create test redirect")

        resp = authed_client.post(
            f"/urlredirect/{rid}/edit",
            data={
                "old_url": "/test-edited-old",
                "new_url": "/edited-dest",
                "is_active": "1",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Url_Old" FROM "tblURL" WHERE "Url_ID" = %s', (rid,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        if row:
            assert row[0] == "/test-edited-old"
        # Cleanup
        cur.execute('DELETE FROM "tblURL" WHERE "Url_ID" = %s', (rid,))
        db_conn.commit()

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/urlredirect/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestUrlRedirectDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        rid = _create_redirect(authed_client, db_conn)
        if rid is None:
            pytest.skip("Could not create test redirect")

        resp = authed_client.post(
            f"/urlredirect/{rid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "Url_ID" FROM "tblURL" WHERE "Url_ID" = %s', (rid,))
        assert cur.fetchone() is None
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/urlredirect/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
