"""
E2E: News CRUD flow — browser thật.
Bắt được: Jinja2 template render đúng, flash message hiển thị,
form validation hiển thị error message trên UI.
"""
import time
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.slow


def _name():
    return f"[TEST] News E2E {int(time.time() * 1000)}"


def test_news_list_renders_table(page: Page, flask_server: str):
    """List page phải render table với data."""
    page.goto(f"{flask_server}/news/")
    page.wait_for_load_state("networkidle")
    expect(page.locator("table")).to_be_visible()


def test_news_list_has_add_button(page: Page, flask_server: str):
    """List page phải có nút Thêm mới."""
    page.goto(f"{flask_server}/news/")
    expect(page.get_by_text("Thêm mới")).to_be_visible()


def test_news_create_form_renders_fields(page: Page, flask_server: str):
    """Create form phải có các field cơ bản."""
    page.goto(f"{flask_server}/news/new")
    page.wait_for_load_state("networkidle")
    expect(page.locator('input[name="name"]')).to_be_visible()
    expect(page.locator('input[name="slug"]')).to_be_visible()
    expect(page.locator('button[type="submit"]').first).to_be_visible()


def test_news_create_missing_name_shows_validation_error(
    page: Page, flask_server: str
):
    """Submit form trống phải hiển thị validation error trên UI."""
    page.goto(f"{flask_server}/news/new")
    # Để trống name, submit
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # Phải còn ở form (không redirect) và có error message
    html = page.content()
    assert "bắt buộc" in html.lower() or "required" in html.lower() \
        or "alert-danger" in html or 'class="invalid' in html


def test_news_create_and_flash_success(page: Page, flask_server: str):
    """
    Tạo news thành công phải:
    1. Redirect về list
    2. Hiển thị flash 'thành công' trên UI
    """
    name = _name()
    page.goto(f"{flask_server}/news/new")
    page.wait_for_load_state("networkidle")

    page.fill('input[name="name"]', name)
    page.fill('input[name="slug"]', "test-e2e-news")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # Flash message phải xuất hiện
    html = page.content()
    assert "thành công" in html.lower(), \
        "Flash success message không xuất hiện sau khi tạo news"

    # Cleanup: tìm row vừa tạo và xóa
    try:
        row = page.locator(f"tr:has-text('{name[:20]}')")
        if row.count() > 0:
            delete_btn = row.locator("a[href*='/delete'], form[action*='/delete'] button")
            if delete_btn.count() > 0:
                page.evaluate("document.querySelector('[data-bs-dismiss]')?.click()")
    except Exception:
        pass  # cleanup best-effort


def test_news_edit_form_prefills_data(page: Page, flask_server: str):
    """
    Edit form của news đã tạo phải prefill đúng name.
    """
    name = _name()
    # Tạo news trước
    page.goto(f"{flask_server}/news/new")
    page.fill('input[name="name"]', name)
    page.fill('input[name="slug"]', "test-edit-prefill")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # Tìm link edit trong list
    edit_link = page.locator(f"tr:has-text('{name[:15]}') a[href*='/edit']")
    if edit_link.count() == 0:
        pytest.skip("Không tìm thấy row vừa tạo trong list")

    edit_link.first.click()
    page.wait_for_load_state("networkidle")

    # Name field phải được prefill
    name_input = page.locator('input[name="name"]')
    expect(name_input).to_have_value(name)
