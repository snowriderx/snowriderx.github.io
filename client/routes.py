import os
from datetime import datetime

from flask import (
    Blueprint, abort, make_response, redirect, render_template,
    request, url_for, Response,
)
from sqlalchemy import func, select

from extensions import db
from models.config import get_site_config
from models.link import Link
from models.menu import Menu
from models.news import News
from models.product import Product
from models.url_redirect import find_redirect
from models.contact import Contact
from client.helpers import is_googlebot, get_breadcrumb
from client.theme_config import tc
import client.context_processors as _ctx

bp = Blueprint("client", __name__)


# ── Legacy VB.NET image path redirects → /static/uploads/ ────────────────────
# Old paths from VB.NET are stored in DB and referenced in templates.
# 301 redirect keeps SEO value and works without touching the DB.

@bp.route("/uploads/<path:filename>")
def legacy_uploads(filename):
    return redirect(f"/static/uploads/media/{filename}", 301)


@bp.route("/Uploads/images/<path:filename>")
def legacy_uploads_images(filename):
    return redirect(f"/static/uploads/images/{filename}", 301)


@bp.route("/Uploads/<path:filename>")
def legacy_uploads_upper(filename):
    return redirect(f"/static/uploads/{filename}", 301)


@bp.route("/images/news/<path:filename>")
def legacy_images_news(filename):
    return redirect(f"/static/uploads/news/{filename}", 301)


@bp.route("/images/<path:filename>")
def legacy_images(filename):
    return redirect(f"/static/uploads/images/{filename}", 301)


# ── 301 redirect middleware ───────────────────────────────────────────────────

@bp.before_request
def handle_301_redirects():
    """Query tblURL for old→new URL mappings — mirrors VB tblURL check."""
    path = request.path
    skip_prefixes = ("/static", "/favicon")
    skip_exact = ("/sitemap.xml", "/robots.txt", "/ads.txt")
    if any(path.startswith(p) for p in skip_prefixes) or path in skip_exact:
        return None
    new_url = find_redirect(path)
    if new_url:
        return redirect(new_url, 301)


# ── Home ─────────────────────────────────────────────────────────────────────

@bp.route("/")
def home():
    cfg = get_site_config()
    googlebot = is_googlebot()
    game_src = tc.GAME_SRC
    referrerpolicy = tc.IFRAME_REFERRERPOLICY

    schema_org_json = cfg.script_home if cfg and cfg.script_home else ""

    # content_home: prefer tblTotal.ContentHome; fall back to first active
    # product's DescP (mirrors VB6 where home = game ID=1, "Escape Road").
    content_home = cfg.content_home if cfg else ""
    if not content_home and tc.HAS_PRODUCTS:
        first_product = db.session.execute(
            select(Product).where(Product.is_active != 0).limit(1)
        ).scalar_one_or_none()
        if first_product:
            content_home = first_product.desc or ""
            game_src = game_src or (
                f"/static/game/{first_product.locale or first_product.slug}/index.html?v=1.2.1"
                if (first_product.locale or first_product.slug) else ""
            )

    return render_template(
        "home.html",
        page_title=cfg.meta_title if cfg else "",
        meta_keywords=cfg.meta_keyword if cfg else "",
        meta_description=cfg.meta_description if cfg else "",
        content_home=content_home,
        script_home="",
        schema_org_json=schema_org_json,
        game_src=game_src,
        iframe_referrerpolicy=referrerpolicy,
        is_googlebot=googlebot,
        canonical_url=request.host_url.rstrip("/"),
    )


# ── Slug router ───────────────────────────────────────────────────────────────

@bp.route("/<path:slug>")
def page_router(slug: str):
    """
    Central router — replicates Default.aspx.vb LoadID().
    Dispatches on tblLink.RowType (typed):
      1 → category page
      2 → article detail
      3 → game/product page (escaperoadx only)
    """
    slug = slug.split("?")[0].lower().strip("/")

    # Special named routes
    if slug == "unblocked":
        return _render_unblocked()
    if slug == "noads":
        return _render_noads()

    link = db.session.execute(
        select(Link)
        .where(func.lower(Link.row_url) == slug)
        .limit(1)
    ).scalar_one_or_none()

    if link is None:
        abort(404)

    googlebot = is_googlebot()
    row_type = link.row_type

    if row_type == 1:
        return _render_category(link, googlebot)
    elif row_type == 2:
        return _render_article(link, googlebot)
    elif row_type == 3:
        return _render_game(link, googlebot)
    else:
        abort(404)


# ── Category (typed=1) ────────────────────────────────────────────────────────

