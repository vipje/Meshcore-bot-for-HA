"""Export and import of the bot's settings and database through Home Assistant's /share folder.

Usage: data_transfer.py <data_dir> <share_dir>        (run.sh: /data /share/meshcore-bot, before generate_config.py)

Why: an add-on installed from another repository (or on another Home Assistant) is a new add-on with an empty /data.
Home Assistant backups cannot be opened by hand, so this is the way to take the bot with you.

- Export: when <share_dir>/EXPORT exists, the bot's files are copied to <share_dir>/export/<date-time>/ and EXPORT is
  removed. The database is copied with SQLite's backup API, so the copy is consistent.
- Import: only when <data_dir>/config.ini does not exist yet (a new installation) and <share_dir>/import/ holds a
  config.ini or a database. The files are copied to <data_dir>, the add-on options are restored through the
  Supervisor (when options.json is there), and the folder is renamed to import-done-<date-time>. An installation that
  already has settings is never overwritten.

Only standard library; everything is logged to stdout (the add-on log). Nothing here ever stops the add-on from starting.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request

FILES = ("config.ini", "generated_keys.json", "options.json")   # small files, copied as they are
DB = "meshcore_bot.db"


def log(text: str) -> None:
    print(f"data_transfer: {text}", flush=True)


def free_path(base: str) -> str:
    """base, or base-2, base-3, ... when it already exists (two runs within one second)."""
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-{n}"
    return path


def stamp() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S")


def copy_db(src: str, dst: str) -> None:
    """Consistent copy of a SQLite database (also when it has a -wal file)."""
    source, target = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=DELETE")   # one self-contained file, no -wal/-shm next to it
    finally:
        target.close()
        source.close()


def export(data_dir: str, share_dir: str) -> str | None:
    request = os.path.join(share_dir, "EXPORT")
    if not os.path.exists(request):
        return None
    target = free_path(os.path.join(share_dir, "export", stamp()))
    os.makedirs(target, exist_ok=True)
    done = []
    for name in FILES:
        src = os.path.join(data_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(target, name))
            done.append(name)
    if os.path.isfile(os.path.join(data_dir, DB)):
        copy_db(os.path.join(data_dir, DB), os.path.join(target, DB))
        done.append(DB)
    os.remove(request)
    log(f"export ready in {target}: {', '.join(done) or 'nothing to export'}")
    return target


def restore_options(options: dict, supervisor_url: str, token: str) -> bool:
    """Store the exported options as this add-on's options, so the Configuration tab shows them too."""
    if not token:
        log("no Supervisor token: options not restored, fill them in on the Configuration tab")
        return False
    req = urllib.request.Request(f"{supervisor_url}/addons/self/options", data=json.dumps({"options": options}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = json.loads(resp.read() or b"{}").get("result") == "ok"
    except Exception as e:  # noqa: BLE001 - e.g. an option this version no longer knows
        log(f"options not restored ({e}); check the Configuration tab")
        return False
    log("add-on options restored" if ok else "options not restored; check the Configuration tab")
    return ok


def import_(data_dir: str, share_dir: str, supervisor_url: str = "http://supervisor", token: str = "") -> bool:
    source = os.path.join(share_dir, "import")
    if not os.path.isdir(source):
        return False
    if os.path.exists(os.path.join(data_dir, "config.ini")):
        log(f"{source} found, but this installation already has settings: nothing imported (remove {data_dir}/config.ini "
            "by reinstalling the add-on if you really want to import)")
        return False
    present = [n for n in FILES + (DB,) if os.path.isfile(os.path.join(source, n))]
    if "config.ini" not in present and DB not in present:
        log(f"{source} holds no config.ini or {DB}: nothing imported")
        return False
    for name in present:
        src, dst = os.path.join(source, name), os.path.join(data_dir, name)
        if name == DB:
            copy_db(src, dst)
        elif name != "options.json":
            shutil.copy2(src, dst)
    if "options.json" in present:
        with open(os.path.join(source, "options.json"), encoding="utf-8") as f:
            options = json.load(f)
        if restore_options(options, supervisor_url, token):
            # This start already read options.json; use the imported one right away as well.
            with open(os.path.join(data_dir, "options.json"), "w", encoding="utf-8") as f:
                json.dump(options, f)
    done = free_path(os.path.join(share_dir, f"import-done-{stamp()}"))
    os.rename(source, done)
    log(f"imported {', '.join(present)}; the folder is now {done}")
    return True


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    data_dir, share_dir = sys.argv[1], sys.argv[2]
    if not os.path.isdir(os.path.dirname(share_dir.rstrip("/")) or "/"):
        return 0   # no /share mapped
    try:
        os.makedirs(share_dir, exist_ok=True)
        import_(data_dir, share_dir, token=os.environ.get("SUPERVISOR_TOKEN", ""))
        export(data_dir, share_dir)
    except Exception as e:  # noqa: BLE001 - never stop the add-on from starting
        log(f"failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
