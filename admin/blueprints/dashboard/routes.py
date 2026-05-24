"""
Dashboard blueprint — post-login landing page for super-admin (IDU=1).
"""

from flask import render_template
from flask_login import login_required
from sqlalchemy import select, func

from admin.blueprints.dashboard import bp
from extensions import db
from models.news import News
from models.user import User
from models.menu import Menu
from models.contact import Contact
from models.comment import Comment
from models.product import Product
from admin.utils.access import super_admin_redirect


@bp.before_request
def _guard():
    return super_admin_redirect()


@bp.route("/")
@bp.route("/dashboard")
@login_required
def index():
    total_news = db.session.execute(
        select(func.count()).select_from(News).where(News.is_active != 99)
    ).scalar_one()

    total_users = db.session.execute(
        select(func.count()).select_from(User).where(User.role == 1, User.IDU != 1)
    ).scalar_one()

    total_products = db.session.execute(
        select(func.count()).select_from(Product).where(Product.is_active != 99)
    ).scalar_one()

    total_contacts = db.session.execute(
        select(func.count()).select_from(Contact).where(Contact.is_read == 0)
    ).scalar_one()

    total_comments = db.session.execute(
        select(func.count()).select_from(Comment).where(Comment.is_show == 0)
    ).scalar_one()

    recent_news = db.session.execute(
        select(News)
        .where(News.is_active != 99)
        .order_by(News.created_at.desc())
        .limit(6)
    ).scalars().all()

    recent_products = db.session.execute(
        select(Product)
        .where(Product.is_active != 99)
        .order_by(Product.created_at.desc())
        .limit(5)
    ).scalars().all()

    recent_contacts = db.session.execute(
        select(Contact)
        .order_by(Contact.created_at.desc())
        .limit(5)
    ).scalars().all()

    stats = {
        "total_news":     total_news,
        "total_users":    total_users,
        "total_products": total_products,
        "total_contacts": total_contacts,
        "total_comments": total_comments,
    }
    return render_template(
        "dashboard/index.html",
        stats=stats,
        recent_news=recent_news,
        recent_products=recent_products,
        recent_contacts=recent_contacts,
    )
