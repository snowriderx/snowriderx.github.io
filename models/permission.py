"""
SQLAlchemy model for tblPermissions.

VB equivalent: phanquyen.aspx / phanquyen.aspx.vb

Column mapping (DB name → Python attribute):
  ID       → ID         int, PK, IDENTITY
  UserID   → user_id    int — FK to tblUser.IDU
  MenuID   → menu_id    nvarchar(6) — matches tblMenu.IDM
  AddNews  → can_add    int — 1=allowed, 0/NULL=denied
  EditNews → can_edit   int
  DelNews  → can_del    int
  ChkNews  → can_chk    int — approve/publish
  Upfile   → can_up     int — upload file

VB save strategy: DELETE all rows for UserID, then INSERT checked rows.
Flask mirrors this DELETE+INSERT pattern in the permissions route.

VB access: Type=1 admins can manage permissions for other Type=1 users (IDU<>1).
Super-admin (IDU=1) is excluded from the permission UI — always full access.
"""

from extensions import db


class Permission(db.Model):
    __tablename__ = "tblPermissions"

    ID       = db.Column(db.Integer,     primary_key=True, name="ID")
    user_id  = db.Column(db.Integer,     nullable=True,    name="UserID")
    menu_id  = db.Column(db.Unicode(6),  nullable=True,    name="MenuID")
    can_add  = db.Column(db.Integer,     nullable=True,    name="AddNews")
    can_edit = db.Column(db.Integer,     nullable=True,    name="EditNews")
    can_del  = db.Column(db.Integer,     nullable=True,    name="DelNews")
    can_chk  = db.Column(db.Integer,     nullable=True,    name="ChkNews")
    can_up   = db.Column(db.Integer,     nullable=True,    name="Upfile")

    def __repr__(self) -> str:
        return (
            f"<Permission user={self.user_id} menu={self.menu_id} "
            f"add={self.can_add} edit={self.can_edit} del={self.can_del}>"
        )
