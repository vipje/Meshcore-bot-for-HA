"""Alle pagina's van de echte (gepatchte) viewer, met en zonder Home Assistant ingress-header."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, hashlib, os, re, sys, tempfile

TREE = sys.argv[1]
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else ""
os.chdir(TREE); sys.path.insert(0, TREE)

work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Test|🤖"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": PASSWORD}
cfg["Channels"] = {"monitor_channels": "#test"}
with open(f"{work}/config.ini", "w") as f:
    cfg.write(f)

from modules.web_viewer.app import BotDataViewer
viewer = BotDataViewer(config_path=f"{work}/config.ini")
app = viewer.app
app.config["TESTING"] = True

PREFIX = "/api/hassio_ingress/TESTTOKEN"
HDR = {"X-Ingress-Path": PREFIX}

pages = sorted({r.rule for r in app.url_map.iter_rules()
                if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith(("/static", "/api/", "/socket.io"))})
print(f"{len(pages)} pagina's:", " ".join(pages))

ABS_ATTR = re.compile(r'(?:href|src|action)\s*=\s*["\']/(?!/)([^"\']*)', re.I)
problems, ok = [], 0


def login(client, headers):
    if PASSWORD:
        r = client.post("/login", data={"password": PASSWORD}, headers=headers, follow_redirects=False)
        return r
    return None


for headers, label in ((HDR, "ingress"), ({}, "gewoon")):
    client = app.test_client()
    if PASSWORD:
        r = login(client, headers)
        print(f"[{label}] login: {r.status_code} Location={r.headers.get('Location')}")
    for page in pages:
        r = client.get(page, headers=headers, follow_redirects=False)
        body = r.get_data(as_text=True) if "text" in (r.content_type or "") or "json" in (r.content_type or "") else ""
        loc = r.headers.get("Location", "")
        if r.status_code in (301, 302, 303, 307, 308):
            if label == "ingress" and loc.startswith("/") and not loc.startswith(PREFIX):
                problems.append(f"[{label}] {page}: redirect naar {loc} zonder voorvoegsel")
            elif label == "gewoon" and "hassio_ingress" in loc:
                problems.append(f"[{label}] {page}: redirect bevat ingress-pad {loc}")
            else:
                ok += 1
            continue
        if r.status_code >= 500:
            problems.append(f"[{label}] {page}: HTTP {r.status_code}")
            continue
        if "html" not in (r.content_type or ""):
            ok += 1; continue
        if label == "ingress":
            bad = [m for m in ABS_ATTR.findall(body) if not ("api/hassio_ingress/" in m)]
            if bad:
                problems.append(f"[{label}] {page}: {len(bad)} absolute attributen, bv. /{bad[0][:60]}")
            if "_ingress/shim.js" not in body:
                problems.append(f"[{label}] {page}: shim.js niet ingevoegd")
            for cookie in r.headers.getlist("Set-Cookie"):
                if "Path=/" in cookie and PREFIX not in cookie and "Path=/;" in cookie + ";":
                    problems.append(f"[{label}] {page}: cookie zonder pad-voorvoegsel: {cookie[:80]}")
        else:
            if "hassio_ingress" in body or "_ingress" in body:
                problems.append(f"[{label}] {page}: ingress-sporen in gewone respons")
        ok += 1

# shim en statische bestanden
client = app.test_client()
if PASSWORD:
    login(client, HDR)
r = client.get("/_ingress/shim.js", headers=HDR)
print("shim.js:", r.status_code, r.content_type, len(r.get_data()), "bytes")
if r.status_code != 200 or "javascript" not in (r.content_type or ""):
    problems.append("shim.js wordt niet als javascript geserveerd")

# statische js/css die door de pagina's worden geladen: absolute paden binnenin?
static = set()
client2 = app.test_client()
if PASSWORD: login(client2, {})
for page in pages:
    rr = client2.get(page)
    if 'html' not in (rr.content_type or ''):
        continue
    b = rr.get_data(as_text=True)
    static |= set(re.findall(r'(?:src|href)=["\'](/static/[^"\'?#]+\.(?:js|css))', b))
print(f"{len(static)} statische bestanden")
ABS_IN_STATIC = re.compile(r"""(?:url\(\s*['"]?/(?!/)|import\s*\(\s*['"]/(?!/)|from\s+['"]/(?!/)|import\s+['"]/(?!/))""")
for s in sorted(static):
    b = client.get(s, headers=HDR).get_data(as_text=True)
    hits = ABS_IN_STATIC.findall(b)
    if hits:
        problems.append(f"statisch {s}: {len(hits)} absolute verwijzingen")

# Socket.IO polling met vreemde Origin + ingress header
r = client.get(f"/socket.io/?EIO=4&transport=polling", headers={**HDR, "Origin": "https://xyz.ui.nabu.casa"})
print("socket.io polling (ingress, vreemde Origin):", r.status_code)
if r.status_code not in (200,):
    problems.append(f"socket.io polling met ingress: HTTP {r.status_code}")
r = client.get(f"/socket.io/?EIO=4&transport=polling", headers={"Origin": "https://evil.example"})
print("socket.io polling (GEEN ingress, vreemde Origin):", r.status_code)
if r.status_code == 200:
    problems.append("vreemde Origin zonder ingress-header wordt niet geweigerd")

print(f"\n{ok} pagina-controles goed, {len(problems)} problemen")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
