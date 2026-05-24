"""
SQLAlchemy model for tblTag.

VB equivalents:
  tag.aspx   — Menu tags  (Type=0)
  tagn.aspx  — News tags  (Type=3)
  tagw.aspx  — Website tags (Type=5)

Column map (DB → Python):
  ID     → ID        int PK IDENTITY
  Title  → title     nvarchar(300)  display / anchor text
  Link   → link      nvarchar(300)  URL slug or '#' for no link
  MenuID → menu_id   nvarchar(10)   owner ID:
                                     Type=0 → tblMenu.IDM
                                     Type=3 → str(tblNews.IDN)
                                     Type=5 → '0' (global)
  Ac     → is_active int            1=visible, 0=hidden
  Type   → tag_type  int            0=Menu, 3=News, 5=Website
  Sort   → sort      nvarchar(10)   lexicographic sort key e.g. '01', '01.2'
  Rel    → rel       nvarchar(50)   link rel/target attrs e.g. 'rel=nofollow'

Relationships are semantic only — no FK constraints in DB.
"""

from extensions import db

TAG_TYPE_MENU    = 0
TAG_TYPE_NEWS    = 3
TAG_TYPE_WEBSITE = 5

# Section name → tag_type int (used in URL routing)
SECTIONS: dict[str, int] = {
    "menu":    TAG_TYPE_MENU,
    "news":    TAG_TYPE_NEWS,
    "website": TAG_TYPE_WEBSITE,
}

SECTION_LABELS: dict[str, str] = {
    "menu":    "Menu",
    "news":    "Tin tức",
    "website": "Website",
}

TAG_AC: dict[int, str] = {
    1: "Hiển thị",
    0: "Ẩn",
}


class Tag(db.Model):
    __tablename__ = "tblTag"

    ID        = db.Column(db.Integer,      primary_key=True, name="ID")
    title     = db.Column(db.Unicode(300), nullable=True,    name="Title")
    link      = db.Column(db.Unicode(300), nullable=True,    name="Link")
    menu_id   = db.Column(db.Unicode(10),  nullable=True,    name="MenuID")
    is_active = db.Column(db.Integer,      nullable=True,    default=1,    name="Ac")
    tag_type  = db.Column(db.Integer,      nullable=True,    default=0,    name="Type")
    sort      = db.Column(db.Unicode(10),  nullable=True,    default="00", name="Sort")
    rel       = db.Column(db.Unicode(50),  nullable=True,    name="Rel")

    @property
    def active_label(self) -> str:
        return TAG_AC.get(self.is_active if self.is_active is not None else 1, "—")

    @property
    def display_link(self) -> str:
        return self.link or "#"
