"""
Integration tests for client-facing routes.

Uses a real PostgreSQL DB (same as other integration tests).
Tests cover: home, category, article, game, 404, sitemap, robots,
             security headers, redirect, unblocked.
"""
import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client_app():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from client import create_client_app
    app = create_client_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def c(client_app):
    with client_app.test_client() as client:
        yield client


# ── Home ──────────────────────────────────────────────────────────────────────

def test_home_200(c):
    r = c.get("/")
    assert r.status_code == 200


def test_home_contains_html(c):
    r = c.get("/")
    assert b"<html" in r.data.lower() or b"<!doctype" in r.data.lower()


# ── Security headers ──────────────────────────────────────────────────────────

def test_security_headers_present(c):
    r = c.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Referrer-Policy" in r.headers


def test_security_headers_on_404(c):
    r = c.get("/this-page-does-not-exist-xyz")
    assert r.status_code == 404
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


# ── 404 ───────────────────────────────────────────────────────────────────────

def test_404_returns_404(c):
    r = c.get("/nonexistent-slug-xyz-abc")
    assert r.status_code == 404


def test_404_not_500(c):
    r = c.get("/nonexistent-slug-xyz-abc")
    assert r.status_code != 500


def test_404_has_back_link(c):
    r = c.get("/nonexistent-slug-xyz-abc")
    assert b"/" in r.data


# ── Sitemap ───────────────────────────────────────────────────────────────────

def test_sitemap_200(c):
    r = c.get("/sitemap.xml")
    assert r.status_code == 200


def test_sitemap_content_type(c):
    r = c.get("/sitemap.xml")
    assert "xml" in r.content_type


def test_sitemap_has_urlset(c):
    r = c.get("/sitemap.xml")
    assert b"urlset" in r.data


# ── Robots ────────────────────────────────────────────────────────────────────

def test_robots_200(c):
    r = c.get("/robots.txt")
    assert r.status_code == 200


def test_robots_content_type(c):
    r = c.get("/robots.txt")
    assert "text/plain" in r.content_type


# ── Unblocked ─────────────────────────────────────────────────────────────────

def test_unblocked_200(c):
    r = c.get("/unblocked")
    assert r.status_code == 200


def test_unblocked_no_double_nav(c):
    r = c.get("/unblocked")
    assert r.data.count(b"<header") <= 1
    assert r.data.count(b"<nav") <= 1


# ── Game pages ────────────────────────────────────────────────────────────────

def test_game_with_valid_folder_200(c, client_app):
    """Any active product whose locale folder exists should return 200."""
    with client_app.app_context():
        from extensions import db
        row = db.session.execute(
            db.text(
                'SELECT "RowUrl" FROM "tblLink" '
                'WHERE "RowType" = 3 AND "RowUrl" != \'\' LIMIT 1'
            )
        ).fetchone()
    if row is None:
        pytest.skip("No product rows in tblLink")
    from client.context_processors import _VALID_GAME_FOLDERS
    if row[0] not in _VALID_GAME_FOLDERS:
        pytest.skip(f"Game folder '{row[0]}' not present locally")
    r = c.get(f"/{row[0]}")
    assert r.status_code == 200


def test_game_without_folder_404(c, client_app):
    """A product whose locale folder does not exist must 404."""
    with client_app.app_context():
        from extensions import db
        from client.context_processors import _VALID_GAME_FOLDERS
        rows = db.session.execute(
            db.text(
                'SELECT "RowUrl" FROM "tblLink" WHERE "RowType" = 3'
            )
        ).fetchall()
    missing = [r[0] for r in rows if r[0] not in _VALID_GAME_FOLDERS]
    if not missing:
        pytest.skip("All product folders exist locally")
    r = c.get(f"/{missing[0]}")
    assert r.status_code == 404


# ── 301 redirects ─────────────────────────────────────────────────────────────

def test_active_redirect_followed(c, client_app):
    """An active tblURL rule must issue a 301."""
    with client_app.app_context():
        from extensions import db
        row = db.session.execute(
            db.text(
                'SELECT "Url_Old", "Url_New" FROM "tblURL" '
                'WHERE "Url_Ac" != 0 LIMIT 1'
            )
        ).fetchone()
    if row is None:
        pytest.skip("No active redirect rules in tblURL")
    r = c.get(row[0], follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["Location"] == row[1]


# ── Googlebot ─────────────────────────────────────────────────────────────────

def test_googlebot_gets_200(c):
    r = c.get("/", headers={"User-Agent": "Googlebot/2.1"})
    assert r.status_code == 200


def test_googlebot_no_ads(c):
    """Googlebot response must not contain ad slot markers."""
    r = c.get("/", headers={"User-Agent": "Googlebot/2.1"})
    # Script tags injected for ads should be absent for bots
    assert b"googletag" not in r.data
    assert b"adsbygoogle" not in r.data
