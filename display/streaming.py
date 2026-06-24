"""Serves the live display over HTTP as an MJPEG stream, so you can preview
what the Pi is showing from a browser on the same network instead of having
to look at the physical screen. Runs in a background daemon thread and never
blocks or slows down the main render loop -- it just JPEG-encodes whatever
frame was last handed to it.

Visit http://<pi-ip>:<port>/ for a viewer page with a stream-rate control
and prev/next buttons that drive real navigation in the app (queued the same
way a touchscreen swipe is).
"""

import html
import io
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pygame

from display.manager import NavEvent

MIN_FPS = 1
MAX_FPS = 30
BOUNDARY = "frame"
REPO_DIR = Path(__file__).resolve().parent.parent


class FrameStreamer:
    """Holds the latest frame as JPEG bytes plus the current target stream
    rate, both behind a lock since the HTTP server threads and the main
    render loop all touch them concurrently."""

    def __init__(self, default_fps, rotate_degrees=0):
        self._lock = threading.Lock()
        self._jpeg = None
        self._fps = max(MIN_FPS, min(MAX_FPS, default_fps))
        self._rotate_degrees = rotate_degrees

    def update_frame(self, surface):
        if self._rotate_degrees:
            surface = pygame.transform.rotate(surface, self._rotate_degrees)
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


def _make_handler(streamer, nav_queue):
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
            elif path == "/nav":
                self._nav()
            elif path == "/update":
                self._update()
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

        def _nav(self):
            query = parse_qs(urlparse(self.path).query)
            direction = query.get("dir", [None])[0]
            event = {"next": NavEvent.NEXT, "prev": NavEvent.PREV}.get(direction)
            if event is not None and nav_queue is not None:
                nav_queue.put(event)
            self.send_response(204)
            self.end_headers()

        def _update(self):
            ok, output = _git_pull()
            status = "Updated -- restarting..." if ok else "Update failed"
            body = _UPDATE_HTML.format(status=status, output=html.escape(output)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            if ok:
                # systemd's Restart=always brings the service back up with
                # the new code; exiting (rather than calling systemctl
                # restart ourselves) means this never needs sudo. Delay
                # briefly so the response above actually reaches the client
                # first. Outside the service (e.g. running by hand) this
                # just quits -- nothing restarts it.
                threading.Timer(0.5, lambda: os._exit(0)).start()

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


def _git_pull():
    """Pulls the currently checked-out branch from its origin remote, the
    same way setup/update.sh does -- but without the sudo systemctl restart
    step, since the caller restarts itself instead. Returns (ok, combined
    stdout+stderr) for display on the result page."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        pull = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60,
        )
        output = (pull.stdout + pull.stderr).strip() or "(no output)"
        return pull.returncode == 0, f"$ git pull origin {branch}\n{output}"
    except Exception as exc:
        return False, str(exc)


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
  <p>
    <button onclick="fetch('/nav?dir=prev')" style="font-size:1.5em; padding:0.3em 1em;">&larr; prev</button>
    <button onclick="fetch('/nav?dir=next')" style="font-size:1.5em; padding:0.3em 1em;">next &rarr;</button>
  </p>
  <img src="/stream" style="max-width:100%; image-rendering:pixelated;">
  <p>
    <button onclick="if(confirm('Pull latest from GitHub and restart the display?')) window.location.href='/update'"
            style="font-size:1em; padding:0.3em 1em;">&#8635; Update from GitHub</button>
  </p>
</body>
</html>
"""

_UPDATE_HTML = """\
<!doctype html>
<html>
<head><title>Updating...</title><meta http-equiv="refresh" content="6;url=/"></head>
<body style="background:#0a0c18; color:#ddd; font-family:sans-serif; text-align:center;">
  <h2>{status}</h2>
  <pre style="text-align:left; display:inline-block; background:#000; color:#9f9;
              padding:1em; max-width:90%; overflow:auto;">{output}</pre>
  <p>Returning to the preview shortly...</p>
</body>
</html>
"""


def start_server(streamer, port, nav_queue=None):
    """Starts the HTTP server on a daemon thread and returns it (caller
    doesn't need to do anything else -- it shuts down when the process
    exits). Pass the same queue the touch input thread feeds so the page's
    prev/next buttons can enqueue real NavEvents."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(streamer, nav_queue))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
