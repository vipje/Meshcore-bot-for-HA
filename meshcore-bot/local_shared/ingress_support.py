"""Home Assistant ingress support for the bot's web viewer.

Home Assistant shows an add-on's web page in its sidebar through "ingress": the page is served under
a path prefix such as /api/hassio_ingress/<token>/ and the Supervisor strips that prefix before the
request reaches the add-on. It tells the add-on the prefix in the X-Ingress-Path header. The upstream
web viewer uses absolute paths everywhere (href="/contacts", fetch('/api/...'), Socket.IO on
/socket.io, redirects to /login), so behind that prefix nothing would load.

This is one WSGI layer around the viewer that only acts on requests carrying X-Ingress-Path. Requests
without it (the normal http://host:8081 address) pass through completely untouched.

For an ingress request it
  - makes Socket.IO's origin check pass (the browser's Origin is the public Home Assistant address
    while the Host is the internal one; a browser cannot add X-Ingress-Path to a cross-site
    WebSocket, so this does not open the viewer to other websites),
  - asks the viewer not to compress, so the HTML can be rewritten,
  - rewrites absolute paths in HTML pages (href/src/action attributes, location assignments,
    dynamic imports, the Socket.IO client path) and in Location and Set-Cookie headers,
  - serves /_ingress/shim.js, a small script that prefixes absolute URLs used by fetch, XMLHttpRequest,
    EventSource, history and clicked links/forms, which covers the paths built inside JavaScript.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

SHIM_PATH = "/_ingress/shim.js"

# The prefix is only ever used inside HTML/JS/headers, so accept a conservative character set and
# treat anything else as "not ingress".
_PREFIX_RE = re.compile(r"^/[A-Za-z0-9_\-./]*$")

_ATTR_RE = re.compile(r"""(\s(?:href|src|action|formaction|poster)\s*=\s*)(["'])/(?!/)""", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"""(\blocation(?:\.href)?\s*=\s*|\blocation\.(?:assign|replace)\(\s*)(["'`])/(?!/)""")
_IMPORT_RE = re.compile(r"""(\bimport\(\s*)(["'`])/(?!/)""")
_IO_RE = re.compile(r"""\bio\(\s*\{""")
_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)

SHIM_JS = r"""(function () {
  var tag = document.currentScript;
  var prefix = tag ? (tag.getAttribute('data-prefix') || '') : '';
  if (!prefix) return;
  function fix(u) {
    if (typeof u !== 'string' || u.charAt(0) !== '/' || u.charAt(1) === '/') return u;
    if (u === prefix || u.indexOf(prefix + '/') === 0) return u;
    return prefix + u;
  }
  var _fetch = window.fetch;
  if (_fetch) {
    window.fetch = function (input, init) {
      if (typeof input === 'string') input = fix(input);
      else if (input && typeof input.url === 'string' && window.Request && input instanceof Request) {
        var path = input.url.indexOf(location.origin) === 0 ? input.url.slice(location.origin.length) : '';
        var fixed = fix(path);
        if (path && fixed !== path) input = new Request(location.origin + fixed, input);
      }
      return _fetch.call(this, input, init);
    };
  }
  var _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    var args = Array.prototype.slice.call(arguments);
    args[1] = fix(url);
    return _open.apply(this, args);
  };
  if (window.EventSource) {
    var ES = window.EventSource;
    window.EventSource = function (url, cfg) { return new ES(fix(url), cfg); };
    window.EventSource.prototype = ES.prototype;
  }
  ['pushState', 'replaceState'].forEach(function (name) {
    var orig = history[name];
    history[name] = function (state, title, url) {
      return orig.call(this, state, title, url == null ? url : fix(String(url)));
    };
  });
  var _winOpen = window.open;
  window.open = function (url) {
    var args = Array.prototype.slice.call(arguments);
    if (typeof url === 'string') args[0] = fix(url);
    return _winOpen.apply(this, args);
  };
  document.addEventListener('click', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
    if (el) { var h = el.getAttribute('href'); var f = fix(h); if (f !== h) el.setAttribute('href', f); }
  }, true);
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (form && form.getAttribute) {
      var a = form.getAttribute('action');
      if (a) { var f = fix(a); if (f !== a) form.setAttribute('action', f); }
    }
  }, true);
})();
"""


