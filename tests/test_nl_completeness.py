"""Dekking van upstreams eigen teksten in het Nederlands, Duits en Frans: elke sleutel in translations/en.json heeft
een tekst in upstream's translations/<taal>.json of in onze eigen local_shared/local_translations/<taal>.json
(overlay wint)."""
import json
import pathlib as _pl
import sys

_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")
TREE = sys.argv[1] if len(sys.argv) > 1 else None
if not TREE:
    sys.exit("usage: test_nl_completeness.py <sim_tree>")

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


def flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def deep_merge(base, add):
    for k, v in add.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


en = json.load(open(f"{TREE}/translations/en.json"))
fen = flatten(en)
NAMES = {"nl": "Nederlandse", "de": "Duitse", "fr": "Franse"}
for lang, label in NAMES.items():
    merged = json.load(open(f"{TREE}/translations/{lang}.json"))
    deep_merge(merged, json.load(open(f"{ADDON}/local_shared/local_translations/{lang}.json")))
    flat = flatten(merged)
    # keywords.* are alternate trigger words (functional, not prose) and intentionally not translated.
    missing = sorted(k for k in fen if k not in flat and not k.startswith("keywords."))
    check(
        not missing,
        f"elke upstream-tekst (op keywords.* na) heeft een {label} vertaling, in upstream's eigen "
        f"{lang}.json of in ons lokale overlay ({len(missing)} ontbreken) {missing[:10]}",
    )
print(f"\n{len(fails)} fouten ({len(fen) - sum(1 for k in fen if k.startswith('keywords.'))} teksten gecontroleerd)")
sys.exit(1 if fails else 0)
