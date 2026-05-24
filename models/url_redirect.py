"""
SQLAlchemy model for tblURL (301 redirect rules).

VB equivalent: link.aspx / link.aspx.vb
Client redirect: Default.aspx.vb — queries tblURL on every page request.

Column map:
  Url_ID   → ID         int PK (identity)
  Url_Old  → old_url    nvarchar(255) — source URL (path or full URL)
  Url_New  → new_url    nvarchar(255) — destination URL
  Url_Ac   → is_active  int  0=inactive, 1=active, 99=hidden in list
  Url_Type → url_type   int  optional filter grouping

VB redirect query (Default.aspx.vb):
  SELECT top 1 Url_New FROM tblURL WHERE Url_Ac <> 0 AND Url_Old = '<full_url>'
  → Response.RedirectPermanent(Url_New)

Flask matches by path OR full URL for dev/prod compatibility.
"""

from sqlalchemy import select

from extensions import db


class UrlRedirect(db.Model):
    __tablename__ = "tblURL"

    ID        = db.Column(db.Integer,      primary_key=True, name="Url_ID")
    old_url   = db.Column(db.Unicode(255), nullable=True,    name="Url_Old")
    new_url   = db.Column(db.Unicode(255), nullable=True,    name="Url_New")
    is_active = db.Column(db.Integer,      nullable=True,    default=1, name="Url_Ac")
    url_type  = db.Column(db.Integer,      nullable=True,    default=0, name="Url_Type")

    @property
    def active_label(self) -> str:
        return {1: "Hoạt động", 0: "Tắt"}.get(self.is_active or 0, "—")


def find_redirect(path: str, full_url: str = "") -> "str | None":
    """
    Look up a 301 redirect target for the given path.
    Checks path first (most common), then full URL (VB-compatible fallback).
    Returns the new_url string or None if no active rule matches.
    """
    new_url = db.session.execute(
        select(UrlRedirect.new_url)
        .where(UrlRedirect.is_active != 0, UrlRedirect.old_url == path)
        .limit(1)
    ).scalar_one_or_none()

    if new_url is None and full_url:
        new_url = db.session.execute(
            select(UrlRedirect.new_url)
            .where(UrlRedirect.is_active != 0, UrlRedirect.old_url == full_url)
            .limit(1)
        ).scalar_one_or_none()

    return new_url
