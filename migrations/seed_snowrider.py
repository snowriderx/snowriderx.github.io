"""
Seed script for Snow Rider X — parses static HTML from snowridex_old/
and populates tblMenu, tblNews, tblLink, tblTotal.

Usage:
    cd /opt/snowriderx
    .venv/bin/python migrations/seed_snowrider.py

Idempotent: checks existence before inserting.
"""
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from bs4 import BeautifulSoup

# ── path to static HTML source ────────────────────────────────────────────────
# On local dev: sibling folder snowridex_old
# On server: pass env var SNOW_SRC or place source at /tmp/snowridex_old
SNOW_SRC = Path(os.getenv("SNOW_SRC", ROOT.parent / "snowridex_old"))
if not SNOW_SRC.exists():
    print(f"ERROR: SNOW_SRC not found at {SNOW_SRC}")
    print("Set env var SNOW_SRC=/path/to/snowridex_old and re-run.")
    sys.exit(1)

from app_setup import get_db_conn

conn = get_db_conn()
cur = conn.cursor()
now = datetime.now(timezone.utc)


def _exists(table, col, val):
    cur.execute(f'SELECT 1 FROM "{table}" WHERE "{col}" = %s LIMIT 1', (val,))
    return cur.fetchone() is not None


def _parse_html(path: Path):
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _get_meta(soup, name):
    tag = soup.find("meta", attrs={"name": name}) or \
          soup.find("meta", attrs={"property": f"og:{name}"}) or \
          soup.find("meta", attrs={"property": name})
    return (tag.get("content") or "").strip() if tag else ""


def _get_title(soup):
    t = soup.find("title")
    return t.get_text(strip=True) if t else ""


def _get_content(soup):
    section = soup.find("div", class_="content-section")
    return str(section) if section else ""


def _get_img(soup):
    section = soup.find("div", class_="content-section")
    if section:
        img = section.find("img")
        if img and img.get("src"):
            return Path(img["src"]).name
    return ""


# ── 1. tblTotal — site config ─────────────────────────────────────────────────
print("Seeding tblTotal...")
if not _exists("tblTotal", "IDT", 1):
    index_soup = _parse_html(SNOW_SRC / "index.html")
    desc = _get_meta(index_soup, "description") or \
           _get_meta(index_soup, "og:description")
    cur.execute(
        '''INSERT INTO "tblTotal"
           ("IDT", "TitleT", "DescrT", "KeyT", "AcT", "WebsiteInfo")
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (
            1,
            "Snow Rider X",
            desc,
            "snow rider 3d, snow rider, browser game, unblocked",
            1,
            '{"FileLogo": "/static/uploads/icon/logo.jpg", '
            '"FileFavicon": "/static/uploads/icon/favicon.png", '
            '"FileShare": "/static/uploads/icon/logo.jpg"}',
        )
    )
    print("  inserted tblTotal row 1")
else:
    print("  tblTotal row 1 already exists, skipping")


# ── 2. tblMenu + tblLink — navigation pages ───────────────────────────────────
print("Seeding tblMenu + tblLink...")

PAGES = [
    # (IDM,     slug,          name,                   tab_m,  type_m, html_file)
    ("010000", "how-to-play",  "How To Play",          "-6-",  0,      "How-to-play.html"),
    ("020000", "faq",          "FAQ",                  "-6-",  0,      "faq.html"),
    ("030000", "blog",         "Blog",                 "-6-",  1,      "blog.html"),
    ("040000", "about",        "About Us",             "-6-",  0,      "about.html"),
    ("050000", "contact",      "Contact",              "-6-",  0,      "contact.html"),
    ("060000", "privacy",      "Privacy Policy",       "-8-",  0,      "privacy.html"),
    ("070000", "terms",        "Terms and Conditions", "-8-",  0,      "terms.html"),
]

for idm, slug, name, tab_m, type_m, html_file in PAGES:
    if not _exists("tblMenu", "IDM", idm):
        soup = _parse_html(SNOW_SRC / html_file)
        title = _get_title(soup) or name
        desc  = _get_meta(soup, "description") or _get_meta(soup, "og:description")
        cur.execute(
            '''INSERT INTO "tblMenu"
               ("IDM", "NameM", "Name1M", "TitleM", "DescrM",
                "AcM", "levels", "tab_m", "TypeM", "lang", "sort_order")
               VALUES (%s, %s, %s, %s, %s, 1, 1, %s, %s, 1, %s)''',
            (idm, name, slug, title, desc, tab_m, type_m, int(idm[:2]))
        )
        print(f"  inserted tblMenu {idm} {slug}")
    else:
        print(f"  tblMenu {idm} already exists, skipping")

    if not _exists("tblLink", "RowUrl", slug):
        row_type = 1 if type_m == 1 else 0
        cur.execute(
            '''INSERT INTO "tblLink" ("RowUrl", "row_type", "IDM", "AcL")
               VALUES (%s, %s, %s, 1)''',
            (slug, row_type, idm)
        )
        print(f"  inserted tblLink {slug}")


# ── 3. tblNews + tblLink — blog articles ──────────────────────────────────────
print("Seeding tblNews + tblLink (blog articles)...")

BLOG_DIR = SNOW_SRC / "blog"
BLOG_MENU_IDM = "030000"

for html_path in sorted(BLOG_DIR.glob("*.html")):
    slug = html_path.stem  # e.g. "history-of-snow-rider-3d"
    soup = _parse_html(html_path)

    title   = _get_title(soup).strip(" \t\n")
    desc    = _get_meta(soup, "description") or _get_meta(soup, "og:description")
    content = _get_content(soup)
    img     = _get_img(soup)

    if not title:
        print(f"  SKIP {slug} — no title")
        continue

    if not _exists("tblNews", "Name1N", slug):
        cur.execute(
            '''INSERT INTO "tblNews"
               ("NameN", "Name1N", "MenuIDN", "TitleN", "DecripN",
                "DescN", "ImgN", "AcN", "TypeN", "SEON", "TimeN", "TimeUpN")
               VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, 1, %s, %s)''',
            (title, slug, BLOG_MENU_IDM, title, desc,
             content, img, now, now)
        )
        print(f"  inserted tblNews {slug}")
    else:
        print(f"  tblNews {slug} already exists, skipping")

    if not _exists("tblLink", "RowUrl", slug):
        cur.execute(
            '''INSERT INTO "tblLink" ("RowUrl", "row_type", "AcL")
               VALUES (%s, 2, 1)''',
            (slug,)
        )
        print(f"  inserted tblLink {slug}")


conn.commit()
cur.close()
conn.close()
print("\nDone. All rows seeded.")
