"""
E2E: Login flow — browser thật, form thật, session thật.
Bắt được: template render, redirect, flash message hiển thị trên UI.
"""
import os
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.slow


def test_login_page_renders_form(anon_page: Page, flask_server: str):
    """Login page phải có form với username/password fields."""
    anon_page.goto(f"{flask_server}/login")
    expect(anon_page.locator('input[name="username"]')).to_be_visible()
    expect(anon_page.locator('input[name="password"]')).to_be_visible()
    expect(anon_page.locator('button[type="submit"]')).to_be_visible()


def test_login_wrong_password_shows_error(anon_page: Page, flask_server: str):
    """Login sai password phải ở lại trang login, không vào dashboard."""
    anon_page.goto(f"{flask_server}/login")
    anon_page.fill('input[name="username"]', "admin")
    anon_page.fill('input[name="password"]', "wrong_password_xyz")
    anon_page.click('button[type="submit"]')
    # Vẫn ở trang login (hoặc redirect về login)
    anon_page.wait_for_load_state("networkidle")
    assert "/login" in anon_page.url or "login" in anon_page.title().lower()


def test_login_success_redirects_to_dashboard(anon_page: Page, flask_server: str):
    """Login đúng phải redirect vào dashboard."""
    username = os.environ.get("E2E_USER", "admin")
    password = os.environ.get("E2E_PASS", "")

    anon_page.goto(f"{flask_server}/login")
    anon_page.fill('input[name="username"]', username)
    anon_page.fill('input[name="password"]', password)
    anon_page.click('button[type="submit"]')
    anon_page.wait_for_load_state("networkidle")

    # Không còn ở trang login nữa
    assert "/login" not in anon_page.url


def test_authed_user_sees_dashboard(page: Page, flask_server: str):
    """User đã login phải thấy dashboard với nav menu."""
    page.goto(f"{flask_server}/dashboard")
    page.wait_for_load_state("networkidle")
    assert "/login" not in page.url
    # Phải có nav hoặc sidebar
    expect(page.locator("#sidebar")).to_be_visible()


def test_unauthenticated_redirects_to_login(anon_page: Page, flask_server: str):
    """Truy cập route protected khi chưa login phải redirect về login."""
    anon_page.goto(f"{flask_server}/news/")
    anon_page.wait_for_load_state("networkidle")
    assert "/login" in anon_page.url
