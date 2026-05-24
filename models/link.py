"""
SQLAlchemy model for tblLink (URL routing index).

VB equivalent: url.aspx — read-only GridView of all site URLs.

tblLink is the central slug→content routing table used by Default.aspx.vb:
  SELECT top 1 * FROM tblLink WHERE RowUrl = '<slug>'

It is auto-synced by VB when saving Menu / News / Product.
Flask does NOT auto-sync yet — this module manages existing entries.

Column map:
  ID          → ID         int PK
  RowID       → row_id     int  content PK (AutoM/IDN/IDP)
  RowUrl      → row_url    nvarchar(200) — the URL slug (unique)
  RowTypeM    → row_type_m int  menu type (1=news, 2=pro)
  RowType     → row_type   int  1=menu, 2=news, 3=product
  RowLevels   → row_levels int  depth 1/2/3
  RowIDM      → row_idm    nvarchar(10) — menu IDM
  title       → title      nvarchar(200) SEO title
  keywords    → keywords   nvarchar(300) SEO keywords
  description → description nvarchar(500) SEO description
  RowName     → row_name   nvarchar(200) display name
  Rss         → rss        nvarchar(1000)
  RowLang     → row_lang   int  language (1=VI)
"""

from extensions import db

ROW_TYPE_LABELS = {1: "Menu", 2: "Tin tức", 3: "Sản phẩm"}


class Link(db.Model):
    __tablename__ = "tblLink"

    ID          = db.Column(db.Integer,       primary_key=True, name="ID")
    row_id      = db.Column(db.Integer,       nullable=True,    name="RowID")
    row_url     = db.Column(db.Unicode(200),  nullable=True,    name="RowUrl")
    row_type_m  = db.Column(db.Integer,       nullable=True,    name="RowTypeM")
    row_type    = db.Column(db.Integer,       nullable=True,    name="RowType")
    row_levels  = db.Column(db.Integer,       nullable=True,    name="RowLevels")
    row_idm     = db.Column(db.Unicode(10),   nullable=True,    name="RowIDM")
    title       = db.Column(db.Unicode(200),  nullable=True,    name="title")
    keywords    = db.Column(db.Unicode(300),  nullable=True,    name="keywords")
    description = db.Column(db.Unicode(500),  nullable=True,    name="description")
    row_name    = db.Column(db.Unicode(200),  nullable=True,    name="RowName")
    rss         = db.Column(db.Unicode(1000), nullable=True,    name="Rss")
    row_lang    = db.Column(db.Integer,       nullable=True,    default=1, name="RowLang")

    @property
    def type_label(self) -> str:
        return ROW_TYPE_LABELS.get(self.row_type or 0, "—")

    @property
    def full_url(self) -> str:
        return f"/{self.row_url}" if self.row_url else ""
