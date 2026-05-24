"""
Smoke tests — verify core pages respond without 500 errors.
Uses anonymous client (no login) — expects 302 redirect to login.
"""
import pytest

pytestmark = pytest.mark.integration


PROTECTED_ROUTES = [
    "/",
    "/dashboard",
    "/news/",
    "/product/",
    "/menu/",
    "/users/",
    "/banner/",
    "/config/",
]


@pytest.mark.parametrize("path", PROTECTED_ROUTES)
def test_protected_route_redirects_to_login(client, path):
    """Unauthenticated requests must redirect, not 500."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (302, 301), (
        f"{path} returned {resp.status_code} — expected redirect to login"
    )


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_404_handled(client):
    resp = client.get("/nonexistent-route-xyz")
    assert resp.status_code == 404
