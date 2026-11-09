"""A small web server, only reachable from this Mac, that feeds the interface."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .actions import installed_apps
from .gestures import APP_GESTURES, SLEEP_GESTURES
from .poses import PINCH_POSE, POSES

UI_FOLDER = Path(__file__).parent / "ui"
UI_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
BOUNDARY = "maestro-frame"


def create_server(engine, port=0):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _is_trusted(self):
            """Stops other websites from reaching the camera feed or changing settings."""
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            site = self.headers.get("Sec-Fetch-Site", "same-origin")
            return host in ALLOWED_HOSTS and site in ("same-origin", "none")

        def _send(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, value):
            self._send(status, json.dumps(value).encode())

        def _start_stream(self, content_type):
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

        def _stream_events(self):
            self._start_stream("text/event-stream")
            seq = -1
            while True:
                seq = engine.wait_for_update(seq)
                self.wfile.write(f"data: {json.dumps(engine.snapshot())}\n\n".encode())
                self.wfile.flush()

        def _stream_video(self):
            self._start_stream(f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            seq = -1
            while True:
                seq = engine.wait_for_update(seq)
                frame = engine.latest_frame()
                if frame is None:
                    continue
                header = f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n"
                self.wfile.write(header.encode() + frame + b"\r\n")
                self.wfile.flush()

        def do_GET(self):
            if not self._is_trusted():
                return self._send_json(403, {"error": "Not allowed"})
            try:
                if self.path == "/events":
                    return self._stream_events()
                if self.path == "/video":
                    return self._stream_video()
            except (BrokenPipeError, ConnectionResetError):
                return None
            if self.path == "/api/setup":
                all_poses = {**POSES, "pinch": PINCH_POSE}
                poses = {name: [point[:2] for point in pose] for name, pose in all_poses.items()}
                return self._send_json(200, {"apps": installed_apps(), "poses": poses})
            if self.path in UI_FILES:
                name, content_type = UI_FILES[self.path]
                return self._send(200, (UI_FOLDER / name).read_bytes(), content_type)
            return self._send_json(404, {"error": "Not found"})

        def _read_json(self):
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return None
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length < 10_000:
                return None
            try:
                value = json.loads(self.rfile.read(length))
            except ValueError:
                return None
            return value if isinstance(value, dict) else None

        def do_POST(self):
            body = self._read_json()
            if not self._is_trusted() or body is None:
                return self._send_json(403, {"error": "Not allowed"})

            if self.path == "/api/listening" and isinstance(body.get("listening"), bool):
                engine.set_listening(body["listening"])
                return self._send_json(200, {"ok": True})

            if self.path == "/api/binding":
                gesture, app = body.get("gesture"), body.get("app")
                # Only real installed apps, so a gesture can't be pointed at anything else.
                if gesture not in APP_GESTURES or app not in installed_apps():
                    return self._send_json(400, {"error": "Choose an app installed on this Mac."})
                engine.set_binding(gesture, app)
                return self._send_json(200, {"ok": True})

            if self.path == "/api/sleep-gesture":
                if body.get("gesture") not in SLEEP_GESTURES:
                    return self._send_json(400, {"error": "Choose one of the sleep gestures."})
                engine.set_sleep_gesture(body["gesture"])
                return self._send_json(200, {"ok": True})

            if self.path == "/api/cursor-permission":
                engine.request_cursor_permission()
                return self._send_json(200, {"ok": True})

            if self.path == "/api/retry-camera":
                engine.retry_camera()
                return self._send_json(200, {"ok": True})

            return self._send_json(404, {"error": "Not found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
