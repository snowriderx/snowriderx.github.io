"""
Contact (tblContact) và Comment (tblComment) integration tests.
"""
import pytest

from tests.integration.helpers import assert_flash_success

pytestmark = pytest.mark.integration


class TestContactList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/contact/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_no_500(self, authed_client):
        resp = authed_client.get("/contact/")
        assert resp.status_code != 500


class TestContactDetail:
    def test_detail_existing_renders(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDC" FROM "tblContact" LIMIT 1')
        row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No contact rows in DB")
        resp = authed_client.get(f"/contact/{row[0]}")
        assert resp.status_code == 200
        # Detail page phải render content — không chỉ redirect
        assert b"<table" in resp.data or b"<div" in resp.data

    def test_detail_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/contact/99999999", follow_redirects=True
        )
        assert resp.status_code != 500


class TestContactDelete:
    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/contact/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500

    def test_delete_existing_removes_row(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDC" FROM "tblContact" LIMIT 1')
        row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No contact rows in DB to delete")
        cid = row[0]

        resp = authed_client.post(
            f"/contact/{cid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur.execute(
            'SELECT "IDC" FROM "tblContact" WHERE "IDC" = %s', (cid,)
        )
        assert cur.fetchone() is None
        db_conn.rollback()


class TestCommentList:
    def test_list_renders_table(self, authed_client):
        resp = authed_client.get("/comment/")
        assert resp.status_code == 200
        assert b"<table" in resp.data

    def test_list_no_500(self, authed_client):
        resp = authed_client.get("/comment/")
        assert resp.status_code != 500


class TestCommentEdit:
    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/comment/99999999/edit", follow_redirects=True
        )
        assert resp.status_code != 500

    def test_edit_existing_renders_form(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDC" FROM "tblComment" LIMIT 1')
        row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No comment rows in DB")
        resp = authed_client.get(f"/comment/{row[0]}/edit")
        assert resp.status_code == 200
        assert b"<form" in resp.data


class TestCommentDelete:
    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/comment/99999999/delete", follow_redirects=True
        )
        assert resp.status_code != 500

    def test_delete_existing_removes_row(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDC" FROM "tblComment" LIMIT 1')
        row = cur.fetchone()
        db_conn.rollback()
        if row is None:
            pytest.skip("No comment rows in DB to delete")
        cid = row[0]

        resp = authed_client.post(
            f"/comment/{cid}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert_flash_success(resp)

        cur.execute(
            'SELECT "IDC" FROM "tblComment" WHERE "IDC" = %s', (cid,)
        )
        assert cur.fetchone() is None
        db_conn.rollback()
