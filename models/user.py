"""
User model — maps to [tblUser] in SQL Server.
Schema verified against live DB (escaperoadx_db) on 2026-04-19.

Column mapping (DB name → Python attribute):
  IDU   → IDU            int,          PK, IDENTITY
  Users → username       nvarchar(30)
  Pass  → password       nvarchar(300) — DES+Base64 encrypted
  AcU   → is_active_flag int           — 1=active, 0=disabled
  Type  → role           int           — 1=admin, 0=editor
  Email → email          nvarchar(100)
  Name  → full_name      nvarchar(50)
  TimeU → time_updated   datetime
  ImgU  → avatar         nvarchar(50)
  AtU   → at_u           int           — VB hardcodes to 0 on save, not user-editable
  DescU → bio            ntext         — Thông tin chi tiết (CKEditor)
  FbL   → fb_link        nvarchar(200) — Page Facebook URL
  WebL  → web_link       nvarchar(200) — Website URL
  FbID  → fb_id          nvarchar(50)  — Facebook user ID (not exposed in admin form)

VB note: VB reads WebL as "WbL" (typo in edit form load) — Flask fixes this correctly.
"""

from flask_login import UserMixin
from extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "tblUser"

    IDU            = db.Column(db.Integer,      primary_key=True,  name="IDU")
    username       = db.Column(db.Unicode(30),  nullable=True,     name="Users")
    password       = db.Column(db.Unicode(300), nullable=True,     name="Pass")
    bcrypt_hash    = db.Column(db.Unicode(255), nullable=True,     name="BcryptHash")
    is_active_flag = db.Column(db.Integer,      nullable=True,     name="AcU")
    role           = db.Column(db.Integer,      nullable=True,     name="Type")
    email          = db.Column(db.Unicode(100), nullable=True,     name="Email")
    full_name      = db.Column(db.Unicode(50),  nullable=True,     name="Name")
    time_updated   = db.Column(db.DateTime,     nullable=True,     name="TimeU")
    avatar         = db.Column(db.Unicode(50),  nullable=True,     name="ImgU")
    at_u           = db.Column(db.Integer,      nullable=True,     name="AtU")
    bio            = db.Column(db.UnicodeText,  nullable=True,     name="DescU")
    fb_link        = db.Column(db.Unicode(200), nullable=True,     name="FbL")
    web_link       = db.Column(db.Unicode(200), nullable=True,     name="WebL")
    fb_id          = db.Column(db.Unicode(50),  nullable=True,     name="FbID")

    # ------------------------------------------------------------------ #
    # Flask-Login interface
    # ------------------------------------------------------------------ #
    def get_id(self) -> str:
        return str(self.IDU)

    @property
    def is_active(self) -> bool:
        return bool(self.is_active_flag)

    @property
    def is_admin(self) -> bool:
        """Type=1 — has admin-level access."""
        return self.role == 1

    @property
    def is_super_admin(self) -> bool:
        """
        IDU=1 — the original super-admin account.
        VB index.aspx redirects IDU=1 to menu.aspx, all others to news.aspx.
        """
        return self.IDU == 1

    def __repr__(self) -> str:
        return f"<User IDU={self.IDU} username={self.username!r} role={self.role}>"


@login_manager.user_loader
def load_user(user_id: str) -> "User | None":
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None
