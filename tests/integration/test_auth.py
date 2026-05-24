"""
Auth integration tests — login form behavior.
"""
import pytest

pytestmark = pytest.mark.integration


def test_login_empty_credentials(client):
    resp = client.post("/login", data={"username": "", "password": ""})
    # Re-render form (400) or redirect back — never 500
    assert resp.status_code in (200, 302, 400)
    if resp.status_code == 200:
        assert b"<form" in resp.data


def test_login_wrong_password(client):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "wrong_password_xyz"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Must stay on login page or show error — never reach dashboard
    assert b"<form" in resp.data or b"login" in resp.data.lower()


def test_login_sql_injection_safe(client):
    """kill_chars strips injection chars; query must not crash."""
    resp = client.post(
        "/login",
        data={"username": "'; DROP TABLE tblUser; --", "password": "x"},
        follow_redirects=True,
    )
    # Must not 500
    assert resp.status_code != 500


def test_logout_redirects(client):
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code in (302, 301, 405)
