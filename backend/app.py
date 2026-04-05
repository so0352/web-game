import os

from flask import Flask, render_template, request
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

from handlers.ai_handlers import register_ai_handlers
from handlers.game_handlers import register_game_handlers
from handlers.matchmaking_handlers import handle_disconnect as handle_match_disconnect
from handlers.matchmaking_handlers import register_matchmaking_handlers
from handlers.move_handlers import register_move_handlers
from game_store import detach_client_game, unregister_client_game

app = Flask(__name__)
_DEFAULT_SECRET_KEY = "othello-secret-key"
_is_production = os.environ.get("APP_ENV", "").lower() == "production"
_configured_secret = os.environ.get("SECRET_KEY", _DEFAULT_SECRET_KEY)
if _is_production and _configured_secret == _DEFAULT_SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in production")

app.config["SECRET_KEY"] = _configured_secret
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
)

allowed_origins_raw = os.environ.get(
    "SOCKETIO_CORS_ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
)
allowed_origins = [
    origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()
]
if _is_production and "*" in allowed_origins:
    raise RuntimeError("SOCKETIO_CORS_ALLOWED_ORIGINS cannot be '*' in production")
if len(allowed_origins) == 1:
    allowed_origins = allowed_origins[0]
socketio = SocketIO(app, cors_allowed_origins=allowed_origins)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:",
    )
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/othello")
def othello():
    return render_template("othello.html")


@app.route("/shogi")
def shogi():
    return render_template("shogi.html")


@socketio.on("connect")
def handle_connect():
    print("Client connected")


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")
    hold_for_reconnect = handle_match_disconnect(socketio, request.sid)
    if hold_for_reconnect:
        detach_client_game(request.sid, allow_cleanup=False)
        return
    unregister_client_game(request.sid)


register_game_handlers(socketio)
register_ai_handlers(socketio)
register_move_handlers(socketio)
register_matchmaking_handlers(socketio)


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(
        app, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=debug_mode
    )
