"""
Permissions integration tests.
"""
import pytest

pytestmark = pytest.mark.integration


class TestPermissions:
    def test_permissions_page_no_500(self, authed_client):
        resp = authed_client.get("/permissions/", follow_redirects=True)
        assert resp.status_code != 500

    def test_permissions_post_no_500(self, authed_client, db_conn):
        cur = db_conn.cursor()
        cur.execute('SELECT "IDU" FROM "tblUser" WHERE "AcU" = 1 LIMIT 1')
        row = cur.fetchone()
        if row is None:
            pytest.skip("No active user in DB")
        user_id = row[0]
        resp = authed_client.post(
            "/permissions/",
            data={f"perm_{user_id}_menu": "1"},
            follow_redirects=True,
        )
        assert resp.status_code != 500
