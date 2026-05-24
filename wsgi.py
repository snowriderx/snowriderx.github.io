import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from admin import create_admin_app
from client import create_client_app

admin_app = create_admin_app()
client_app = create_client_app()

# / → client_app, /admin → admin_app
# DispatcherMiddleware strips the /admin prefix before forwarding to admin_app,
# so admin blueprints register at /login, /dashboard, etc. (not /admin/login).
# Nginx and the browser see /admin/login because Nginx prepends the prefix.
application = DispatcherMiddleware(client_app, {"/admin": admin_app})

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    port = int(os.environ.get("PORT", 5001))
    run_simple("127.0.0.1", port, application, use_reloader=True, use_debugger=True)
