"""
SQLAlchemy model for tblIntro (intro/template content blocks).

VB equivalents:
  template.aspx / template.aspx.vb

Column mapping (Python attr → DB column):
  ID        → ID       (PK, identity)
  name      → Name     nvarchar(100)   display title (required)
  descs     → Descs    ntext           body HTML (CKEditor; h1→h2 on save)
  intro_type→ Type     int             always 80 (hardcoded in VB, not exposed)
  is_active → Ac       int             1=show, 0=hidden, 99=soft-deleted
  sort      → Sort     nvarchar(10)    sort order string (default "50")
  img       → Img      nvarchar(200)   image filename (max 100px wide)

VB Ac values:
  1  → "Hiển thị"   (visible)
  0  → "Ẩn"         (hidden)
  99 → soft-deleted  (excluded from list — never hard-deleted)

VB note: module is called "template.aspx" but the table is tblIntro.
"""

from sqlalchemy import select

from extensions import db

INTRO_STATUS: dict[int, str] = {
    1: "Hiển thị",
    0: "Ẩn",
}


class Intro(db.Model):
    __tablename__ = "tblIntro"

    ID         = db.Column(db.Integer, primary_key=True, name="ID")
    name       = db.Column(db.Unicode(100), nullable=True, name="Name")
    descs      = db.Column(db.UnicodeText, nullable=True, name="Descs")
    intro_type = db.Column(db.Integer, nullable=True, default=80, name="Type")
    is_active  = db.Column(db.Integer, nullable=True, default=1, name="Ac")
    sort       = db.Column(db.Unicode(10), nullable=True, default="50", name="Sort")
    img        = db.Column(db.Unicode(200), nullable=True, default="null.gif", name="Img")

    @property
    def has_image(self) -> bool:
        """True when Img is a real file, not the null placeholder."""
        return bool(self.img) and self.img != "null.gif"

    @property
    def status_label(self) -> str:
        return INTRO_STATUS.get(self.is_active if self.is_active is not None else 1, "—")


def get_active_intros() -> "list[Intro]":
    """Return visible intro blocks (Ac=1) ordered by Sort ASC."""
    q = select(Intro).where(Intro.is_active == 1).order_by(Intro.sort.asc())
    return db.session.execute(q).scalars().all()
