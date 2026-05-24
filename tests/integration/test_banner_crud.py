"""
Banner (tblAdvert) CRUD integration tests.
"""
import time
import pytest

from tests.integration.helpers import (
    assert_flash_success,
    assert_form_error,
    assert_no_flash_success,
)

pytestmark = pytest.mark.integration


def _title():
    return f"[TEST] Banner {int(time.time() * 1000)}"


def _create_banner(authed_client, db_conn, title=None) -> "int | None":
    title = title or _title()
    authed_client.post(
        "/banner/new",
        data={"title": title, "name": "test", "sort": "0"},
        follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "ID" FROM "tblAdvert" WHERE "Title" = %s', (title,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestBannerList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/banner/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_has_create_button(self, authed_client):
        html = authed_client.get("/banner/").data.decode("utf-8")
        assert "Thêm mới" in html or "/banner/new" in html


class TestBannerCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/banner/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        title = _title()
        resp = authed_client.post(
            "/banner/new",
            data={"title": title, "name": "test-banner", "sort": "0"},
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
        assert row is not None, f"Banner '{title}' not found in DB"

    def test_create_missing_title_shows_error(self, authed_client):
        resp = authed_client.post(
            "/banner/new",
            data={"title": "", "name": ""},
            follow_redirects=True,
        )
        # validation fail → no success flash
        assert_no_flash_success(resp)


class TestBannerEdit:
    def test_edit_form_prefills_title(self, authed_client, db_conn):
        bid = _create_banner(authed_client, db_conn)
        if bid is None:
            pytest.skip("Could not create test banner")
        resp = authed_client.get(f"/banner/{bid}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data

    def test_edit_saves_changes(self, authed_client, db_conn):
        bid = _create_banner(authed_client, db_conn)
        if bid is None:
            pytest.skip("Could not create test banner")

        new_title = _title() + " edited"
        resp = authed_client.post(
            f"/banner/{bid}/edit",
            data={"title": new_title, "name": "edited", "sort": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute(
            'SELECT "Title" FROM "tblAdvert" WHERE "ID" = %s', (bid,)
        )
        row = cur.fetchone()
        db_conn.rollback()
        assert row and row[0] == new_title

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/banner/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestBannerDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        bid = _create_banner(authed_client, db_conn)
        if bid is None:
            pytest.skip("Could not create test banner")

        resp = authed_client.post(
            f"/banner/{bid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID" FROM "tblAdvert" WHERE "ID" = %s', (bid,))
        assert cur.fetchone() is None
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/banner/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
