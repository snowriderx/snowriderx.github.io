"""
SQLAlchemy model for tblMenu (site navigation / content categories).

VB equivalents: menu.aspx / menu.aspx.vb

Column map (DB name → Python attr):
  IDM    → IDM        nvarchar(10)  PK — structured code e.g. '010000'
  NameM  → name       nvarchar(200) display name
  Name1M → slug       nvarchar(100) URL slug (VB: VnToEn(NameM))
  TypeM  → type_m     int           1=news, 2=pro/product, else blank
  Levels → levels     int           depth: 1=top, 2=sub, 3=sub-sub
  SortM  → sort_order nvarchar(10)  sort key; list is ordered by SortM ASC
  AcM    → is_active  int           1=visible, 0=hidden
  Lang   → lang       int           1=VI

Columns confirmed in VB source (menu.aspx.vb) but not yet exposed in
the admin form (lower priority — added as nullable to avoid write errors):
  AutoM   — auto-increment int used as RowID in tblLink (RowType=1)
  ChkM    — menu group/check type
  GroupM  — display group
  HomeM   — 1=shown on homepage
  DescM   — body description (ntext)
  NameMH  — alternate heading used in tblLink.RowName
  ImgM    — icon image filename
  ImgM1   — banner image filename
  URL     — external URL override
  TabM    — tab association (comma-delimited IDs like '-1-,-2-')
  ischema — JSON-LD / schema.org markup
  Rel     — rel attribute for links
  title   — SEO <title>
  keywords — SEO keywords
  description — SEO meta description

Hierarchy encoding (IDM format, zero-padded to 6 chars):
  Level 1: XX0000   e.g. '010000' — top-level category
  Level 2: XXYY00   e.g. '010100' — sub-category under 'XX0000'
  Level 3: XXYYZZ   e.g. '010101' — leaf under 'XXYY00'

Parent-child is inferred from the IDM string — there is NO parent_id column.
  Level 2 parent  = IDM[:2] + '0000'
  Level 3 parent  = IDM[:4] + '00'

Ordering: VB orders menus by SortM ASC (a string, zero-padded e.g. '01').
  Flask falls back to IDM ASC when SortM is NULL / equal.

VB list query (menu.aspx.vb loadMenu):
  SELECT IDM, NameM, Name1M, SortM, AcM, ImgM, URL, TypeM
  FROM tblMenu
  WHERE levels = <lv> AND Left(IDM, lv*2-2) = Left(parent, lv*2-2)
  AND Lang = <lang>
  ORDER BY SortM

VB news-form menu dropdown (news.aspx.vb LoadInsert / BindData):
  SELECT IDM as ID,
         CASE WHEN Levels=2 THEN '......'+NameM
              WHEN Levels=3 THEN '.........'+NameM
              ELSE NameM END Name
  FROM tblMenu
  WHERE TypeM IN (1) AND Lang = <lang>
  ORDER BY IDM ASC         ← NOTE: IDM not SortM in news context

Compatibility notes:
  - tblNews.MenuIDN (nvarchar 6) references IDM directly.
  - tblLink.RowIDM  references IDM directly; RowType=1 for menus.
  - tblLink.RowID   for menus uses AutoM (not IDM), unlike news (IDN).
  - Deleting IDM without cascading will orphan tblNews.MenuIDN references.

VB delete cascade (menu.aspx.vb dtgrView_DeleteCommand):
  If Right(IDM, 4) = '0000':   ← Level-1 item
    DELETE tblLink  WHERE Left(RowIDM, 2) = Left(IDM, 2) AND RowType=1
    DELETE tblMenu  WHERE Left(IDM,   2) = Left(IDM, 2)  ← deletes ALL children
  Else:
    DELETE tblLink WHERE RowIDM = IDM AND RowType=1
    DELETE tblMenu WHERE IDM    = IDM

Flask currently BLOCKS delete if children exist (safer, no cascade).
This is a known behavioral difference — VB admins should be aware.

VB tblLink sync (menu.aspx.vb btnAddU1_Click):
  DELETE tblLink WHERE RowIDM=IDM AND RowType=1 AND RowLang=lang
  INSERT INTO tblLink (...) SELECT AutoM, Name1M, 1, TypeM, Levels, IDM,
    title, keywords, description, NameMH, Lang FROM tblMenu WHERE IDM=IDM
Flask does NOT sync tblLink on menu save (gap — tblLink for menus may drift
until VB admin re-saves or a future tblLink sync is added).

Permission-system readiness:
  IDM is the stable natural key. VB stores per-user, per-menu permissions
  in tblPermissions (MenuID, UserID, AddNews, EditNews, DelNews, ChkNews).
  Flask does not yet implement this — all logged-in users see all menus.
"""

