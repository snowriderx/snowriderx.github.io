"""
SQLAlchemy model for tblLangM (language-2 menu tree).

VB equivalent: lang.aspx / lang.aspx.vb

tblLangM has the SAME schema as tblMenu — it stores the navigation
structure for the second site language (typically English / language ID=2).
It is NOT a simple language-code registry.

Column map mirrors tblMenu (IDM primary key, NameM, SortM, AcM, …).

get_active_langs() returns a static list of language filter options
(1=Vietnamese, 2=English) used by news / product / banner dropdowns.
These are integer tag values stored in content rows — not derived from tblLangM.
"""

from collections import namedtuple

import sqlalchemy as _sa

from extensions import db


# ------------------------------------------------------------------ #
# Language filter options (static — used across content modules)
# ------------------------------------------------------------------ #

LangOption = namedtuple("LangOption", ["ID", "name"])

_LANG_OPTIONS: list[LangOption] = [
    LangOption(1, "Tiếng Việt"),
    LangOption(2, "English"),
]


def get_active_langs() -> list[LangOption]:
    """Return static language filter options (1=VI, 2=EN)."""
    return list(_LANG_OPTIONS)


# ------------------------------------------------------------------ #
# LangMenu model — maps tblLangM (mirror of tblMenu schema)
# ------------------------------------------------------------------ #

LANG_AC: dict[int, str] = {1: "Hiển thị", 0: "Ẩn"}
LANG_TYPES: dict[int, str] = {0: "Blank: Chứa nội dung", 1: "News: Chứa tin bài", 2: "Pro: Chứa Profile"}


class LangMenu(db.Model):
    __tablename__ = "tblLangM"

    IDM        = db.Column(db.Unicode(10),  primary_key=True, name="IDM")
    name       = db.Column(db.Unicode(200), nullable=True,    name="NameM")
    slug       = db.Column(db.Unicode(100), nullable=True,    name="Name1M")
    type_m     = db.Column(db.Integer,      nullable=True,    name="TypeM",  default=1)
    levels     = db.Column(db.Integer,      nullable=True,    name="Levels", default=1)
    sort_order = db.Column(db.Unicode(10),  nullable=True,    name="SortM",  default="00")
    is_active  = db.Column(db.Integer,      nullable=True,    name="AcM",    default=1)
    lang       = db.Column(db.Integer,      nullable=True,    name="Lang",   default=2)

    # Optional columns — class-level None defaults; mapped dynamically at startup
    # by init_optional_langmenu_columns() if the column exists in the live DB.
    auto_m      = None  # AutoM — identity int used in tblLink.RowID
    name_mh     = None  # NameMH — alternate heading for tblLink.RowName
    url         = None  # URL
    home_m      = None  # HomeM
    desc_m      = None  # DescM
    seo_title   = None  # title
    keywords    = None  # keywords
    description = None  # description
    ischema     = None  # ischema
    rel         = None  # Rel
    chk_m       = None  # ChkM
    tab_m       = None  # TabM

    @property
    def level_label(self) -> str:
        lvl = self.levels or 1
        return {1: "Cấp 1", 2: "Cấp 2", 3: "Cấp 3"}.get(lvl, f"Cấp {lvl}")

    @property
    def type_label(self) -> str:
        return {1: "News", 2: "Pro"}.get(self.type_m or 0, "Blank")

    @property
    def active_label(self) -> str:
        return LANG_AC.get(self.is_active if self.is_active is not None else 1, "—")

    @property
    def parent_idm(self) -> "str | None":
        lvl = self.levels or 1
        if lvl <= 1:
            return None
        if lvl == 2:
            return (self.IDM or "")[:2] + "0000"
        if lvl == 3:
            return (self.IDM or "")[:4] + "00"
        return None

    @property
    def computed_slug(self) -> str:
        if self.slug:
            return self.slug
        from admin.utils.text import slugify_vi
        return slugify_vi(self.name or "")


# Backward-compat alias — existing imports: `from app.models.lang import Lang`
Lang = LangMenu


# ------------------------------------------------------------------ #
# Optional column specs — mapped dynamically at startup
# ------------------------------------------------------------------ #

_OPTIONAL_LANGMENU_COLS: list[tuple] = [
    ("auto_m",      "AutoM",       _sa.Integer),
    ("name_mh",     "NameMH",      _sa.Unicode(200)),
    ("url",         "URL",         _sa.Unicode(100)),
    ("home_m",      "HomeM",       _sa.Integer),
    ("desc_m",      "DescM",       _sa.UnicodeText),
    ("seo_title",   "title",       _sa.Unicode(200)),
    ("keywords",    "keywords",    _sa.Unicode(100)),
    ("description", "description", _sa.Unicode(300)),
    ("ischema",     "ischema",     _sa.UnicodeText),
    ("rel",         "Rel",         _sa.Unicode(100)),
    ("chk_m",       "ChkM",        _sa.Integer),
    ("tab_m",       "TabM",        _sa.Unicode(20)),
]


def init_optional_langmenu_columns(engine) -> set:
    """
    Inspect tblLangM schema and map optional columns that actually exist.
    Called once from create_app() inside an app context.
    Returns the set of attr names that were successfully mapped.
    """
    from sqlalchemy import inspect as sa_inspect, Column, Identity
    from sqlalchemy.orm import column_property

    try:
        existing_db = {c["name"] for c in sa_inspect(engine).get_columns("tblLangM")}
    except Exception:
        return set()

    mapped: set = set()
    tbl = LangMenu.__table__

    for attr_name, db_name, sa_type in _OPTIONAL_LANGMENU_COLS:
        if attr_name in LangMenu.__mapper__.columns:
            mapped.add(attr_name)
            continue
        if db_name not in existing_db:
            continue
        if attr_name == "auto_m":
            col = Column(db_name, sa_type, Identity(), nullable=True)
        else:
            col = Column(db_name, sa_type, nullable=True)
        tbl.append_column(col)
        LangMenu.__mapper__.add_property(attr_name, column_property(col))
        mapped.add(attr_name)

    return mapped
