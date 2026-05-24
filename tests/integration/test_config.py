"""
Config (tblTotal) integration tests.
Singleton — chỉ có GET/POST /, không có create/delete.
Super-admin only (IDU=1).
"""
import pytest

pytestmark = pytest.mark.integration


class TestConfigPage:
    def test_config_renders(self, authed_client):
        resp = authed_client.get("/config/")
        # Super-admin only — may 403 if test user is not IDU=1, never 500
        assert resp.status_code in (200, 302, 403)

    def test_config_no_500(self, authed_client):
        resp = authed_client.get("/config/")
        assert resp.status_code != 500

    def test_config_post_no_500(self, authed_client):
        resp = authed_client.post(
            "/config/",
            data={"slogan": "Test Site", "script_head": ""},
            follow_redirects=True,
        )
        assert resp.status_code != 500
