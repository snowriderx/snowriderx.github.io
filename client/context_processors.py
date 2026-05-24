import os
import time
from datetime import timezone, datetime

from flask import Flask
from sqlalchemy import select

from extensions import db
from models.menu import Menu
from models.product import Product
from models.config import get_site_config

_GAME_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "theme", "static", "game")
)

_VALID_GAME_FOLDERS: frozenset = frozenset()

# Cache for nav/footer menus and series list — changes rarely, TTL 5 minutes
_NAV_CACHE: dict = {}
_NAV_TTL = 300  # seconds

_CURRENT_YEAR = datetime.now(timezone.utc).year


def init_game_folder_cache() -> None:
    global _VALID_GAME_FOLDERS
    if os.path.isdir(_GAME_DIR):
        _VALID_GAME_FOLDERS = frozenset(
            d for d in os.listdir(_GAME_DIR)
            if os.path.isdir(os.path.join(_GAME_DIR, d))
        )


def _build_nav_data() -> dict:
    """Query menus + products for nav/footer/series. Cached for _NAV_TTL seconds."""
    now = time.monotonic()
    entry = _NAV_CACHE.get("nav")
    if entry and now < entry[1]:
        return entry[0]

    menus = db.session.execute(
        select(Menu)
        .where(Menu.is_active != 0, Menu.levels == 1, Menu.lang == 1)
        .order_by(Menu.sort_order.asc(), Menu.IDM.asc())
    ).scalars().all()

    navbar_items = [m for m in menus if m.tab_m and "-6-" in m.tab_m]
    footer_items = [m for m in menus if m.tab_m and "-8-" in m.tab_m]

    from client.theme_config import tc
    series_list = []
    game_thumbnails = []
    if tc.HAS_PRODUCTS:
        products = db.session.execute(
            select(Product)
            .where(Product.is_active == 1)
            .order_by(Product.ID.asc())
        ).scalars().all()
        for p in products:
            slug = p.locale or p.slug
            if not slug or slug not in _VALID_GAME_FOLDERS:
                continue
            url = "/" if p.ID == 1 else f"/{slug}"
            series_list.append({"name": p.name, "slug": slug})
            img = (
                f"/static/uploads/pro/{p.img}"
                if p.img and p.img != "null.gif"
                else ""
            )
            game_thumbnails.append({
                "url": url,
                "img": img,
                "alt": f"Play {p.name} online",
            })

    data = {
        "navbar_items": navbar_items,
        "footer_items": footer_items,
        "series_list": series_list,
        "game_thumbnails": game_thumbnails,
    }
    _NAV_CACHE["nav"] = (data, now + _NAV_TTL)
    return data


def register_context_processors(app: Flask) -> None:

    @app.context_processor
    def inject_site_globals():
        cfg = get_site_config()

        website_info: dict = {}
        if cfg and cfg.website_info:
            if isinstance(cfg.website_info, dict):
                website_info = cfg.website_info

        from client.theme_config import tc
        nav = _build_nav_data()

        return {
            "site_cfg": cfg,
            "website_info": website_info,
            "navbar_items": nav["navbar_items"],
            "footer_items": nav["footer_items"],
            "SITE_NAME": tc.SITE_NAME,
            "GAME_NAME": tc.GAME_NAME,
            "SCHEMA_TYPE": tc.SCHEMA_TYPE,
            "series_list": nav["series_list"],
            "game_thumbnails": nav["game_thumbnails"],
            "favicon_url": website_info.get("FileFavicon", ""),
            "logo_url": website_info.get("FileLogo", ""),
            "share_img_url": website_info.get("FileShare", ""),
            "script_verify": cfg.script_verify if cfg else "",
            "script_head": cfg.script_head if cfg else "",
            "script_body": cfg.script_body if cfg else "",
            "footer_html": cfg.footer if cfg else "",
            "now": _CURRENT_YEAR,
        }
