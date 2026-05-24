# Snow Rider X — Flask + PostgreSQL

Flask web application for Snow Rider X. Server-side rendered with Jinja2, styled with Tailwind CSS, backed by PostgreSQL.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Local Development Setup](#local-development-setup)
- [Running the App](#running-the-app)
- [Tailwind CSS](#tailwind-css)
- [Running Tests](#running-tests)
- [Production Deploy (Ubuntu + Nginx)](#production-deploy-ubuntu--nginx)
- [Environment Variables Reference](#environment-variables-reference)

---

## Architecture

```
Browser / Googlebot
       │
       ▼
   Nginx (port 80/443)
   ├── /static/*        → serve files directly from theme/static/
   ├── /admin/static/*  → serve files directly from admin/static/
   ├── /game/*          → serve game binaries directly from theme/static/game/
   └── /*               → proxy_pass → Gunicorn (127.0.0.1:8002)
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
snowriderx/
├── wsgi.py                    # Entry point — DispatcherMiddleware wiring
├── config.py                  # Config, AdminConfig, ClientConfig (reads .env)
├── extensions.py              # db, login_manager, limiter singletons
├── requirements.txt
├── alembic.ini
├── tailwind.config.js
├── package.json               # Tailwind dev dependency
├── pytest.ini
├── .env.example               # Copy to .env and fill in values
│
├── models/                    # SQLAlchemy models — shared by admin + client
│   ├── config.py              # tblTotal — SiteConfig + TTL cache
│   ├── menu.py                # tblMenu — navigation hierarchy
│   ├── news.py                # tblNews — blog articles
│   ├── link.py                # tblLink — slug → page type router
│   ├── banner.py              # tblAdvert
│   ├── contact.py             # tblContact
│   └── url_redirect.py        # tblURL — 301 redirects
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
│       ├── category.html      # Blog article list with pagination
│       ├── article.html       # Article detail + NewsArticle JSON-LD
│       ├── static_page.html   # Static content pages (about, privacy, etc.)
│       ├── unblocked.html     # /unblocked — noindex
│       ├── contact.html       # Contact page
│       ├── sitemap.xml        # Dynamic XML sitemap
│       ├── 404.html
│       └── macros/
│           └── ads.html       # Ad slots — skipped for Googlebot
│
├── admin/                     # CMS backend — /admin/*
│   ├── __init__.py            # create_admin_app()
│   ├── blueprints/            # One blueprint per resource (news, menu, config…)
│   ├── templates/             # Admin UI (Bootstrap-based)
│   ├── static/                # Admin CSS/JS/uploads
│   └── utils/                 # Upload, HTML sanitisation, auth helpers
│
├── theme/                     # Site-specific assets and config
│   ├── site_config.py         # SITE_NAME, GAME_SRC, feature flags
│   └── static/
│       ├── css/
│       │   ├── input.css      # Tailwind source — edit this
│       │   └── style.css      # Compiled output — gitignored, regenerate on deploy
│       ├── game/snow-rider/   # Unity WebGL game binaries (served by Nginx)
│       ├── uploads/           # Seeded images (blog photos, logo, favicon)
│       ├── manifest.json      # PWA manifest
│       └── sw.js              # Service worker
│
├── migrations/                # Alembic + DB seed scripts
│   ├── env.py
│   └── seed_snowrider.py      # Seeds menus, articles, redirects from production HTML
│
├── tests/
│   ├── unit/                  # Pure function tests — no DB needed
│   ├── integration/           # Flask test client + real PostgreSQL (280 tests)
│   └── e2e/                   # Playwright end-to-end (requires live server)
│
└── deploy/
    ├── nginx/snowriderx.conf      # Nginx virtual host (port 8002, gzip, CSP headers)
    └── systemd/snowriderx.service # systemd service unit
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
git clone https://github.com/snowriderx/snowriderx.github.io.git
cd snowriderx.github.io
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
DATABASE_URL=postgresql://youruser:yourpassword@localhost:5432/snowriderx_pg
SECRET_KEY=your-random-secret-key-here
FLASK_ENV=development
```

Generate a secure `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Create PostgreSQL database and seed data

```bash
createdb snowriderx_pg
python migrations/seed_snowrider.py
```

### 4. Install Tailwind CSS and compile styles

```bash
npm install
npm run build:css
```

---

## Running the App

### Development server

```bash
source .venv/bin/activate
PORT=5002 python wsgi.py
```

- Client site: http://127.0.0.1:5002
- Admin panel: http://127.0.0.1:5002/admin/login

Default admin credentials: set via the admin UI or directly in the DB.

### Verify app starts correctly

```bash
python -c "from wsgi import application; print('OK')"
flask --app wsgi:client_app routes
flask --app wsgi:admin_app routes
```

---

## Tailwind CSS

During development, watch for changes:

```bash
npm run watch:css
```

For production (minified):

```bash
npm run build:css
```

`theme/static/css/style.css` is gitignored — always regenerate on deploy.

---

## Running Tests

Requires a running PostgreSQL database with `DATABASE_URL` set in `.env`.

```bash
# Unit tests (no DB)
pytest tests/unit/ -v

# Integration tests (real PostgreSQL)
pytest tests/integration/ -v

# All tests
pytest tests/unit tests/integration
```

**Do not run integration tests against a production database** — tests create and delete rows.

---

## Production Deploy (Ubuntu + Nginx)

### 1. Install system dependencies

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip \
    postgresql postgresql-client nginx redis-server nodejs npm
```

### 2. Create app user and directory

```bash
sudo useradd -r -s /bin/false deploy
sudo mkdir -p /opt/snowriderx
sudo chown deploy:deploy /opt/snowriderx
```

### 3. Deploy code

```bash
sudo -u deploy git clone https://github.com/snowriderx/snowriderx.github.io.git /opt/snowriderx
cd /opt/snowriderx
sudo -u deploy git checkout flask_jinja2
```

### 4. Create virtual environment and install dependencies

```bash
sudo -u deploy python3.11 -m venv /opt/snowriderx/.venv
sudo -u deploy /opt/snowriderx/.venv/bin/pip install -r requirements.txt
```

### 5. Create `.env`

```bash
sudo -u deploy cp /opt/snowriderx/.env.example /opt/snowriderx/.env
sudo nano /opt/snowriderx/.env
```

Minimum production values:
```env
DATABASE_URL=postgresql://snowriderx:strongpassword@localhost:5432/snowriderx_pg
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
FLASK_ENV=production
COOKIE_SECURE=true
RATELIMIT_STORAGE_URI=redis://localhost:6379/0
```

### 6. Set up PostgreSQL

```bash
sudo -u postgres createuser snowriderx --pwprompt
sudo -u postgres createdb snowriderx_pg --owner=snowriderx
# Then restore a dump from local:
pg_restore -h localhost -U snowriderx -d snowriderx_pg dump.pgdump
```

### 7. Compile Tailwind CSS

```bash
cd /opt/snowriderx
sudo npm install
sudo -u deploy npm run build:css
```

### 8. Set up log directory

```bash
sudo mkdir -p /var/log/snowriderx
sudo chown deploy:deploy /var/log/snowriderx
```

### 9. Install systemd service

```bash
sudo cp deploy/systemd/snowriderx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable snowriderx
sudo systemctl start snowriderx
sudo systemctl status snowriderx
```

### 10. Configure Nginx

```bash
sudo cp deploy/nginx/snowriderx.conf /etc/nginx/sites-available/snowriderx
sudo ln -s /etc/nginx/sites-available/snowriderx /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 11. SSL certificate (when domain is ready)

**Option A — Cloudflare origin certificate** (recommended):
1. Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate
2. Save cert and key, then uncomment the SSL block in `deploy/nginx/snowriderx.conf`

**Option B — Let's Encrypt**:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d snowriderx.com -d www.snowriderx.com
```

### Verify deploy

```bash
# Gunicorn is listening
curl -s http://127.0.0.1:8002/ | head -5

# Nginx responds
curl -I http://snowriderx.com/

# Sitemap is valid
curl -s http://snowriderx.com/sitemap.xml | head -10

# Googlebot gets no ads
curl -sA "Googlebot/2.1" http://snowriderx.com/ | grep -c "box-media"
# should print 0
```

### Update deployment

```bash
cd /opt/snowriderx
sudo -u deploy git pull origin flask_jinja2
sudo -u deploy /opt/snowriderx/.venv/bin/pip install -r requirements.txt
sudo -u deploy npm run build:css
sudo systemctl restart snowriderx
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | `postgresql://user:pass@host:5432/snowriderx_pg` |
| `SECRET_KEY` | Yes | — | Flask session signing key — generate randomly |
| `FLASK_ENV` | No | `production` | `development` enables debug mode and reloader |
| `PORT` | No | `5001` | Port for development server (`python wsgi.py`) |
| `COOKIE_SECURE` | No | `false` | Set `true` in production (HTTPS-only cookies) |
| `RATELIMIT_STORAGE_URI` | No | `memory://` | Use `redis://localhost:6379/0` in production |
| `RATELIMIT_LOGIN` | No | `5 per minute;20 per hour` | Login attempt limits |
| `RATELIMIT_MUTATION` | No | `30 per minute` | Write operation limits |
| `UPLOAD_FOLDER` | No | `admin/static/uploads` | Where uploaded images are stored |
| `MAX_CONTENT_LENGTH_MB` | No | `10` | Max HTTP request size in MB |
| `UPLOAD_MAX_FILE_MB` | No | `5` | Max single file size in MB |
| `IMAGE_BASE_URL` | No | `` | CDN base URL for images (leave blank for local) |

---

## Key Design Decisions

**Why DispatcherMiddleware instead of Blueprints?**
Admin needs Flask-Login, Flask-WTF CSRF, and Flask-Limiter. The public client needs none of these. Separate WSGI apps keep the client lean and eliminate any risk of auth state leaking to public routes.

**Why `theme/` instead of `site/`?**
Python has a built-in module named `site`. Naming the folder `site/` would shadow it and cause hard-to-debug import errors.

**Why PostgreSQL case-sensitive slugs matter?**
SQL Server is case-insensitive by default; PostgreSQL is not. Slugs stored as mixed-case in `tblLink.RowUrl` would 404 on every request. The fix is to `LOWER()` all slugs after import and use a functional index.

**Why no jQuery?**
jQuery is 87 KB. It was only used for three operations: toggling classes, scrolling, and removing DOM nodes. Replaced by an inline ~1 KB vanilla JS shim in `base.html`.
