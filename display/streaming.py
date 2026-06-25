"""Serves a lightweight web page for previewing the display remotely, so you
can check what the Pi is showing from a browser on the same network instead
of having to look at the physical screen.

Unlike a continuous video stream, this captures a *single* frame on demand:
the page has a "Capture frame" button that grabs whatever is on screen right
now. Nothing is encoded while nobody is asking for it, which keeps the render
loop free and avoids the steady memory growth a per-frame JPEG encode caused.

The actual JPEG encode runs on the main render thread (the only thread that
may safely touch the live pygame surface) -- the HTTP handler just requests a
frame and waits briefly for it. The page also has prev/next buttons that
enqueue real NavEvents (the same path a touchscreen swipe takes) and an
"Update from GitHub" button.
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

REPO_DIR = Path(__file__).resolve().parent.parent


class FrameCapture:
    """Captures a single snapshot of the latest rendered frame on demand.

    The main loop hands us a reference to the live screen each frame
    (set_source) and calls service_pending() once per frame; the actual
    encode only happens when an HTTP handler has asked for a frame, and it
    happens on the main thread so it never races the renderer. With no
    pending request this is essentially free -- no copy, no encode."""

    def __init__(self, rotate_degrees=0):
        self._rotate_degrees = rotate_degrees
        self._source = None
        self._jpeg = None
        self._jpeg_lock = threading.Lock()
        self._buf = io.BytesIO()  # reused; a fresh BytesIO per encode leaks in SDL_image
        self._requested = threading.Event()
        self._ready = threading.Event()
        self._capture_lock = threading.Lock()  # serialize concurrent capture() callers

    def set_source(self, surface):
        """Called every frame by the main loop -- just stores a reference."""
        self._source = surface

    def service_pending(self):
        """Called every frame by the main loop. Encodes the current frame
        only if an HTTP handler has requested one since the last call."""
        if self._requested.is_set():
            self._requested.clear()
            jpeg = self._encode(self._source)
            with self._jpeg_lock:
                self._jpeg = jpeg
            self._ready.set()

    def _encode(self, surface):
        if surface is None:
            return None
        if self._rotate_degrees:
            surface = pygame.transform.rotate(surface, self._rotate_degrees)
        self._buf.seek(0)
        self._buf.truncate(0)
        pygame.image.save(surface, self._buf, "frame.jpg")
        return self._buf.getvalue()

    def capture(self, timeout=2.0):
        """Called from an HTTP handler thread. Asks the main loop for a fresh
        frame and waits up to `timeout` seconds for it. Returns JPEG bytes, or
        None if no frame was produced in time."""
        with self._capture_lock:
            self._ready.clear()
            self._requested.set()
            if self._ready.wait(timeout):
                with self._jpeg_lock:
                    return self._jpeg
            return None


def _make_handler(capture, nav_queue):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep stdout clean; this runs forever alongside the demo

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._serve_index()
            elif path == "/snapshot":
                self._serve_snapshot()
            elif path == "/nav":
                self._nav()
            elif path == "/update":
                self._update()
            else:
                self.send_error(404)

        def _serve_index(self):
            body = _INDEX_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_snapshot(self):
            jpeg = capture.capture()
            if jpeg is None:
                self.send_error(503, "no frame available")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpeg)

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
    <button onclick="fetch('/nav?dir=prev')" style="font-size:1.5em; padding:0.3em 1em;">&larr; prev</button>
    <button onclick="fetch('/nav?dir=next')" style="font-size:1.5em; padding:0.3em 1em;">next &rarr;</button>
  </p>
  <p>
    <button onclick="capture()" style="font-size:1.2em; padding:0.3em 1em;">&#128247; Capture frame</button>
  </p>
  <img id="frame" alt="press Capture frame to grab the current screen"
       style="max-width:100%; image-rendering:pixelated;">
  <p>
    <button onclick="if(confirm('Pull latest from GitHub and restart the display?')) window.location.href='/update'"
            style="font-size:1em; padding:0.3em 1em;">&#8635; Update from GitHub</button>
  </p>
  <script>
    function capture() {
      fetch('/snapshot', {cache: 'no-store'})
        .then(r => r.ok ? r.blob() : Promise.reject(r.status))
        .then(b => {
          const img = document.getElementById('frame');
          if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
          const url = URL.createObjectURL(b);
          img.dataset.url = url;
          img.src = url;
        })
        .catch(() => {});
    }
  </script>
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


def start_server(capture, port, nav_queue=None):
    """Starts the HTTP server on a daemon thread and returns it (caller
    doesn't need to do anything else -- it shuts down when the process
    exits). Pass the same queue the touch input thread feeds so the page's
    prev/next buttons can enqueue real NavEvents."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(capture, nav_queue))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