from extensions import db

MENU_TYPES: dict[int, str] = {
    0: "Blank: Chứa nội dung",
    1: "News: Chứa tin bài",
    2: "Pro: Chứa Profile",
}

MENU_LANGS: dict[int, str] = {
    1: "Tiếng Việt",
}

MENU_AC: dict[int, str] = {
    1: "Hiển thị",
    0: "Ẩn",
}

MENU_CHK: dict[int, str] = {
    1: "Menu ngang trên",
    2: "Menu chân trang",
}


class Menu(db.Model):
    __tablename__ = "tblMenu"

    IDM        = db.Column(db.Unicode(10),  primary_key=True, name="IDM")
    name       = db.Column(db.Unicode(200), nullable=True,    name="NameM")
    # Name1M: URL slug — VB generates via VnToEn(NameM). Flask mirrors with
    # slugify_vi(). Always write this on create/edit so tblLink stays consistent.
    slug       = db.Column(db.Unicode(100), nullable=True,    name="Name1M")
    type_m     = db.Column(db.Integer,      nullable=True,    name="TypeM",  default=1)
    levels     = db.Column(db.Integer,      nullable=True,    name="Levels", default=1)
    # SortM: string sort key e.g. '01', '02'. VB orders menus by SortM ASC.
    sort_order = db.Column(db.Unicode(10),  nullable=True,    name="SortM",  default="00")
    # AcM: 1=visible, 0=hidden. VB's menu batch-update sets this per row.
    is_active  = db.Column(db.Integer,      nullable=True,    name="AcM",    default=1)
    lang       = db.Column(db.Integer,      nullable=True,    name="Lang",   default=1)
    # lang (Lang) stores the tblLangM.ID value directly as an integer.

    # ------------------------------------------------------------------ #
    # Extended fields — mapped dynamically by init_optional_menu_columns()
    # in app/__init__.py after the DB schema is inspected at startup.
    # Columns that don't exist in the actual DB get a Python None default
    # so templates / routes never see an AttributeError.
    # ------------------------------------------------------------------ #
    # Python-level None defaults (overwritten by mapper when column exists):
    auto_m      = None  # AutoM — identity int, used in image filenames + tblLink
    name_mh     = None  # NameMH
    url         = None  # URL
    home_m      = None  # HomeM
    desc_m      = None  # DescM
    seo_title   = None  # title
    keywords    = None  # keywords
    description = None  # description
    ischema     = None  # ischema
    rel         = None  # Rel
    img_m       = None  # ImgM
    img_m1      = None  # ImgM1
    chk_m       = None  # ChkM
    tab_m       = None  # TabM — comma-delimited tab IDs e.g. '-1-,-2-'
    bg_m        = None  # BgM — CSS background color hex e.g. '#f5f5f5'
    css_m       = None  # Css — custom CSS block for layout pages

    # ------------------------------------------------------------------ #
    # Display helpers
    # ------------------------------------------------------------------ #

    @property
    def display_name(self) -> str:
        """
        Indent display name by depth level — mirrors VB CASE expression.
        Used by News / Banner dropdowns so indentation is consistent.

        VB: CASE WHEN Levels=2 THEN '......'+NameM
                 WHEN Levels=3 THEN '.........'+NameM
                 ELSE NameM END
        """
        lvl = self.levels or 1
        if lvl == 2:
            prefix = "...... "
        elif lvl == 3:
            prefix = "......... "
        elif lvl > 3:
            prefix = "." * (lvl * 3) + " "
        else:
            prefix = ""
        return prefix + (self.name or "")

    @property
    def computed_slug(self) -> str:
        """
        Derive slug from name using slugify_vi() — matches VB's VnToEn().
        Returns stored slug if set, otherwise derives on-the-fly.
        """
        if self.slug:
            return self.slug
        from admin.utils.text import slugify_vi
        return slugify_vi(self.name or "")

    @property
    def parent_idm(self) -> "str | None":
        """Derive parent IDM from the structured IDM code."""
        lvl = self.levels or 1
        if lvl <= 1:
            return None
        if lvl == 2:
            return (self.IDM or "")[:2] + "0000"
        if lvl == 3:
            return (self.IDM or "")[:4] + "00"
        return None

    @property
    def type_label(self) -> str:
        return {1: "News", 2: "Pro"}.get(self.type_m, "Blank")

    @property
    def has_icon(self) -> bool:
        return bool(self.img_m) and self.img_m != "null.gif"

    @property
    def has_banner(self) -> bool:
        return bool(self.img_m1) and self.img_m1 != "null.gif"

    @property
    def level_label(self) -> str:
        lvl = self.levels or 1
        return {1: "Cấp 1", 2: "Cấp 2", 3: "Cấp 3"}.get(lvl, f"Cấp {lvl}")

    @property
    def active_label(self) -> str:
        return MENU_AC.get(self.is_active if self.is_active is not None else 1, "—")

    @property
    def chk_label(self) -> str:
        return MENU_CHK.get(self.chk_m, "—") if self.chk_m else "—"

    @property
    def tab_selected_ids(self) -> set:
        """Parse TabM string '-1-,-2-' into a set of integer IDs {1, 2}."""
        if not self.tab_m:
            return set()
        ids = set()
        for part in (self.tab_m or "").split(","):
            part = part.strip().strip("-")
            if part.isdigit():
                ids.add(int(part))
        return ids


