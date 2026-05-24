from extensions import db


class Comment(db.Model):
    __tablename__ = "tblComment"

    ID      = db.Column(db.Integer,      primary_key=True, name="IDC")
    name    = db.Column(db.Unicode(100), nullable=True,    name="NameC")
    email   = db.Column(db.Unicode(100), nullable=True,    name="EmailC")
    content = db.Column(db.Unicode(500), nullable=True,    name="CommentC")
    is_show = db.Column(db.Integer,      nullable=True,    default=0, name="AcC")
    created_at = db.Column(db.DateTime,  nullable=True,    name="TimeC")
    news_id = db.Column(db.Integer,      nullable=True,    name="NewsID")
    type_c  = db.Column(db.Integer,      nullable=True,    default=0, name="TypeC")
    rate    = db.Column(db.Integer,      nullable=True,    name="Rate")

    @property
    def status_label(self):
        return "Hiện thị" if self.is_show == 1 else "Ẩn"

    @property
    def status_class(self):
        return "success" if self.is_show == 1 else "secondary"
