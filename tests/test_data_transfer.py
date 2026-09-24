"""data_transfer.py: export and import of settings and database through /share (moving the bot to a new installation)."""
import http.server
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "meshcore-bot"))
import data_transfer as T  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def make_data(d: pathlib.Path, bot_name="Oud"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.ini").write_text(f"[Bot]\nbot_name = {bot_name}\n")
    (d / "generated_keys.json").write_text('{"Bot": ["bot_name"]}')
    (d / "options.json").write_text(json.dumps({"bot": {"name": bot_name}}))
    with sqlite3.connect(d / "meshcore_bot.db") as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE t (x)")
        c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(500)])
    # keep a connection open with uncommitted-to-main data in the WAL, like a running bot
    keep = sqlite3.connect(d / "meshcore_bot.db")
    keep.execute("PRAGMA journal_mode=WAL")
    keep.execute("INSERT INTO t VALUES (999)")
    keep.commit()
    return keep


def rows(db):
    with sqlite3.connect(db) as c:
        return c.execute("SELECT COUNT(*), MAX(x) FROM t").fetchone()


class Supervisor(http.server.BaseHTTPRequestHandler):
    received = []
    answer = {"result": "ok", "data": {}}

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Supervisor.received.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        data = json.dumps(Supervisor.answer).encode()
        self.send_response(200 if Supervisor.answer.get("result") == "ok" else 400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    old, share = tmp / "old", tmp / "share" / "meshcore-bot"
    keep = make_data(old)
    share.mkdir(parents=True)

    # --- export
    check(T.export(str(old), str(share)) is None and not (share / "export").exists(), "export: zonder EXPORT-bestand gebeurt niets")
    (share / "EXPORT").write_text("")
    target = pathlib.Path(T.export(str(old), str(share)))
    check(not (share / "EXPORT").exists(), "export: het verzoekbestand is weg (geen export bij elke start)")
    check(sorted(p.name for p in target.iterdir()) == ["config.ini", "generated_keys.json", "meshcore_bot.db", "options.json"],
          f"export: alle vier bestanden ({sorted(p.name for p in target.iterdir())})")
    check(rows(target / "meshcore_bot.db") == (501, 999), "export: de database is compleet, ook wat nog in de WAL stond")
    check(not list(target.glob("*-wal")), "export: geen losse WAL-bestanden")
    keep.close()

    # --- import on a new installation
    new = tmp / "new"
    new.mkdir()
    (new / "options.json").write_text(json.dumps({"bot": {"name": "MeshCoreBot"}}))   # the defaults of a new add-on
    os.rename(target, share / "import")
    srv = http.server.HTTPServer(("127.0.0.1", 0), Supervisor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    check(T.import_(str(new), str(share), url, "tok") is True, "import: nieuwe installatie wordt gevuld")
    check((new / "config.ini").read_text() == "[Bot]\nbot_name = Oud\n" and rows(new / "meshcore_bot.db") == (501, 999)
          and (new / "generated_keys.json").exists(), "import: config.ini, database en generated_keys.json staan in /data")
    check(Supervisor.received == [("/addons/self/options", "Bearer tok", {"options": {"bot": {"name": "Oud"}}})],
          f"import: opties via de Supervisor teruggezet ({Supervisor.received})")
    check(json.loads((new / "options.json").read_text()) == {"bot": {"name": "Oud"}}, "import: deze start gebruikt meteen de oude opties")
    done = [p.name for p in share.iterdir() if p.name.startswith("import-done-")]
    check(not (share / "import").exists() and len(done) == 1, f"import: map hernoemd ({done})")

    # --- never overwrite an installation that already has settings
    (share / "import").mkdir()
    (share / "import" / "config.ini").write_text("[Bot]\nbot_name = Ander\n")
    check(T.import_(str(new), str(share), url, "tok") is False and (new / "config.ini").read_text() == "[Bot]\nbot_name = Oud\n"
          and (share / "import").exists(), "import: bestaande instellingen worden nooit overschreven, de map blijft staan")

    # --- options the Supervisor refuses: the files are still imported, options.json of this start stays as it was
    fresh = tmp / "fresh"
    fresh.mkdir()
    (fresh / "options.json").write_text('{"bot": {"name": "MeshCoreBot"}}')
    (share / "import" / "options.json").write_text('{"bot": {"name": "Ander"}, "unknown": 1}')
    Supervisor.answer = {"result": "error", "message": "unknown option"}
    check(T.import_(str(fresh), str(share), url, "tok") is True and (fresh / "config.ini").exists()
          and json.loads((fresh / "options.json").read_text()) == {"bot": {"name": "MeshCoreBot"}},
          "import: geweigerde opties = bestanden wel geïmporteerd, opties van deze start ongewijzigd")
    fresh2 = tmp / "fresh2"
    fresh2.mkdir()
    (share / "import").mkdir()
    (share / "import" / "options.json").write_text("{}")
    check(T.import_(str(fresh2), str(share), url, "") is False and not (fresh2 / "config.ini").exists(),
          "import: zonder config.ini of database wordt niets geïmporteerd")
    (share / "import" / "config.ini").write_text("[Bot]\n")
    before = len(Supervisor.received)
    check(T.import_(str(fresh2), str(share), url, "") is True and len(Supervisor.received) == before,
          "import: zonder Supervisor-token geen oproep, bestanden wel geïmporteerd")
    srv.shutdown()

    # --- main() never fails the start
    sys.argv = ["data_transfer.py", str(tmp / "nodata"), str(tmp / "share" / "meshcore-bot")]
    (share / "EXPORT").write_text("")
    check(T.main() == 0, "main: geeft altijd 0 terug (de add-on start altijd)")
    sys.argv = ["data_transfer.py", str(new), str(tmp / "noshare" / "meshcore-bot")]
    check(T.main() == 0 and not (tmp / "noshare").exists(), "main: zonder /share gebeurt niets")

run_sh = (HERE.parent / "meshcore-bot" / "run.sh").read_text()
check(run_sh.index("data_transfer.py") < run_sh.index("generate_config.py"), "run.sh: import/export vóór generate_config.py")
cfg = (HERE.parent / "meshcore-bot" / "config.yaml").read_text()
check("  - share:rw" in cfg and "hassio_api: true" in cfg, "config.yaml: /share gekoppeld en Supervisor-API aan")
check("COPY data_transfer.py /opt/data_transfer.py" in (HERE.parent / "meshcore-bot" / "Dockerfile").read_text(), "Dockerfile kopieert data_transfer.py")

print(f"\n{fails} fouten")
sys.exit(1 if fails else 0)
