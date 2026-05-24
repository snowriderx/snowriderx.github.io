import time

from flask import request
from sqlalchemy import select

from extensions import db
from models.menu import Menu
from models.banner import Advert


def is_googlebot() -> bool:
    """
    Replicates VB IsGoogleBot().
    Returns True for Googlebot / bot / lighthouse crawlers.
    Returns False for googleads / googlepartner (let ads show).
    """
    ua = (request.user_agent.string or "").lower()
    if any(kw in ua for kw in ("google", "bot", "lighthouse")):
        if any(exc in ua for exc in ("ads", "partner")):
            return False
        return True
    return False


def get_breadcrumb(idm: str) -> list[dict]:
    """
    Replicates VB LoadLinkN().
    Builds breadcrumb list from Home to current page based on IDM hierarchy.

    IDM encoding (zero-padded 6 chars):
      XX0000 → Level 1: [Home, this]
      XXYY00 → Level 2: [Home, parent(XX0000), this]
      XXYYZZ → Level 3: [Home, grandparent(XX0000), parent(XXYY00), this]
    """
    crumbs: list[dict] = [{"name": "Home", "url": "/"}]

    if not idm or len(idm) != 6:
        return crumbs

    if idm.endswith("0000"):
        idms_to_fetch = [idm]
    elif idm.endswith("00"):
        idms_to_fetch = [idm[:2] + "0000", idm]
    else:
        idms_to_fetch = [idm[:2] + "0000", idm[:4] + "00", idm]

    rows = db.session.execute(
        select(Menu.IDM, Menu.name, Menu.slug).where(Menu.IDM.in_(idms_to_fetch))
    ).all()

    by_idm = {r.IDM: r for r in rows}
    for key in idms_to_fetch:
        m = by_idm.get(key)
        if m:
            crumbs.append({"name": m.name, "url": f"/{m.slug}"})

    return crumbs


# ── Ads cache ─────────────────────────────────────────────────────────────────
# Keyed by (zone_type, menu_id, lang) → (html, expires_at)
_ADS_CACHE: dict = {}
_ADS_TTL = 60  # seconds


def get_ads_for_template(zone_type: int, menu_id: str = "000000", lang: int = 1) -> str:
    """
    Fetch HTML for a given ad zone — injected as Jinja2 global get_ads().
    Replicates VB LoadAdv2(). Results cached 60s to avoid per-slot DB queries.

    zone_type ints (from tblAdvert.Type):
      1=Slider, 2=Widget, 7=Quảng cáo, 8=Sidebar, 9=Footer, 96=Banner, ...
    """
    key = (zone_type, menu_id, lang)
    entry = _ADS_CACHE.get(key)
    now = time.monotonic()
    if entry and now < entry[1]:
        return entry[0]

    rows = db.session.execute(
        select(Advert.html)
        .where(
            Advert.zone_type == zone_type,
            Advert.is_active != 0,
            Advert.menu_id == menu_id,
            Advert.lang == lang,
        )
        .order_by(Advert.sort.asc())
    ).scalars().all()
    html = "".join(r or "" for r in rows)
    _ADS_CACHE[key] = (html, now + _ADS_TTL)
    return html
