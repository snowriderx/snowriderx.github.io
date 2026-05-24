"""
SQLAlchemy model for tblNews (news articles).

VB equivalents:
  news.aspx / news.aspx.vb

Column map (Python attr → DB column):
  ID          → IDN          (PK, identity)
  name        → NameN        nvarchar(200)   article title (required)
  slug        → Name1N       nvarchar(200)   URL slug (auto-generated)
  title       → TitleN       nvarchar(200)   SEO page title
  keywords    → KeyN         nvarchar(300)   SEO keywords
  description → DecripN      nvarchar(500)   SEO meta description
  content     → ContentN     nvarchar(500)   short excerpt / summary
  desc        → DescN        ntext           full body HTML (CKEditor)
  news_type   → TypeN        int             1=article, 2=landing page
  script_code → ScriptCode   ntext           raw embed code (no sanitize)
  is_active   → AcN          int             1=show, 3=hidden from list, 0=hide
  img         → ImgN         nvarchar(200)   thumbnail filename
  img1        → Img1N        nvarchar(200)   secondary image filename
  menu_id     → MenuIDN      nvarchar(6)     category (FK → tblMenu.IDM)
  created_at  → TimeN        datetime        insert / eTop bump timestamp
  updated_at  → TimeUpN      datetime        last update timestamp
  user_id     → uID          int             admin user who created
  rss_url     → URL          nvarchar(1000)  RSS source link (unused in UI)
  seo_type    → SEON         int             NOT NULL, default 0 (SEO flag)
  news_flag   → News         int             misc flag
  position    → Vt           nvarchar        position/layout hint
  views       → Views        int             view counter

VB AcN values:
  1 → "Hiển thị"           (visible on site)
  3 → "Ẩn khỏi danh mục"  (hidden from listing, but accessible by URL)
  0 → "Ẩn"                 (fully hidden)
"""

from extensions import db

NEWS_STATUS: dict[int, str] = {
    1: "Hiển thị",
    3: "Ẩn khỏi danh mục",
    0: "Ẩn",
}

NEWS_TYPES: dict[int, str] = {
    1: "Tin bài",
    2: "Landing page",
}


class News(db.Model):
    __tablename__ = "tblNews"

    ID          = db.Column(db.Integer, primary_key=True, name="IDN")
    name        = db.Column(db.Unicode(200), nullable=True, name="NameN")
    slug        = db.Column(db.Unicode(200), nullable=True, name="Name1N")
    title       = db.Column(db.Unicode(200), nullable=True, name="TitleN")
    keywords    = db.Column(db.Unicode(300), nullable=True, name="KeyN")
    description = db.Column(db.Unicode(500), nullable=True, name="DecripN")
    content     = db.Column(db.Unicode(500), nullable=True, name="ContentN")
    desc        = db.Column(db.UnicodeText, nullable=True, name="DescN")
    news_type   = db.Column(db.Integer, nullable=True, default=1, name="TypeN")
    script_code = db.Column(db.UnicodeText, nullable=True, name="ScriptCode")
    is_active   = db.Column(db.Integer, nullable=True, default=1, name="AcN")
    img         = db.Column(
        db.Unicode(200), nullable=True, default="null.gif", name="ImgN",
    )
    img1        = db.Column(db.Unicode(200), nullable=True, name="Img1N")
    menu_id     = db.Column(db.Unicode(6), nullable=True, name="MenuIDN")
    created_at  = db.Column(db.DateTime, nullable=True, name="TimeN")
    updated_at  = db.Column(db.DateTime, nullable=True, name="TimeUpN")
    user_id     = db.Column(db.Integer, nullable=True, name="uID")
    rss_url     = db.Column(
        db.Unicode(1000), nullable=True, default=",", name="URL",
    )
    seo_type    = db.Column(db.Integer, nullable=False, default=0, name="SEON")
    news_flag   = db.Column(db.Integer, nullable=True, name="News")
    position    = db.Column(db.Unicode(200), nullable=True, name="Vt")
    views       = db.Column(db.Integer, nullable=True, default=0, name="Views")
    # tblNews has no Lang column — news language is inferred from its menu.

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @property
    def has_image(self) -> bool:
        """True when ImgN is a real file, not the null placeholder."""
        return bool(self.img) and self.img != "null.gif"

    @property
    def status_label(self) -> str:
        return NEWS_STATUS.get(self.is_active if self.is_active is not None else 1, "—")

    @property
    def type_label(self) -> str:
        return NEWS_TYPES.get(self.news_type or 1, "—")
