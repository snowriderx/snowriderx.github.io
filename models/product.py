"""
SQLAlchemy model for tblPro (products).

VB equivalents:
  pro.aspx / pro.aspx.vb

Column mapping (Python attr → DB column):
  ID         → IDP        (PK, identity)
  name       → NameP      nvarchar(150)   product name
  slug       → Name1P     nvarchar(150)   URL slug
  title      → TitleP     nvarchar(200)   SEO page title
  keywords   → KeyP       nvarchar(300)   SEO keywords
  description→ DecripP    nvarchar(500)   SEO meta description
  script     → ScriptP    nvarchar(2000)  custom JS/embed
  is_home    → HomeP      int             featured / hot flag
  locale     → LocaleP    nvarchar(50)    locale URL path (used in tblLink)
  style      → StyleP     nvarchar(50)    CSS class
  source     → SourceP    ntext           source HTML (CKEditor)
  content    → ContentP   ntext           content HTML (CKEditor)
  desc       → DescP      ntext           description HTML (CKEditor; h1→h2)
  footer     → FooterP    ntext           footer HTML (CKEditor)
  is_active  → AcP        int             1=active, 0=inactive
  img        → ImgP       nvarchar(100)   thumbnail filename  (sm-<id>.<ext>)
  img1       → Img1P      nvarchar(100)   large image filename (lg_<id>.<ext>)
  menu_id    → MenuIDP    nvarchar(8)     always '070000' (hardcoded in VB)
  created_at → TimeP      datetime        insert/bump timestamp
  user_id    → uID        int             admin user ID
  lang       → LangP      int             language (1 = VI)

Optional column (added by Flask migration, not in original VB schema):
  tab_id     → TabIDP     int             FK → tblTab.ID (nullable)
  Mapped dynamically by init_optional_product_columns() at startup.
  Run migrations/add_tab_id_to_tblpro.sql before enabling tab filtering.
"""

import sqlalchemy as _sa

from extensions import db


class Product(db.Model):
    __tablename__ = "tblPro"

    ID = db.Column(db.Integer, primary_key=True, name="IDP")
    name = db.Column(db.Unicode(150), nullable=True, name="NameP")
    slug = db.Column(db.Unicode(150), nullable=True, name="Name1P")
    title = db.Column(db.Unicode(200), nullable=True, name="TitleP")
    keywords = db.Column(db.Unicode(300), nullable=True, name="KeyP")
    description = db.Column(db.Unicode(500), nullable=True, name="DecripP")
    script = db.Column(db.UnicodeText, nullable=True, name="ScriptP")
    is_home = db.Column(db.Integer, nullable=True, default=0, name="HomeP")
    locale = db.Column(db.Unicode(50), nullable=True, name="LocaleP")
    style = db.Column(db.Unicode(50), nullable=True, name="StyleP")
    source = db.Column(db.UnicodeText, nullable=True, name="SourceP")
    content = db.Column(db.UnicodeText, nullable=True, name="ContentP")
    desc = db.Column(db.UnicodeText, nullable=True, name="DescP")
    footer = db.Column(db.UnicodeText, nullable=True, name="FooterP")
    is_active = db.Column(db.Integer, nullable=True, default=1, name="AcP")
    img = db.Column(
        db.Unicode(100), nullable=True, default="null.gif", name="ImgP"
    )
    img1 = db.Column(
        db.Unicode(100), nullable=True, default="null.gif", name="Img1P"
    )
    menu_id = db.Column(
        db.Unicode(8), nullable=True, default="070000", name="MenuIDP"
    )
    created_at = db.Column(db.DateTime, nullable=True, name="TimeP")
    user_id = db.Column(db.Integer, nullable=True, name="uID")
    lang = db.Column(db.Text, nullable=True, default="1", name="LangP")

    # lang (LangP): DB stores as TEXT (e.g. "1", "2") — cast on compare.

    # ------------------------------------------------------------------ #
    # Optional tab column — mapped by init_optional_product_columns().
    # Class-level None default: routes + templates must guard with
    # tab_column_ready() before using this attribute.
    # ------------------------------------------------------------------ #
    tab_id = None   # TabIDP int → tblTab.ID

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @property
    def has_image(self) -> bool:
        """Thumbnail (ImgP) is a real file, not the null placeholder."""
        return bool(self.img) and self.img != "null.gif"

    @property
    def has_image1(self) -> bool:
        """Large image (Img1P) is a real file, not the null placeholder."""
        return bool(self.img1) and self.img1 != "null.gif"


# ------------------------------------------------------------------ #
# Optional column specs — mapped dynamically at startup.
# ------------------------------------------------------------------ #

_OPTIONAL_PRODUCT_COLS: list[tuple] = [
    ("tab_id", "TabIDP", _sa.Integer),
]


def tab_column_ready() -> bool:
    """Return True if TabIDP has been mapped onto the Product model."""
    try:
        return "tab_id" in Product.__mapper__.columns
    except Exception:
        return False


def init_optional_product_columns(engine) -> set:
    """
    Inspect tblPro schema and map optional columns that actually exist.

    Called once from create_app() inside an app context.
    For each optional column:
      - exists in DB  → append to Table + add mapper property
      - missing in DB → leave the class-level None default in place

    Returns the set of attr names that were successfully mapped.
    Run migrations/add_tab_id_to_tblpro.sql to enable tab filtering.
    """
    from sqlalchemy import inspect as sa_inspect, Column
    from sqlalchemy.orm import column_property

    try:
        existing_db = {c["name"] for c in sa_inspect(engine).get_columns("tblPro")}
    except Exception:
        return set()

    mapped: set = set()
    tbl = Product.__table__

    for attr_name, db_name, sa_type in _OPTIONAL_PRODUCT_COLS:
        if attr_name in Product.__mapper__.columns:
            mapped.add(attr_name)
            continue

        if db_name not in existing_db:
            continue

        col = Column(db_name, sa_type, nullable=True)
        tbl.append_column(col)
        Product.__mapper__.add_property(attr_name, column_property(col))
        mapped.add(attr_name)

    return mapped
