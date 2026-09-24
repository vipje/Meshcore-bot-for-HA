import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import configparser, os, sys, tempfile
TREE = sys.argv[1]; os.chdir(TREE); sys.path.insert(0, TREE)
work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/v.db", "bot_name": "Own|🤖"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
with open(f"{work}/config.ini", "w") as f: cfg.write(f)
from modules.web_viewer.app import BotDataViewer
v = BotDataViewer(config_path=f"{work}/config.ini"); v.app.config["TESTING"] = True
open(sys.argv[2], "w", encoding="utf-8").write(v.app.test_client().get("/bots").get_data(as_text=True))
