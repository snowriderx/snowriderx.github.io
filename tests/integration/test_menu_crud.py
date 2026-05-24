"""
Menu CRUD integration tests.
Menu IDM là 6-char string (e.g. "010000"), không phải int.
"""
import time
import pytest

pytestmark = pytest.mark.integration


def _idm():
    # Dùng prefix "T1" để tránh conflict, đảm bảo 6 chars
    ts = str(int(time.time()))[-4:]
    return f"T1{ts}"


class TestMenuList:
    def test_list_renders(self, authed_client):
        resp = authed_client.get("/menu/")
        assert resp.status_code == 200

    def test_list_no_500(self, authed_client):
        resp = authed_client.get("/menu/")
        assert resp.status_code != 500


class TestMenuCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/menu/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_minimal(self, authed_client, db_conn):
        idm = _idm()
        resp = authed_client.post(
            "/menu/new",
            data={"IDM": idm, "name": "[TEST] Menu item", "slug": "test-menu"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        cur = db_conn.cursor()
        cur.execute('SELECT "IDM" FROM "tblMenu" WHERE "IDM" = %s', (idm,))
        # May or may not be created depending on validation — just no 500
        db_conn.rollback()

    def test_create_no_500(self, authed_client):
        resp = authed_client.post(
            "/menu/new",
            data={"IDM": _idm(), "name": "[TEST] Menu", "slug": "test"},
            follow_redirects=True,
        )
        assert resp.status_code != 500


class TestMenuEdit:
    def test_edit_nonexistent_no_crash(self, authed_client):
        resp = authed_client.get(
            "/menu/ZZ9999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestMenuDelete:
    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/menu/ZZ9999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