def _clean_prefix(raw: Optional[str]) -> str:
    prefix = (raw or "").strip().rstrip("/")
    return prefix if prefix and _PREFIX_RE.match(prefix) else ""


def rewrite_html(html: str, prefix: str) -> str:
    """Point every absolute path in an HTML page at the ingress prefix."""
    html = _ATTR_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{prefix}/", html)
    html = _LOCATION_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{prefix}/", html)
    html = _IMPORT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{prefix}/", html)
    html = _IO_RE.sub(lambda m: f'io({{path: "{prefix}/socket.io", ', html)
    shim = f'<script src="{prefix}{SHIM_PATH}" data-prefix="{prefix}"></script>'
    head = _HEAD_RE.search(html)
    if head:
        return html[:head.end()] + shim + html[head.end():]
    return shim + html


def _fix_location(value: str, prefix: str) -> str:
    if value.startswith("/") and not value.startswith("//") and value != prefix \
            and not value.startswith(prefix + "/"):
        return prefix + value
    return value


def _fix_cookie(value: str, prefix: str) -> str:
    return re.sub(r"(?i)(;\s*path=)/(?=\s*(;|$))", lambda m: f"{m.group(1)}{prefix}/", value)


class IngressMiddleware:
    def __init__(self, app: Callable):
        self.app = app

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        prefix = _clean_prefix(environ.get("HTTP_X_INGRESS_PATH"))
        if not prefix:
            return self.app(environ, start_response)

        if environ.get("PATH_INFO") == SHIM_PATH:
            body = SHIM_JS.encode("utf-8")
            start_response("200 OK", [("Content-Type", "application/javascript; charset=utf-8"),
                                      ("Content-Length", str(len(body))),
                                      ("Cache-Control", "no-cache")])
            return [body]

        # Socket.IO compares the browser's Origin with the request's own address. Through ingress
        # the Origin is the public Home Assistant address, so let it match.
        origin = environ.get("HTTP_ORIGIN")
        if origin:
            parts = urlsplit(origin)
            if parts.scheme in ("http", "https") and parts.netloc:
                environ["HTTP_HOST"] = parts.netloc
                environ["wsgi.url_scheme"] = parts.scheme
        # Uncompressed HTML is needed to rewrite it.
        environ.pop("HTTP_ACCEPT_ENCODING", None)

        captured: List[Any] = []

        def capture(status: str, headers: List[Tuple[str, str]], exc_info: Any = None):
            content_type = next((v for k, v in headers if k.lower() == "content-type"), "")
            fixed: List[Tuple[str, str]] = []
            for name, value in headers:
                lower = name.lower()
                if lower == "location":
                    value = _fix_location(value, prefix)
                elif lower == "set-cookie":
                    value = _fix_cookie(value, prefix)
                fixed.append((name, value))
            if content_type.lower().startswith("text/html"):
                captured.append((status, fixed, exc_info))
                return lambda data: None  # body is collected below
            return start_response(status, fixed, exc_info)

        result = self.app(environ, capture)
        if not captured:
            return result
        try:
            body = b"".join(result)
        finally:
            close = getattr(result, "close", None)
            if close:
                close()
        status, headers, exc_info = captured[0]
        charset = "utf-8"
        for name, value in headers:
            if name.lower() == "content-type" and "charset=" in value.lower():
                charset = value.lower().split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            body = rewrite_html(body.decode(charset), prefix).encode(charset)
        except (UnicodeError, LookupError):
            pass  # not text we can handle: leave the page as it is
        headers = [(k, v) for k, v in headers if k.lower() not in ("content-length", "content-encoding")]
        headers.append(("Content-Length", str(len(body))))
        start_response(status, headers, exc_info)
        return [body]


def install_ingress_support(flask_app: Any) -> None:
    """Wrap the viewer's WSGI app. Call after Flask-SocketIO's init_app, so this layer sits outside it."""
    flask_app.wsgi_app = IngressMiddleware(flask_app.wsgi_app)
