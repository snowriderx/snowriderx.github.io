"""
SQLAlchemy model for tblContact (contact/feedback submissions).

VB equivalent: contact.aspx

Column map:
  IDC      → ID         int PK
  NameC    → name       nvarchar(100)
  EmailC   → email      nvarchar(100)
  TelC     → tel        nvarchar(20)
  MobileC  → mobile     nvarchar(20)
  AddressC → address    nvarchar(300)
  ContentC → content    ntext
  TimeC    → created_at datetime
  AcC      → is_read    int  0=chưa đọc, 1=đã đọc
  ImgC     → img        nvarchar(50)
  PostID   → post_id    int  linked News.ID
  UserID   → user_id    int  admin user who handled
"""

from extensions import db


class Contact(db.Model):
    __tablename__ = "tblContact"

    ID         = db.Column(db.Integer,      primary_key=True, name="IDC")
    name       = db.Column(db.Unicode(100), nullable=True,    name="NameC")
    email      = db.Column(db.Unicode(100), nullable=True,    name="EmailC")
    tel        = db.Column(db.Unicode(20),  nullable=True,    name="TelC")
    mobile     = db.Column(db.Unicode(20),  nullable=True,    name="MobileC")
    address    = db.Column(db.Unicode(300), nullable=True,    name="AddressC")
    content    = db.Column(db.UnicodeText,  nullable=True,    name="ContentC")
    created_at = db.Column(db.DateTime,     nullable=True,    name="TimeC")
    is_read    = db.Column(db.Integer,      nullable=True,    default=0, name="AcC")
    img        = db.Column(db.Unicode(50),  nullable=True,    name="ImgC")
    post_id    = db.Column(db.Integer,      nullable=True,    name="PostID")
    user_id    = db.Column(db.Integer,      nullable=True,    name="UserID")

    @property
    def status_label(self) -> str:
        return {0: "Chưa xử lý", 1: "Đang xử lý", 2: "Hủy bỏ", 3: "Hoàn thành"}.get(self.is_read or 0, "—")

    @property
    def status_class(self) -> str:
        return {0: "warning", 1: "primary", 2: "secondary", 3: "success"}.get(self.is_read or 0, "secondary")
