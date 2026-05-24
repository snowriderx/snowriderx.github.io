# Escape Road X — Flask + PostgreSQL

Flask web application for [escaperoadx.com](https://escaperoadx.com). Server-side rendered with Jinja2, styled with Tailwind CSS, backed by PostgreSQL. Replaces the legacy VB.NET/IIS stack.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Local Development Setup](#local-development-setup)
- [Running the App](#running-the-app)
- [Tailwind CSS](#tailwind-css)
- [Running Tests](#running-tests)
- [Adapting for Another Site](#adapting-for-another-site)
- [Production Deploy (Ubuntu + Nginx)](#production-deploy-ubuntu--nginx)
- [Environment Variables Reference](#environment-variables-reference)

---

## Architecture

```
Browser / Googlebot
       │
       ▼
   Nginx (port 443)
   ├── /static/*        → serve files directly from theme/static/
   ├── /admin/static/*  → serve files directly from admin/static/
   ├── /game/*          → serve game binaries directly from theme/static/game/
   └── /*               → proxy_pass → Gunicorn (127.0.0.1:8001)
                                │
                                ▼
                     DispatcherMiddleware (wsgi.py)
                     ├── /admin/* → admin_app  (Flask-Login, CSRF, rate limiting)
                     └── /*       → client_app (public, read-only, no auth)
```

Both apps share the **same PostgreSQL database** via a single `SQLAlchemy` instance in `extensions.py`. The client app is pure read-only SSR — no sessions, no CSRF, no login. The admin app handles all content management.

---

## Project Structure

```
escaperoadx/
├── wsgi.py                    # Entry point — DispatcherMiddleware wiring
├── config.py                  # Config, AdminConfig, ClientConfig (reads .env)
├── extensions.py              # db, login_manager, limiter singletons
├── requirements.txt
├── alembic.ini                # Alembic config (sqlalchemy.url set via env)
├── tailwind.config.js
├── package.json               # Tailwind dev dependency
├── pytest.ini
├── .env.example               # Copy to .env and fill in values
│
├── models/                    # SQLAlchemy models — shared by admin + client
│   ├── __init__.py            # Re-exports all models
│   ├── config.py              # tblTotal — SiteConfig + TTL cache
│   ├── menu.py                # tblMenu — navigation hierarchy
│   ├── news.py                # tblNews — articles
│   ├── product.py             # tblPro  — game series
│   ├── link.py                # tblLink — slug → page type router
│   ├── banner.py              # tblAdvert
│   ├── contact.py             # tblContact
│   ├── url_redirect.py        # tblURL — 301 redirects
│   ├── user.py                # tblUser
│   ├── comment.py             # tblComment
│   ├── intro.py               # tblIntro
│   ├── lang.py                # tblLang
│   ├── permission.py          # tblPermissions
│   ├── tab.py                 # tblTab
│   └── tag.py                 # tblTag
│
├── client/                    # Public-facing website
│   ├── __init__.py            # create_client_app()
│   ├── routes.py              # /, /<slug>, /sitemap.xml, /robots.txt, /ads.txt
│   ├── helpers.py             # is_googlebot(), get_breadcrumb()
│   ├── context_processors.py  # Nav/footer menus, site config (5-min cache)
│   ├── theme_config.py        # Loads theme/site_config.py into a typed object
│   └── templates/
│       ├── base.html          # Master layout — nav, footer, SEO meta, PWA
│       ├── home.html          # Home page — game iframe + content
│       ├── game.html          # Game series page (typed=3)
│       ├── category.html      # Article list with pagination (typed=1)
│       ├── article.html       # Article detail + NewsArticle JSON-LD (typed=2)
│       ├── static_page.html   # Static content page (about, privacy, etc.)
│       ├── unblocked.html     # /unblocked — noindex
│       ├── contact.html       # Contact form (optional per site)
│       ├── sitemap.xml        # Dynamic XML sitemap with <lastmod>
│       ├── 404.html
│       ├── 500.html
│       └── macros/
│           ├── ads.html       # Ad slots — skipped for Googlebot
│           ├── seo.html       # Schema.org JSON-LD, canonical, og tags
│           └── game_iframe.html  # Game iframe with optional delay
│
├── admin/                     # CMS backend — /admin/*
│   ├── __init__.py            # create_admin_app()
│   ├── blueprints/            # One blueprint per resource
│   │   ├── auth/              # Login, logout, change password
│   │   ├── dashboard/
│   │   ├── news/              # Articles CRUD
│   │   ├── menu/              # Navigation CRUD
│   │   ├── product/           # Game series CRUD
│   │   ├── config/            # Site settings (SiteConfig)
│   │   ├── banner/            # Banners/Adverts
│   │   ├── advertc/           # Ad code snippets
│   │   ├── urlredirect/       # 301 redirects
│   │   ├── tag/, tab/, lang/  # Taxonomies
│   │   ├── users/, permissions/
│   │   ├── contact/, comment/
│   │   ├── template/, layout/
│   │   ├── urlmgmt/
│   │   └── api/               # Internal JSON API
│   ├── templates/             # Admin UI (Bootstrap-based)
│   ├── static/                # Admin CSS/JS/uploads
│   └── utils/                 # upload, html sanitisation, auth helpers
│
├── theme/                     # Site-specific assets and config
│   ├── site_config.py         # SITE_NAME, GAME_SRC, feature flags per site
│   ├── images/                # Static images served by Nginx
│   └── static/
│       ├── css/
│       │   ├── input.css      # Tailwind source — edit this
│       │   └── style.css      # Compiled output — gitignored, regenerate
│       ├── js/
│       │   └── bootstrap.bundle.min.js
│       ├── game/              # Unity WebGL game binaries (served by Nginx)
│       ├── icons/             # PWA icons
│       ├── manifest.json      # PWA manifest
│       ├── sw.js              # Service worker
│       └── uploads/           # User-uploaded images (gitignored)
│
├── migrations/                # Alembic migration scripts + DB seed scripts
│   ├── env.py
│   ├── script.py.mako
│   └── migrate_mssql_to_pg.py # One-time migration from SQL Server
│
├── tests/
│   ├── unit/                  # Pure function tests — no DB needed
│   │   ├── conftest.py
│   │   ├── test_auth_utils.py
│   │   ├── test_html.py
│   │   ├── test_text.py
│   │   └── test_upload.py
│   ├── integration/           # Flask test client + real PostgreSQL
│   │   ├── conftest.py
│   │   ├── test_smoke.py
│   │   ├── test_auth.py
│   │   ├── test_client_routes.py
│   │   ├── test_news_crud.py
│   │   ├── test_product_crud.py
│   │   └── ... (15 more test files)
│   └── e2e/                   # Playwright end-to-end (requires live server)
│       ├── conftest.py
│       ├── test_login.py
│       └── test_news_e2e.py
│
└── deploy/
    ├── nginx/escaperoadx.conf     # Nginx virtual host config
    └── systemd/escaperoadx.service  # systemd service unit
```

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| Node.js | 18+ (Tailwind CSS only) |
| Redis | 7+ (production only, for rate limiting) |

---

## Local Development Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/XoanTransf/escaperoadx.git
cd escaperoadx
git checkout flask_jinja2

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` — minimum required:

```env
DATABASE_URL=postgresql://youruser:yourpassword@localhost:5432/escaperoadx_pg
SECRET_KEY=your-random-secret-key-here
FLASK_ENV=development
```

Generate a secure `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Create PostgreSQL database

```bash
createdb escaperoadx_pg
```

If migrating from SQL Server, run the migration script:
```bash
python migrations/migrate_mssql_to_pg.py
```

Then apply any pending Alembic migrations:
```bash
alembic upgrade head
```

After data import, normalise slugs for PostgreSQL case sensitivity:
```sql
UPDATE "tblLink" SET "RowUrl" = LOWER("RowUrl");
CREATE INDEX IF NOT EXISTS ix_tbllink_rowurl ON "tblLink" (LOWER("RowUrl"));
```

### 4. Install Tailwind CSS and compile styles

```bash
npm install
npx tailwindcss -i ./theme/static/css/input.css -o ./theme/static/css/style.css
```

---

## Running the App

### Development server

```bash
source .venv/bin/activate
python wsgi.py
```

- Client site: http://127.0.0.1:5001
- Admin panel: http://127.0.0.1:5001/admin/login

### Using Flask CLI

```bash
flask --app wsgi:client_app run --port 5001
```

Check registered routes:
```bash
flask --app wsgi:client_app routes
flask --app wsgi:admin_app routes
```

Verify the app imports without error:
```bash
python -c "from wsgi import application; print('OK')"
```

---

## Tailwind CSS

During development, watch for changes and auto-recompile:

```bash
npx tailwindcss -i ./theme/static/css/input.css -o ./theme/static/css/style.css --watch
```

For production, minify output:

```bash
npx tailwindcss -i ./theme/static/css/input.css -o ./theme/static/css/style.css --minify
```

`theme/static/css/style.css` is gitignored — always regenerate it on deploy.

---

## Running Tests

Tests require a running PostgreSQL database with `DATABASE_URL` set in `.env`.

### Unit tests (no DB required)

```bash
pytest tests/unit/ -v
```

### Integration tests (requires PostgreSQL)

```bash
pytest tests/integration/ -v
```

Integration tests use the **real database**. Each test cleans up rows it creates (rows prefixed with `[TEST]` are deleted after each test). **Do not run against a production database.**

### All tests

```bash
pytest
```

### Run a specific test file

```bash
pytest tests/integration/test_client_routes.py -v
pytest tests/unit/test_html.py -v
```

---

## Adapting for Another Site

This repo is the **Escape Road X template**. To use it for Snow Rider, Slice Master, or Tiny Fishing, change only `theme/site_config.py` and the `.env`:

**`theme/site_config.py`** — site identity and feature flags:

```python
# Snow Rider X example
SITE_NAME = "Snow Rider X"
GAME_NAME = "Snow Rider"
GAME_SRC = "/static/game/snow-rider/index.html"
SCHEMA_TYPE = "VideoGame"
HAS_PRODUCTS = False        # no series dropdown
HAS_NOADS = False
HAS_CONTACT_FORM = True     # enables /contact route
GAME_DELAY_MS = 0
CACHE_BUSTER_TYPE = "none"
```

```python
# Slice Master example
SITE_NAME = "Slice Master"
GAME_NAME = "Slice Master"
GAME_SRC = "https://game-hub.nyc3.cdn.digitaloceanspaces.com/slice-master/index.html"
HAS_PRODUCTS = False
GAME_DELAY_MS = 2000        # show placeholder for 2s before loading iframe
```

```python
# Tiny Fishing example
SITE_NAME = "Tiny Fishing"
GAME_NAME = "Tiny Fishing"
GAME_SRC = "/static/game/2025/index.html"
HAS_NOADS = True            # enables /noads route
CACHE_BUSTER_TYPE = "session_storage_daily"   # appends ?v=YYYYMMDD to iframe src
```

**`.env`** — point to the correct database and pick a unique port:

| Site | Port | Database |
|------|------|----------|
| Escape Road X | 8001 | escaperoadx_pg |
| Snow Rider X | 8002 | snowriderx_pg |
| Slice Master | 8003 | slicemaster_pg |
| Tiny Fishing | 8004 | tinyfishing_pg |

---

## Production Deploy (Ubuntu + Nginx)

### 1. Set up the server

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip \
    postgresql postgresql-client nginx redis-server
```

### 2. Create app directory and user

```bash
sudo mkdir -p /opt/escaperoadx
sudo chown www-data:www-data /opt/escaperoadx
```

### 3. Deploy code

```bash
cd /opt/escaperoadx
sudo -u www-data git clone https://github.com/XoanTransf/escaperoadx.git .
sudo -u www-data git checkout flask_jinja2
```

### 4. Create virtual environment and install dependencies

```bash
sudo -u www-data python3.11 -m venv .venv
sudo -u www-data .venv/bin/pip install -r requirements.txt
```

### 5. Create `.env`

```bash
sudo -u www-data cp .env.example .env
sudo -u www-data nano .env
```

Set at minimum:
```env
DATABASE_URL=postgresql://escaperoadx:strongpassword@localhost:5432/escaperoadx_pg
SECRET_KEY=<output of: python3 -c "import secrets; print(secrets.token_hex(32))">
FLASK_ENV=production
COOKIE_SECURE=true
RATELIMIT_STORAGE_URI=redis://localhost:6379/0
```

### 6. Compile Tailwind CSS

```bash
sudo npm install -g tailwindcss
sudo -u www-data npx tailwindcss \
    -i ./theme/static/css/input.css \
    -o ./theme/static/css/style.css --minify
```

### 7. Set up log directory

```bash
sudo mkdir -p /var/log/escaperoadx
sudo chown www-data:www-data /var/log/escaperoadx
```

### 8. Install systemd service

```bash
sudo cp deploy/systemd/escaperoadx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable escaperoadx
sudo systemctl start escaperoadx
sudo systemctl status escaperoadx
```

### 9. Configure Nginx

```bash
sudo cp deploy/nginx/escaperoadx.conf /etc/nginx/sites-available/escaperoadx
sudo ln -s /etc/nginx/sites-available/escaperoadx /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 10. SSL certificate

**Option A — Cloudflare origin certificate** (recommended if using Cloudflare):
1. Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate
2. Save cert to `/etc/ssl/escaperoadx/cert.pem` and key to `/etc/ssl/escaperoadx/key.pem`

**Option B — Let's Encrypt (certbot)**:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d escaperoadx.com -d www.escaperoadx.com
```
Then update the `ssl_certificate` paths in `deploy/nginx/escaperoadx.conf` to the certbot paths.

### Verify deploy

```bash
# App process is running
sudo systemctl status escaperoadx

# Gunicorn is listening
curl -s http://127.0.0.1:8001/ | head -5

# HTTPS responds
curl -I https://escaperoadx.com/

# Admin panel is accessible
curl -I https://escaperoadx.com/admin/login

# Sitemap is valid
curl -s https://escaperoadx.com/sitemap.xml | head -10

# Googlebot gets no ads (check: no .box-media in response)
curl -sA "Googlebot/2.1" https://escaperoadx.com/ | grep -c "box-media"
# should print 0
```

### Update deployment

```bash
cd /opt/escaperoadx
sudo -u www-data git pull origin flask_jinja2
sudo -u www-data .venv/bin/pip install -r requirements.txt
# Recompile CSS if templates changed:
sudo -u www-data npx tailwindcss \
    -i ./theme/static/css/input.css \
    -o ./theme/static/css/style.css --minify
sudo systemctl restart escaperoadx
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | `postgresql://user:pass@host:5432/dbname` |
| `SECRET_KEY` | Yes | — | Flask session signing key — generate randomly |
| `FLASK_ENV` | No | `production` | `development` enables debug mode and reloader |
| `COOKIE_SECURE` | No | `false` | Set `true` in production (HTTPS only cookies) |
| `RATELIMIT_STORAGE_URI` | No | `memory://` | Use `redis://localhost:6379/0` in production |
| `RATELIMIT_LOGIN` | No | `5 per minute;20 per hour` | Login attempt limits |
| `RATELIMIT_MUTATION` | No | `30 per minute` | Write operation limits |
| `UPLOAD_FOLDER` | No | `admin/static/uploads` | Where uploaded images are stored |
| `MAX_CONTENT_LENGTH_MB` | No | `10` | Max HTTP request size in MB |
| `UPLOAD_MAX_FILE_MB` | No | `5` | Max single file size in MB |
| `IMAGE_BASE_URL` | No | `` | CDN base URL for images (leave blank for local) |
| `SITE_NAME` | No | `` | Overrides `theme/site_config.py` SITE_NAME if set |

---

## Key Design Decisions

**Why DispatcherMiddleware instead of Blueprints?**
Admin needs Flask-Login, Flask-WTF CSRF, and Flask-Limiter. The public client needs none of these. Separate WSGI apps keep the client lean and eliminate any risk of auth state leaking to public routes.

**Why `theme/` instead of `site/`?**
Python has a built-in module named `site`. Naming the folder `site/` would shadow it and cause hard-to-debug import errors.

**Why PostgreSQL case-sensitive slugs matter?**
SQL Server is case-insensitive by default; PostgreSQL is not. Slugs stored as mixed-case in `tblLink.RowUrl` would 404 on every request. The fix is to `LOWER()` all slugs after import and use a functional index.

**Why no jQuery?**
jQuery is 87 KB. It was only used for three operations: toggling classes, scrolling, and removing DOM nodes. These are replaced by an inline ~1 KB vanilla JS shim in `base.html`, improving page load time and Core Web Vitals score.
