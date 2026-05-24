"""
Lang (tblLangM) CRUD integration tests.
Lang menu IDM là 6-char string tương tự tblMenu.
"""
import pytest

pytestmark = pytest.mark.integration


class TestLangList:
    def test_list_renders(self, authed_client):
        resp = authed_client.get("/lang/")
        assert resp.status_code == 200

    def test_list_no_500(self, authed_client):
        resp = authed_client.get("/lang/")
        assert resp.status_code != 500


class TestLangCreate:
    def test_create_form_renders(self, authed_client):
        resp = authed_client.get("/lang/new")
        assert resp.status_code == 200
        assert b"<form" in resp.data

    def test_create_no_500(self, authed_client):
        resp = authed_client.post(
            "/lang/new",
            data={"name": "[TEST] Lang item", "slug": "test-lang"},
            follow_redirects=True,
        )
        assert resp.status_code != 500


class TestLangEdit:
    def test_edit_nonexistent_no_500(self, authed_client):
        resp = authed_client.get(
            "/lang/ZZ9999/edit", follow_redirects=True
        )
        assert resp.status_code != 500


class TestLangDelete:
    def test_delete_nonexistent_no_500(self, authed_client):
        resp = authed_client.post(
            "/lang/ZZ9999/delete", follow_redirects=True
        )
        assert resp.status_code != 500
