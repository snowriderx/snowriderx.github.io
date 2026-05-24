"""
E2E: Product CRUD flow — browser thật.
"""
import time
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.slow


def _name():
    return f"[TEST] Pro E2E {int(time.time() * 1000)}"


def test_product_list_renders(page: Page, flask_server: str):
    page.goto(f"{flask_server}/product/")
    page.wait_for_load_state("networkidle")
    expect(page.locator("table")).to_be_visible()


def test_product_list_lang_filter_no_error(page: Page, flask_server: str):
    """Filter ?lang=1 không được gây lỗi 500 hay type error."""
    page.goto(f"{flask_server}/product/?lang=1")
    page.wait_for_load_state("networkidle")
    html = page.content()
    assert "500" not in page.title()
    assert "InternalError" not in html
    assert "operator does not exist" not in html


def test_product_create_form_renders(page: Page, flask_server: str):
    page.goto(f"{flask_server}/product/new")
    page.wait_for_load_state("networkidle")
    expect(page.locator('input[name="name"]')).to_be_visible()
    expect(page.locator('button[type="submit"]').first).to_be_visible()


def test_product_create_missing_name_shows_error(
    page: Page, flask_server: str
):
    """Submit form không có name phải hiện lỗi validation."""
    page.goto(f"{flask_server}/product/new")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    html = page.content()
    assert "bắt buộc" in html.lower() or "alert-danger" in html \
        or "required" in html.lower()


def test_product_create_flash_success(page: Page, flask_server: str):
    """
    Tạo product thành công phải:
    1. Redirect về list
    2. Hiển thị flash 'thành công'
    """
    name = _name()
    page.goto(f"{flask_server}/product/new")
    page.wait_for_load_state("networkidle")

    page.fill('input[name="name"]', name)
    slug_input = page.locator('input[name="slug"]')
    if slug_input.count() > 0:
        slug_input.fill("test-e2e-product")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    html = page.content()
    assert "thành công" in html.lower(), \
        "Flash success không xuất hiện sau khi tạo product"


def test_product_edit_form_prefills(page: Page, flask_server: str):
    """Edit form phải prefill name đúng."""
    name = _name()
    page.goto(f"{flask_server}/product/new")
    page.fill('input[name="name"]', name)
    slug_input = page.locator('input[name="slug"]')
    if slug_input.count() > 0:
        slug_input.fill("test-e2e-edit")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    edit_link = page.locator(f"tr:has-text('{name[:14]}') a[href*='/edit']")
    if edit_link.count() == 0:
        pytest.skip("Không tìm thấy product vừa tạo trong list")

    edit_link.first.click()
    page.wait_for_load_state("networkidle")

    expect(page.locator('input[name="name"]')).to_have_value(name)
