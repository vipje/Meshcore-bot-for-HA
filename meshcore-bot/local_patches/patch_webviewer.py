#!/usr/bin/env python3
"""Source patches applied to the vendored meshcore-bot web viewer.

Runs once during the Docker build, right after `git clone`, against the
freshly cloned source tree (cwd = WORKDIR, i.e. /opt/meshcore-bot). Each
patch is an exact string replacement that asserts its anchor text exists
exactly once — if a future upstream release changes the code around it,
the build fails loudly here instead of silently leaving the bug in place
(or silently no-op'ing the patch).
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


# 1. (vervallen in upstream v1.1.0) /api/maintenance/backup_now gaf altijd 503 omdat de webviewer
#    een apart proces is zonder bot.scheduler. Upstream maakt vanaf v1.1.0 zelf een
#    MaintenanceRunner aan in de viewer (app.py, self._maintenance_runner), dus onze
#    eigen backup-code is niet meer nodig.

# 2. Mesh map's light theme used plain OpenStreetMap tiles; its dark theme
#    pointed at CARTO's `dark_all` basemap, which now requires a paid API key
#    (every tile rendered as a watermarked "API KEY REQUIRED" placeholder).
#    User tried OpenTopoMap+Esri-satellite as a replacement first and didn't
#    like the look; settled on Esri's World Street Map for day, Esri's own
#    World Dark Gray Base (a muted dark canvas map, not a photo) for night -
#    same tile host as the street map, so no extra CSP host is needed and the
#    two styles read as one coherent day/night pair rather than a mismatch.
#    No CSS invert-filter hack needed either (unlike the old CARTO workaround
#    this replaces), since World Dark Gray Base is already dark by design.
# (Adapted for upstream v1.1.0: it now has an OpenStreetMap light layer and an OpenFreeMap vector dark
#  style. We keep the Esri pair chosen above, so this replaces that TILE_LAYERS block and switches off the
#  CSS inversion that upstream applies when the dark layer is a raster.)
patch(
    "modules/web_viewer/templates/mesh.html",
    "    const TILE_LAYERS = {\n        light: {\n            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',\n            attribution: '© OpenStreetMap contributors'\n        },\n        dark: {\n            styleUrl: 'https://tiles.openfreemap.org/styles/dark',\n            // Used only by the raster fallback below; the vector style carries its own\n            // attribution, which the bridge reads off the style once it loads.\n            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',\n            attribution: '© OpenStreetMap contributors'\n        }\n    };\n",
    "    const TILE_LAYERS = {\n        light: {\n            url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',\n            attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ'\n        },\n        dark: {\n            url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',\n            attribution: 'Tiles &copy; Esri &mdash; Source: Esri'\n        }\n    };\n",
)

patch(
    "modules/web_viewer/templates/mesh.html",
    "            container.classList.toggle('mesh-basemap-fallback', theme === 'dark' && !useVector);",
    "            container.classList.toggle('mesh-basemap-fallback', false);  // Esri dark is already dark: no CSS inversion",
)

# 3. The webviewer's CSP `img-src` only allow-lists the two hosts the old
#    OSM/CARTO tiles came from, so the Esri tiles from patch #2 above load
#    nothing (silently dropped by CSP - no console network error, the tile
#    pane just stays blank grey). Add the Esri tile host.
patch(
    "modules/web_viewer/app.py",
    '                "img-src \'self\' data: blob: https://*.tile.openstreetmap.org "\n                "https://tiles.openfreemap.org "\n',
    '                "img-src \'self\' data: blob: https://*.tile.openstreetmap.org "\n                "https://tiles.openfreemap.org "\n                "https://server.arcgisonline.com "\n',
)

# 3. `X-Frame-Options: SAMEORIGIN` blocks HA's "Webpagina"/panel_iframe
#    sidebar shortcut from rendering this app: that panel embeds the URL in
#    an <iframe> served from HA Core's own origin (host:8123), a different
#    origin than the webviewer's (host:8081), so SAMEORIGIN makes the browser
#    refuse to render it - same result for any host in the iframe URL, LAN IP
#    or 127.0.0.1, since the origin never matches. Dropped entirely rather
#    than allow-listing a specific origin via CSP frame-ancestors, since
#    there's no single fixed HA origin to allow-list here (LAN IP, .local
#    hostname, remote/VPN URL can all load the same dashboard). Acceptable
#    given this add-on already sits behind host_network (LAN-only) plus its
#    own webviewer_password.
patch(
    "modules/web_viewer/app.py",
    """            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'""",
    """            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'""",
)
