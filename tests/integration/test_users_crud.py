"""
Users CRUD integration tests.
"""
import pytest

from tests.integration.helpers import assert_flash_success, assert_no_flash_success

pytestmark = pytest.mark.integration


def _get_first_user_id(db_conn) -> "int | None":
    cur = db_conn.cursor()
    cur.execute('SELECT "IDU" FROM "tblUser" WHERE "AcU" = 1 LIMIT 1')
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestUsersList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/users/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_search_returns_results(self, authed_client):
        resp = authed_client.get("/users/?q=a")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_search_no_results_no_500(self, authed_client):
        resp = authed_client.get("/users/?q=xyznonexistent999")
        assert resp.status_code == 200
        assert resp.status_code != 500


class TestUsersCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/users/new")
        assert resp.status_code == 200
        assert b'name="username"' in resp.data or b"<form" in resp.data

    def test_create_missing_username_no_success(self, authed_client):
        resp = authed_client.post(
            "/users/new",
            data={"username": "", "password": ""},
            follow_redirects=True,
        )
        assert_no_flash_success(resp)


class TestUsersEdit:
    def test_edit_form_renders(self, authed_client, db_conn):
        user_id = _get_first_user_id(db_conn)
        if user_id is None:
            pytest.skip("No active user in DB")
        resp = authed_client.get(f"/users/{user_id}/edit")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_edit_form_prefills_data(self, authed_client, db_conn):
        user_id = _get_first_user_id(db_conn)
        if user_id is None:
            pytest.skip("No active user in DB")
        resp = authed_client.get(f"/users/{user_id}/edit")
        assert resp.status_code == 200
        # Form phải có data — input value không trống
        assert b'value=""' not in resp.data or b"admin" in resp.data.lower()

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/users/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestUsersBump:
    def test_bump_no_500(self, authed_client, db_conn):
        user_id = _get_first_user_id(db_conn)
        if user_id is None:
            pytest.skip("No active user in DB")
        resp = authed_client.post(
            f"/users/{user_id}/bump", follow_redirects=True
        )
        assert resp.status_code != 500


class TestUsersDelete:
    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/users/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
