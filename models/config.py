import time

from extensions import db


class SiteConfig(db.Model):
    """
    Singleton website configuration.
    VB: tblTotal — always read/written as ID=1.
    """

    __tablename__ = "tblTotal"

    ID               = db.Column(db.Integer, primary_key=True, name="ID")
    total            = db.Column(db.Integer, nullable=True, name="Total")
    lang             = db.Column(db.Integer, nullable=True, default=1, name="Lang")

    # ── Contact ──────────────────────────────────────────────────────
    email            = db.Column(db.Unicode(100), nullable=True, name="Email")
    hotline          = db.Column(db.Unicode(50),  nullable=True, name="Hotline")
    slogan           = db.Column(db.Unicode(200), nullable=True, name="Slogan")

    # ── SEO ──────────────────────────────────────────────────────────
    meta_title       = db.Column(db.Unicode(200), nullable=True, name="MetaTitle")
    meta_keyword     = db.Column(db.Unicode(300), nullable=True, name="MetaKeyword")
    meta_description = db.Column(db.Unicode(500), nullable=True, name="MetaDescription")
    ads              = db.Column(db.Unicode(1000), nullable=True, name="Ads")
    robots           = db.Column(db.Unicode(1000), nullable=True, name="Robots")

    # ── Scripts ───────────────────────────────────────────────────────
    script_verify    = db.Column(db.Unicode(2000), nullable=True, name="ScriptVerify")
    script_head      = db.Column(db.UnicodeText, nullable=True, name="ScriptHead")
    script_body      = db.Column(db.UnicodeText, nullable=True, name="ScriptBody")

    # ── Layout ────────────────────────────────────────────────────────
    content_home     = db.Column(db.UnicodeText, nullable=True, name="ContentHome")
    footer           = db.Column(db.UnicodeText, nullable=True, name="Footer")
    head             = db.Column(db.UnicodeText, nullable=True, name="Head")
    script_home      = db.Column(db.UnicodeText, nullable=True, name="ScriptHome")

    # ── Site identity (JSON) ──────────────────────────────────────────
    # {"FileLogo": "...", "FileFavicon": "...", "FileShare": "..."}
    # Missing from python-admin model — added for Flask client.
    website_info     = db.Column(db.JSON, nullable=True, name="WebsiteInfo")


_CONFIG_TTL = 60  # seconds
_cache_ts: float = 0.0
_cache_val: "SiteConfig | None" = None


def get_site_config() -> "SiteConfig | None":
    """Return the singleton SiteConfig (ID=1) with 60-second TTL cache."""
    global _cache_ts, _cache_val
    now = time.monotonic()
    if now - _cache_ts < _CONFIG_TTL and _cache_ts > 0:
        return _cache_val
    try:
        cfg = db.session.get(SiteConfig, 1)
        _cache_ts = now
        _cache_val = cfg
        return cfg
    except Exception:
        return None


def invalidate_site_config_cache() -> None:
    """Call after saving config changes so the next request re-reads from DB."""
    global _cache_ts
    _cache_ts = 0.0
