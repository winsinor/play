"""Serves the live display over HTTP as an MJPEG stream, so you can preview
what the Pi is showing from a browser on the same network instead of having
to look at the physical screen. Runs in a background daemon thread and never
blocks or slows down the main render loop -- it just JPEG-encodes whatever
frame was last handed to it.

Visit http://<pi-ip>:<port>/ for a viewer page with a stream-rate control.
"""

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pygame

MIN_FPS = 1
MAX_FPS = 30
BOUNDARY = "frame"


class FrameStreamer:
    """Holds the latest frame as JPEG bytes plus the current target stream
    rate, both behind a lock since the HTTP server threads and the main
    render loop all touch them concurrently."""

    def __init__(self, default_fps):
        self._lock = threading.Lock()
        self._jpeg = None
        self._fps = max(MIN_FPS, min(MAX_FPS, default_fps))

    def update_frame(self, surface):
        buf = io.BytesIO()
        pygame.image.save(surface, buf, "frame.jpg")
        with self._lock:
            self._jpeg = buf.getvalue()

    def latest_jpeg(self):
        with self._lock:
            return self._jpeg

    @property
    def fps(self):
        with self._lock:
            return self._fps

    @fps.setter
    def fps(self, value):
        with self._lock:
            self._fps = max(MIN_FPS, min(MAX_FPS, value))


def _make_handler(streamer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep stdout clean; this runs forever alongside the demo

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._serve_index()
            elif path == "/stream":
                self._serve_stream()
            elif path == "/fps":
                self._set_fps()
            else:
                self.send_error(404)

        def _serve_index(self):
            body = _INDEX_HTML.format(fps=streamer.fps, min_fps=MIN_FPS, max_fps=MAX_FPS).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _set_fps(self):
            query = parse_qs(urlparse(self.path).query)
            value = query.get("value", [None])[0]
            if value is not None:
                try:
                    streamer.fps = int(value)
                except ValueError:
                    pass
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def _serve_stream(self):
            self.send_response(200)
            self.send_header(
                "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            self.end_headers()
            try:
                while True:
                    jpeg = streamer.latest_jpeg()
                    if jpeg is not None:
                        self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                    threading.Event().wait(1.0 / streamer.fps)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client closed the page/tab -- nothing to clean up

    return Handler


_INDEX_HTML = """\
<!doctype html>
<html>
<head><title>Idle Display Preview</title></head>
<body style="background:#0a0c18; color:#ddd; font-family:sans-serif; text-align:center;">
  <p>
    <form action="/fps" method="get" style="display:inline;">
      stream rate:
      <input type="range" name="value" min="{min_fps}" max="{max_fps}" value="{fps}"
             onchange="this.form.submit()">
      {fps} fps
    </form>
  </p>
  <img src="/stream" style="max-width:100%; image-rendering:pixelated;">
</body>
</html>
"""


def start_server(streamer, port):
    """Starts the HTTP server on a daemon thread and returns it (caller
    doesn't need to do anything else -- it shuts down when the process
    exits)."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(streamer))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
