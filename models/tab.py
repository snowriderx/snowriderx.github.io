"""
SQLAlchemy model for tblTab (product/news/menu tabs).

VB equivalents:
  tab.aspx / tab.aspx.vb

Column mapping (Python attr → DB column):
  ID        → ID     (PK, identity)
  name      → Name   nvarchar(200)  display name
  slug      → Name1  nvarchar(200)  URL slug (auto-generated via VNtoEn)
  sort      → Sort   nvarchar(10)   sort order string (default "00")
  is_active → Ac     bit            1=visible, 0=hidden
  tab_type  → Type   int            1=Product, 2=News, 3=Menu
  total     → Total  int            display record count per tab
  hot       → Hot    int            sidebar visibility (1=show, 0=hide)
"""

from extensions import db

TAB_TYPE_PRODUCT = 1
TAB_TYPE_NEWS = 2
TAB_TYPE_MENU = 3

TAB_TYPE_LABELS = {
    TAB_TYPE_PRODUCT: "Tab sản phẩm",
    TAB_TYPE_NEWS: "Tab tin tức",
    TAB_TYPE_MENU: "Tab menu",
}


class Tab(db.Model):
    __tablename__ = "tblTab"

    ID = db.Column(db.Integer, primary_key=True, name="ID")
    name = db.Column(db.Unicode(200), nullable=True, name="Name")
    slug = db.Column(db.Unicode(200), nullable=True, name="Name1")
    sort = db.Column(db.Unicode(10), nullable=True, default="00", name="Sort")
    is_active = db.Column(db.Integer, nullable=True, default=1, name="Ac")
    tab_type = db.Column(db.Integer, nullable=True, default=TAB_TYPE_PRODUCT, name="Type")
    total = db.Column(db.Integer, nullable=True, default=0, name="Total")
    hot = db.Column(db.Integer, nullable=True, default=0, name="Hot")
