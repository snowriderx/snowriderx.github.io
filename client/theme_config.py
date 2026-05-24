"""
Singleton wrapper around theme/site_config.py.

Loaded once at import time. All client code should import `tc` instead of
calling importlib.import_module("theme.site_config") repeatedly.
"""
import importlib


class _ThemeConfig:
    def __init__(self):
        try:
            sc = importlib.import_module("theme.site_config")
        except Exception:
            sc = None
        self.SITE_NAME = getattr(sc, "SITE_NAME", "")
        self.GAME_NAME = getattr(sc, "GAME_NAME", self.SITE_NAME)
        self.GAME_SRC = getattr(sc, "GAME_SRC", "")
        self.SCHEMA_TYPE = getattr(sc, "SCHEMA_TYPE", "VideoGame")
        self.HAS_PRODUCTS = getattr(sc, "HAS_PRODUCTS", False)
        self.HAS_NOADS = getattr(sc, "HAS_NOADS", False)
        self.HAS_CONTACT_FORM = getattr(sc, "HAS_CONTACT_FORM", False)
        self.IFRAME_REFERRERPOLICY = getattr(sc, "IFRAME_REFERRERPOLICY", "")
        self.GAME_DELAY_MS = getattr(sc, "GAME_DELAY_MS", 0)


tc = _ThemeConfig()
