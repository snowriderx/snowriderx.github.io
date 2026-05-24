"""
E2E test fixtures — spawn Flask server thật, dùng Playwright browser.
Server chạy suốt session, mỗi test dùng browser context riêng.
"""
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

PORT = int(os.environ.get("E2E_PORT", "5099"))
BASE_URL = f"http://127.0.0.1:{PORT}/admin"

# Đọc credentials từ .env hoặc fallback
E2E_USER = os.environ.get("E2E_USER", "admin")
E2E_PASS = os.environ.get("E2E_PASS", "")


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise TimeoutError(f"Server không start được trên port {port}")


@pytest.fixture(scope="session")
def flask_server():
    """Spawn Flask server một lần cho cả session."""
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    log = open(ROOT / "tests" / "e2e" / "server.log", "w")

    proc = subprocess.Popen(
        [sys.executable, "wsgi.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_port(PORT)
        yield BASE_URL
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture(scope="session")
def authed_state(flask_server: str, browser: Browser) -> str:
    """Login một lần, lưu cookie, tái dùng cho tất cả tests."""
    state_path = ROOT / "tests" / "e2e" / "auth_state.json"
    ctx = browser.new_context(base_url=flask_server)
    page = ctx.new_page()
    page.goto(f"{flask_server}/login")
    page.fill('input[name="username"]', E2E_USER)
    page.fill('input[name="password"]', E2E_PASS)
    page.click('button[type="submit"]')
    # Chờ redirect khỏi login
    page.wait_for_url(re.compile(r".*/(?!login).*"), timeout=5000)
    ctx.storage_state(path=str(state_path))
    ctx.close()
    return str(state_path)


@pytest.fixture
def page(browser: Browser, flask_server: str, authed_state: str) -> Page:
    """Per-test page với auth cookie đã load sẵn."""
    ctx = browser.new_context(
        base_url=flask_server,
        storage_state=authed_state,
    )
    p = ctx.new_page()
    yield p
    ctx.close()


@pytest.fixture
def anon_page(browser: Browser, flask_server: str) -> Page:
    """Per-test page không có auth — cho login tests."""
    ctx = browser.new_context(base_url=flask_server)
    p = ctx.new_page()
    yield p
    ctx.close()
