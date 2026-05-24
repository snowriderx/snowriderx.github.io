"""
Tag CRUD integration tests — 3 sections: news, menu, website.
"""
import time
import pytest

from tests.integration.helpers import assert_flash_success, assert_no_flash_success

pytestmark = pytest.mark.integration

SECTIONS = ["news", "menu", "website"]


def _title():
    return f"[TEST] Tag {int(time.time() * 1000)}"


def _get_news_id(db_conn) -> "str | None":
    cur = db_conn.cursor()
    cur.execute('SELECT "IDN" FROM "tblNews" LIMIT 1')
    row = cur.fetchone()
    db_conn.rollback()
    return str(row[0]) if row else None


def _create_tag(authed_client, db_conn, section="news") -> "int | None":
    title = _title()
    data = {"title": title, "sort": "0"}
    if section == "news":
        news_id = _get_news_id(db_conn)
        if news_id:
            data["owner_id"] = news_id
    elif section == "menu":
        data["owner_id"] = "010000"
    # website: owner_id không cần (hardcoded "0")
    authed_client.post(
        f"/tag/{section}/new", data=data, follow_redirects=True,
    )
    cur = db_conn.cursor()
    cur.execute('SELECT "ID" FROM "tblTag" WHERE "Title" = %s', (title,))
    row = cur.fetchone()
    db_conn.rollback()
    return row[0] if row else None


class TestTagList:
    @pytest.mark.parametrize("section", SECTIONS)
    def test_list_renders_table(self, authed_client, section):
        resp = authed_client.get(f"/tag/{section}/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_invalid_section_no_500(self, authed_client):
        resp = authed_client.get("/tag/invalid/", follow_redirects=True)
        assert resp.status_code != 500


class TestTagCreate:
    @pytest.mark.parametrize("section", SECTIONS)
    def test_create_form_renders(self, authed_client, section):
        resp = authed_client.get(f"/tag/{section}/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_saves_to_db(self, authed_client, db_conn):
        news_id = _get_news_id(db_conn)
        if news_id is None:
            pytest.skip("No news rows in DB for tag owner")
        title = _title()
        resp = authed_client.post(
            "/tag/news/new",
            data={"title": title, "sort": "0", "owner_id": news_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID", "Title" FROM "tblTag" WHERE "Title" = %s', (title,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row is not None, f"Tag '{title}' not found in DB"

    def test_create_missing_title_no_success(self, authed_client):
        resp = authed_client.post(
            "/tag/news/new",
            data={"title": "", "sort": "0"},
            follow_redirects=True,
        )
        assert_no_flash_success(resp)


class TestTagEdit:
    def test_edit_form_prefills_title(self, authed_client, db_conn):
        tid = _create_tag(authed_client, db_conn, "news")
        if tid is None:
            pytest.skip("Could not create test tag")
        resp = authed_client.get(f"/tag/news/{tid}/edit")
        assert resp.status_code == 200
        assert b"[TEST]" in resp.data

    def test_edit_saves_changes(self, authed_client, db_conn):
        tid = _create_tag(authed_client, db_conn, "news")
        if tid is None:
            pytest.skip("Could not create test tag")

        new_title = _title() + " edited"
        resp = authed_client.post(
            f"/tag/news/{tid}/edit",
            data={"title": new_title, "sort": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "Title" FROM "tblTag" WHERE "ID" = %s', (tid,))
        row = cur.fetchone()
        db_conn.rollback()
        assert row and row[0] == new_title

    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/tag/news/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestTagDelete:
    def test_delete_removes_from_db(self, authed_client, db_conn):
        tid = _create_tag(authed_client, db_conn, "news")
        if tid is None:
            pytest.skip("Could not create test tag")

        resp = authed_client.post(
            f"/tag/news/{tid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur = db_conn.cursor()
        cur.execute('SELECT "ID" FROM "tblTag" WHERE "ID" = %s', (tid,))
        assert cur.fetchone() is None
        db_conn.rollback()

    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/tag/news/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
