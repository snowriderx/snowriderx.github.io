"""
Permission matrix integration tests.

VB pattern: If Val(Decrypt(cookie)) <> 1 Then Response.Redirect("news.aspx")
Flask equivalent: super_admin_redirect() returns redirect to news.index for IDU≠1.

Tests:
- Super-admin (IDU=1) có thể truy cập tất cả super-admin-only blueprints
- Regular admin (IDU≠1) bị redirect ra khỏi super-admin-only blueprints
- Regular admin vẫn vào được /news/ (không phải super-admin-only)
- Unauthenticated user bị redirect về /login
"""
import pytest

pytestmark = pytest.mark.integration

# Các URL thuộc super-admin-only (có super_admin_redirect() trong before_request)
SUPER_ADMIN_ONLY_URLS = [
    "/dashboard",
    "/product/",
    "/menu/",
    "/banner/",
    "/advertc/",
    "/config/",
    "/comment/",
    "/contact/",
]

# Các URL regular admin có thể vào
REGULAR_ADMIN_URLS = [
    "/news/",
]


# ── Fixture: client đăng nhập với user IDU≠1 ─────────────────────────

@pytest.fixture
def regular_admin_client(_flask_app, db_conn):
    """
    Test client đăng nhập với regular admin (IDU≠1, AcU=1).
    Nếu không có user IDU≠1 active trong DB → skip.
    """
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "IDU" FROM "tblUser" WHERE "IDU" != 1 AND "AcU" = 1 LIMIT 1'
    )
    row = cur.fetchone()
    db_conn.rollback()
    if row is None:
        pytest.skip("No regular admin user (IDU≠1, AcU=1) in DB")

    user_id = row[0]
    with _flask_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True
        yield c


# ── Super-admin access ────────────────────────────────────────────────

class TestSuperAdminAccess:
    @pytest.mark.parametrize("url", SUPER_ADMIN_ONLY_URLS)
    def test_super_admin_can_access(self, authed_client, url):
        """IDU=1 phải vào được tất cả super-admin-only pages."""
        resp = authed_client.get(url, follow_redirects=False)
        # 200 = trực tiếp; 302 về chính nó (e.g. pagination) cũng OK
        # Điều quan trọng: KHÔNG redirect về /news/
        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            assert "/news/" not in location and "news" not in location, (
                f"{url}: super-admin bị redirect về news ({location})"
            )
        else:
            assert resp.status_code == 200, (
                f"{url}: expected 200, got {resp.status_code}"
            )

    def test_super_admin_can_access_news(self, authed_client):
        resp = authed_client.get("/news/")
        assert resp.status_code == 200


# ── Regular admin access ──────────────────────────────────────────────

class TestRegularAdminBlocked:
    @pytest.mark.parametrize("url", SUPER_ADMIN_ONLY_URLS)
    def test_regular_admin_redirected_from_super_admin_only(
        self, regular_admin_client, url
    ):
        """IDU≠1 phải bị redirect ra khỏi super-admin-only pages."""
        resp = regular_admin_client.get(url, follow_redirects=False)
        assert resp.status_code == 302, (
            f"{url}: expected redirect (302), got {resp.status_code}"
        )
        location = resp.headers.get("Location", "")
        # Redirect phải về /news/ (không phải /login/)
        assert "/news/" in location or "news" in location, (
            f"{url}: expected redirect to /news/, got {location!r}"
        )

    def test_regular_admin_can_access_news(self, regular_admin_client):
        """Regular admin vào /news/ phải được 200."""
        resp = regular_admin_client.get("/news/")
        assert resp.status_code == 200

    def test_regular_admin_redirected_from_dashboard(
        self, regular_admin_client
    ):
        resp = regular_admin_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "news" in location


# ── Unauthenticated access ────────────────────────────────────────────

class TestUnauthenticatedBlocked:
    @pytest.mark.parametrize("url", SUPER_ADMIN_ONLY_URLS + REGULAR_ADMIN_URLS)
    def test_unauthenticated_redirected_to_login(self, client, url):
        """Chưa login phải redirect về /login."""
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code in (302, 308), (
            f"{url}: expected redirect, got {resp.status_code}"
        )
        location = resp.headers.get("Location", "")
        assert "login" in location, (
            f"{url}: expected redirect to /login, got {location!r}"
        )