# ------------------------------------------------------------------ #
# Optional column specs — (attr_name, db_column_name, sa_type)
# Mapped dynamically at startup by init_optional_menu_columns().
# ------------------------------------------------------------------ #
import sqlalchemy as _sa

_OPTIONAL_MENU_COLS: list[tuple] = [
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
    ("img_m",       "ImgM",        _sa.Unicode(200)),
    ("img_m1",      "ImgM1",       _sa.Unicode(200)),
    ("chk_m",       "ChkM",        _sa.Integer),
    ("tab_m",       "TabM",        _sa.Unicode(20)),
    ("bg_m",        "BgM",         _sa.Unicode(10)),
    ("css_m",       "Css",         _sa.UnicodeText),
]


def get_layout_pages(lang: int = 1) -> "list[Menu]":
    """
    Return layout pages: tblMenu WHERE ChkM=80 AND Levels=1 ORDER BY SortM ASC.
    Returns [] when ChkM column is not yet mapped (migration not run).
    """
    from sqlalchemy import select
    from extensions import db

    try:
        if "chk_m" not in Menu.__mapper__.columns:
            return []
    except Exception:
        return []

    q = (
        select(Menu)
        .where(Menu.chk_m == 80, Menu.levels == 1, Menu.lang == lang)
        .order_by(Menu.sort_order.asc(), Menu.IDM.asc())
    )
    return db.session.execute(q).scalars().all()


def init_optional_menu_columns(engine) -> set:
    """
    Inspect tblMenu schema and map optional columns that actually exist.

    Called once from create_app() inside an app context so the engine is
    bound.  For each optional column:
      - exists in DB  → append to Table + add mapper property (deferred)
      - missing in DB → leave the class-level None default in place

    Returns the set of attr names that were successfully mapped.
    """
    from sqlalchemy import inspect as sa_inspect, Column, Identity
    from sqlalchemy.orm import column_property

    try:
        existing_db = {c["name"] for c in sa_inspect(engine).get_columns("tblMenu")}
    except Exception:
        return set()

    mapped: set = set()
    tbl = Menu.__table__

    for attr_name, db_name, sa_type in _OPTIONAL_MENU_COLS:
        # Skip if already a proper mapped column (e.g. called twice)
        if attr_name in Menu.__mapper__.columns:
            mapped.add(attr_name)
            continue

        if db_name not in existing_db:
            # Column absent — leave the None class default in place
            continue

        # Append to the Table object and register with the mapper
        # AutoM is a SQL Server IDENTITY column — never include in INSERT
        if attr_name == "auto_m":
            col = Column(db_name, sa_type, Identity(), nullable=True)
        else:
            col = Column(db_name, sa_type, nullable=True)
        tbl.append_column(col)
        Menu.__mapper__.add_property(attr_name, column_property(col))
        mapped.add(attr_name)

    return mapped
