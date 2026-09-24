"""Onze eigen vertaalcatalogus (local_shared/local_translations/{nl,en,de,fr}.json): elke translate()-sleutel die
ergens in local_commands/, local_shared/ of local_service_plugins/ wordt gebruikt, bestaat in alle vier de talen."""
import json
import pathlib as _pl
import re
import sys

ADDON = _pl.Path(__file__).resolve().parent.parent / "meshcore-bot"
LANGS = ["nl", "en", "de", "fr"]

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


catalogs = {lang: json.load(open(ADDON / f"local_shared/local_translations/{lang}.json")) for lang in LANGS}


def get(cat, path):
    node = cat
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# self.translate("key") / self.translate(f"key.{var}") / translate("key", ...) - static or f-string first argument.
PATTERN = re.compile(r"(?<!def )(?:self\.)?translate\(\s*f?(['\"])(?P<key>[^'\"]*)\1")

# Dynamic f-string key prefixes we build ourselves in code -> every suffix that can occur at runtime.
ENUMS = {
    "commands.f1.country": [
        "Australia", "Austria", "Azerbaijan", "Bahrain", "Belgium", "Brazil", "Canada", "China", "France", "Germany",
        "Hungary", "Italy", "Japan", "Mexico", "Monaco", "Netherlands", "Qatar", "Saudi Arabia", "Singapore",
        "Spain", "UAE", "United Arab Emirates", "UK", "United Kingdom", "USA", "United States", "Portugal",
        "Turkey", "Russia", "Argentina", "Malaysia", "South Africa",
    ],
    "commands.f1.session": ["fp1", "fp2", "fp3", "sq", "sprint", "quali", "race"],
    "commands.f1.day": [str(i) for i in range(7)],
    "commands.f1.month": [str(i) for i in range(1, 13)],
    "commands.f1.status": ["live", "suspended", "break", "pre"],
    "commands.wegwerk.type": ["RoadOrCarriagewayOrLaneManagement", "SpeedManagement", "ReroutingManagement", "GeneralNetworkManagement"],
    "commands.sig.verdict": ["good", "fair", "weak", "very_weak"],
    "commands.meshkaart.role": ["companion", "repeater", "room", "sensor", "other"],
    "commands.xp.title": [str(i) for i in range(7)],
    "commands.badge.name": ["msg100", "msg1000", "days30", "days100", "hops3", "hops6", "streak7", "streak30", "karma10", "level5", "level10"],
    "commands.file.type": ["AbnormalTraffic", "Accident", "GeneralObstruction", "VehicleObstruction"],
}

static_keys, prefix_keys = set(), set()
for f in (
    list((ADDON / "local_commands").glob("*.py"))
    + list((ADDON / "local_shared").glob("*.py"))
    + list((ADDON / "local_service_plugins").glob("*.py"))
):
    text = f.read_text()
    text = re.sub(r'#.*', '', text)  # a mention of translate(...) in a comment must not count as a real call
    for m in PATTERN.finditer(text):
        key = m.group("key")
        if "{" in key:
            prefix_keys.add((key.split("{")[0].rstrip("."), f.name))
        else:
            static_keys.add((key, f.name))

bad_static = []
for key, fname in sorted(static_keys):
    missing = [lang for lang in LANGS if not isinstance(get(catalogs[lang], key), str)]
    if missing:
        bad_static.append(f"{key} ({fname}): ontbreekt in {missing}")
check(not bad_static, f"elke vaste translate()-sleutel bestaat in alle 4 talen {bad_static[:6]}")

bad_dynamic = []
unknown_prefixes = sorted({p for p, _f in prefix_keys if p not in ENUMS})
check(not unknown_prefixes, f"elk dynamisch voorvoegsel staat in ENUMS hierboven {unknown_prefixes}")
for prefix, _fname in sorted(prefix_keys):
    for suffix in ENUMS.get(prefix, []):
        full = f"{prefix}.{suffix}"
        missing = [lang for lang in LANGS if not isinstance(get(catalogs[lang], full), str)]
        if missing:
            bad_dynamic.append(f"{full}: ontbreekt in {missing}")
check(not bad_dynamic, f"elke dynamische sleutel (landen, sessies, dagen, maanden, ...) bestaat in alle 4 talen {bad_dynamic[:6]}")

print(f"\n{len(fails)} fouten ({len(static_keys)} vaste sleutels, {len(prefix_keys)} dynamische voorvoegsels gecontroleerd)")
sys.exit(1 if fails else 0)
