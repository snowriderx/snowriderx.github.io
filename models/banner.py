"""
Advert model — maps to tblAdvert.

VB equivalents:
  advert.aspx   → list/CRUD filtered by Type + langid (= MenuID)
  advertc.aspx  → list/CRUD filtered by Type + MenuID (menu tree)

Column map (DB name → Python attr):
  ID         → ID           (PK)
  Title      → title        nvarchar(100)
  Name       → link         nvarchar(300)  stored without "http://"
  Img        → img          nvarchar(30)   default 'null.gif'
  Sort       → sort         nvarchar(10)   default '0'
  Type       → zone_type    int            zone/area on the page
  Ac         → is_active    int            1=visible, 0=hidden
  Lang       → lang         int            always 1 (single-lang site)
  MenuID     → menu_id      nvarchar(10)   '000000'=home, else tblMenu.IDM
  Contents   → contents     nvarchar(500)  short description
  TypeD      → type_d       int            1=Banner, 2=Ads, 3=Code
  Html       → html         ntext          rich HTML (CKEditor)
  sCode      → s_code       nvarchar(1000) embed code (e.g. Adsense)
  Rel        → rel          nvarchar(50)   unused
  isHeading  → is_heading   int            1=styled as heading
"""

from extensions import db

# Zone labels — covers both advert.aspx (91-98) and advertc.aspx (1-11) ranges.
# Keys are the integer Type values stored in the DB.
ZONE_TYPES = {
    1: "Slider",
    2: "Widget",
    3: "Section 1",
    4: "Section 2",
    5: "Section 3",
    6: "Popup",
    7: "Quảng cáo",
    8: "Sidebar",
    9: "Footer",
    10: "Section 4",
    11: "Section 5",
    91: "Tính năng",
    92: "Ưu điểm",
    93: "Hướng dẫn",
    94: "Hỏi đáp",
    95: "Tổng quan",
    96: "Banner",
    97: "Nội dung",
    98: "Chân trang",
}

# Display-type labels for TypeD column
DISPLAY_TYPES = {
    0: "Html",
    1: "Banner",
    2: "Ads",
    3: "Mã code",
}


class Advert(db.Model):
    __tablename__ = "tblAdvert"

    ID = db.Column(db.Integer, primary_key=True, name="ID")
    title = db.Column(db.Unicode(100), nullable=True, name="Title")
    link = db.Column(db.Unicode(300), nullable=True, name="Name")
    img = db.Column(
        db.Unicode(30), nullable=True, default="null.gif", name="Img",
    )
    sort = db.Column(
        db.Unicode(10), nullable=True, default="0", name="Sort",
    )
    zone_type = db.Column(db.Integer, nullable=True, default=0, name="Type")
    is_active = db.Column(db.Integer, nullable=True, default=1, name="Ac")
    lang = db.Column(db.Integer, nullable=True, default=1, name="Lang")
    menu_id = db.Column(
        db.Unicode(10), nullable=True, default="000000", name="MenuID",
    )
    contents = db.Column(
        db.Unicode(500), nullable=True, name="Contents",
    )
    type_d = db.Column(db.Integer, nullable=True, default=1, name="TypeD")
    html = db.Column(db.UnicodeText, nullable=True, name="Html")
    s_code = db.Column(
        db.Unicode(1000), nullable=True, name="sCode",
    )
    rel = db.Column(db.Unicode(50), nullable=True, name="Rel")
    is_heading = db.Column(
        db.Integer, nullable=True, default=0, name="isHeading",
    )
    # lang (Lang) stores the tblLangM.ID value directly as an integer.

    @property
    def has_image(self) -> bool:
        return bool(self.img) and self.img != "null.gif"

    @property
    def zone_label(self) -> str:
        return ZONE_TYPES.get(self.zone_type, f"Zone {self.zone_type}")

    @property
    def type_d_label(self) -> str:
        return DISPLAY_TYPES.get(self.type_d or 0, str(self.type_d))
