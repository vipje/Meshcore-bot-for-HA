#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot web viewer.

Runs once during the Docker build (see patch_webviewer.py for the shared rationale/mechanics).

Hooks modules/ingress_support.py (copied in by the Dockerfile) into the viewer, so the dashboard also
works inside Home Assistant's sidebar (ingress, which serves it under a path prefix). The layer only acts
on requests that carry the X-Ingress-Path header; the normal address on the viewer port is unchanged.
It is installed right after Flask-SocketIO's init_app, so it wraps the whole WSGI stack.

It also lets the viewer bind to one extra host, named by the MESHCORE_VIEWER_BIND environment variable
(run.sh sets it to the add-on's own address on Home Assistant's internal network, 172.30.32.1 under
host networking). That is the address the Supervisor's ingress connects to, but it is not reachable from
the local network, so with `webviewer.lan_access: false` the viewer port is closed to the network while
the sidebar keeps working. Upstream only allows 127.0.0.1, localhost and 0.0.0.0.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/web_viewer/app.py",
    """        self.socketio.init_app(self.app, **self._socketio_kwargs)
""",
    """        self.socketio.init_app(self.app, **self._socketio_kwargs)
        # Home Assistant ingress (sidebar): see modules/ingress_support.py.
        from modules.ingress_support import install_ingress_support
        install_ingress_support(self.app)
""",
)

patch(
    "modules/web_viewer/integration.py",
    """    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']
""",
    """    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0'] + [
        h for h in [os.environ.get("MESHCORE_VIEWER_BIND", "").strip()] if h
    ]
""",
)