def _render_category(link: Link, googlebot: bool):
    idm = link.row_idm or ""

    menu = db.session.execute(
        select(Menu).where(Menu.IDM == idm)
    ).scalar_one_or_none()

    # type_m=0 → static page: render desc_m as article content
    if menu and menu.type_m == 0:
        return render_template(
            "static_page.html",
            menu=menu,
            link=link,
            is_googlebot=googlebot,
            page_title=link.row_name or menu.name,
            meta_keywords=menu.keywords if menu.keywords else "",
            meta_description=menu.description if menu.description else "",
            canonical_url=f"{request.host_url.rstrip('/')}/{link.row_url}",
            ischema=menu.ischema if menu else "",
        )

    page = request.args.get("page", 1, type=int)
    per_page = 15

    # IDM prefix length determines article scope
    if idm.endswith("0000"):
        prefix_len = 2
    elif idm.endswith("00"):
        prefix_len = 4
    else:
        prefix_len = 6

    base_q = (
        select(News)
        .join(Menu, News.menu_id == Menu.IDM)
        .where(
            Menu.is_active != 0,
            News.is_active != 0,
            func.left(News.menu_id, prefix_len) == idm[:prefix_len],
        )
        .order_by(News.created_at.desc())
    )
    total = db.session.execute(
        select(func.count()).select_from(base_q.subquery())
    ).scalar() or 0
    articles = db.session.execute(
        base_q.offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    breadcrumb = get_breadcrumb(idm)

    base_url = f"{request.host_url.rstrip('/')}/{link.row_url}"
    # page=1 canonical = bare URL (no ?page=), avoid duplicate content
    canonical = base_url if page == 1 else f"{base_url}?page={page}"

    return render_template(
        "category.html",
        link=link,
        menu=menu,
        articles=articles,
        page=page,
        total=total,
        per_page=per_page,
        breadcrumb=breadcrumb,
        is_googlebot=googlebot,
        page_title=link.row_name or (menu.name if menu else ""),
        meta_keywords=menu.keywords if menu and menu.keywords else "",
        meta_description=menu.description if menu and menu.description else "",
        canonical_url=canonical,
        base_url=base_url,
        ischema=menu.ischema if menu else "",
    )


# ── Article (typed=2) ─────────────────────────────────────────────────────────

def _render_article(link: Link, googlebot: bool):
    news = db.session.execute(
        select(News)
        .where(func.lower(News.slug) == (link.row_url or "").lower(), News.is_active != 0)
    ).scalar_one_or_none()

    if news is None:
        abort(404)

    # TypeN=2 → raw HTML landing page (pass-through, mirrors VB)
    if news.news_type == 2:
        return Response(news.desc or "", mimetype="text/html")

    idm = link.row_idm or ""
    lvl = link.row_levels or 1
    prefix_len = min(lvl * 2, 6)

    related = db.session.execute(
        select(News)
        .join(Menu, News.menu_id == Menu.IDM)
        .where(
            Menu.is_active != 0,
            News.is_active != 0,
            func.left(News.menu_id, prefix_len) == idm[:prefix_len],
            News.ID != news.ID,
        )
        .order_by(News.created_at.desc())
        .limit(10)
    ).scalars().all()

    breadcrumb = get_breadcrumb(idm)

    canonical = f"{request.host_url.rstrip('/')}/{link.row_url}"
    # Use article's own thumbnail for og:image (same as VB6 /images/news/{ImgN})
    og_image = ""
    if news.img and news.img != "null.gif":
        og_image = f"/images/news/{news.img}"

    return render_template(
        "article.html",
        news=news,
        related=related,
        link=link,
        breadcrumb=breadcrumb,
        is_googlebot=googlebot,
        page_title=news.title or news.name,
        meta_keywords=news.keywords or "",
        meta_description=news.description or "",
        canonical_url=canonical,
        page_lang="vi-vn",
        og_image=og_image,
    )


# ── Game / Product (typed=3, escaperoadx only) ────────────────────────────────

def _render_game(link: Link, googlebot: bool):
    if not tc.HAS_PRODUCTS:
        abort(404)

    product = db.session.get(Product, link.row_id)
    if product is None:
        abort(404)

    game_folder = product.locale or product.slug
    if not game_folder or game_folder not in _ctx._VALID_GAME_FOLDERS:
        abort(404)

    product_game_src = f"/static/game/{game_folder}/index.html?v=1.2.1"

    # Use game's own image for og:image (VB6: /images/pro/{Img1P})
    og_image = ""
    if product.img1 and product.img1 != "null.gif":
        og_image = f"/images/pro/{product.img1}"
    elif product.img and product.img != "null.gif":
        og_image = f"/images/pro/{product.img}"

    return render_template(
        "game.html",
        product=product,
        link=link,
        game_src=product_game_src,
        iframe_referrerpolicy=tc.IFRAME_REFERRERPOLICY,
        is_googlebot=googlebot,
        page_title=product.title or product.name,
        meta_keywords=product.keywords or "",
        meta_description=product.description or "",
        canonical_url=f"{request.host_url.rstrip('/')}/{link.row_url}",
        og_image=og_image,
        product_schema=product.script or "",
    )


# ── Unblocked ─────────────────────────────────────────────────────────────────

def _render_unblocked():
    title = f"Play {tc.SITE_NAME} Unblocked — No Ads, Free"
    resp = make_response(render_template(
        "unblocked.html",
        page_title=title,
        meta_description=title,
        no_robots=True,
        is_noads=True,
        is_googlebot=is_googlebot(),
        game_src=tc.GAME_SRC,
        iframe_referrerpolicy=tc.IFRAME_REFERRERPOLICY,
        canonical_url=f"{request.host_url.rstrip('/')}/unblocked",
    ))
    return resp


# ── NoAds (tinyfishing only) ──────────────────────────────────────────────────

def _render_noads():
    if not tc.HAS_NOADS:
        abort(404)

    cfg = get_site_config()
    title = f"Play {tc.SITE_NAME} — No Ads"
    return render_template(
        "home.html",
        page_title=title,
        meta_description=title,
        content_home=cfg.content_home if cfg else "",
        script_home="",
        is_noads=True,
        is_googlebot=is_googlebot(),
        game_src=tc.GAME_SRC,
        game_delay_ms=tc.GAME_DELAY_MS,
        canonical_url=f"{request.host_url.rstrip('/')}/noads",
    )


# ── Sitemap ───────────────────────────────────────────────────────────────────

@bp.route("/sitemap.xml")
def sitemap():

    menus = db.session.execute(
        select(Menu.slug)
        .where(Menu.is_active != 0, Menu.type_m != 1, Menu.lang == 1)
    ).scalars().all()

    products = []
    if tc.HAS_PRODUCTS:
        all_products = db.session.execute(
            select(Product.slug, Product.locale, Product.created_at)
            .where(Product.is_active != 0)
            .order_by(Product.created_at.desc())
        ).all()
        products = [
            {"slug": row.locale or row.slug, "lastmod": row.created_at}
            for row in all_products
            if (row.locale or row.slug) and (row.locale or row.slug) in _ctx._VALID_GAME_FOLDERS
        ]

    news_rows = db.session.execute(
        select(News.slug, News.updated_at, News.created_at)
        .join(Menu, News.menu_id == Menu.IDM)
        .where(News.is_active != 0, Menu.is_active != 0)
        .order_by(News.created_at.desc())
    ).all()

    xml = render_template(
        "sitemap.xml",
        menus=menus,
        products=products,
        news_rows=news_rows,
        domain=request.host,
    )
    return Response(xml, mimetype="application/xml")


# ── PWA files (served from VB6 root) ─────────────────────────────────────────

@bp.route("/manifest.json")
def manifest_json():
    return send_from_directory(_VB6_ROOT, "manifest.json")


@bp.route("/sw.js")
def sw_js():
    return send_from_directory(_VB6_ROOT, "sw.js", mimetype="application/javascript")


# ── Robots / Ads.txt ─────────────────────────────────────────────────────────

@bp.route("/robots.txt")
def robots():
    cfg = get_site_config()
    content = cfg.robots if cfg and cfg.robots else "User-agent: *\nAllow: /\n"
    return Response(content, mimetype="text/plain")


@bp.route("/ads.txt")
def ads_txt():
    cfg = get_site_config()
    return Response(cfg.ads or "", mimetype="text/plain")


# ── Contact (snowrider only) ──────────────────────────────────────────────────

@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if not tc.HAS_CONTACT_FORM:
        # Fall through to page_router — contact may be a static page in tblLink
        return page_router("contact")

    error = None
    success = False

    if request.method == "POST":
        # Honeypot — bots fill hidden "website" field
        if request.form.get("website"):
            return redirect(url_for("client.contact"))

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        content = request.form.get("content", "").strip()

        if not name or not email or not content:
            error = "Vui lòng điền đầy đủ thông tin."
        else:
            record = Contact(
                name_c=name,
                email_c=email,
                content_c=content,
                time_c=datetime.utcnow(),
                is_read=0,
            )
            db.session.add(record)
            db.session.commit()
            success = True

    return render_template(
        "contact.html",
        error=error,
        success=success,
        page_title="Contact Us",
        is_googlebot=is_googlebot(),
    )
