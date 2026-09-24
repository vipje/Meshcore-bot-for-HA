"""Een melding mag de gedeelde zendbegrenzing niet vullen; een antwoord op een gebruiker wel."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import asyncio, importlib.util, logging, sys, types

U = os.environ["SIM_TREE"]
sys.path.insert(0, U)
from modules.rate_limiter import RateLimiter  # echte upstream-klasse

pkg = types.ModuleType("fakepkg"); pkg.__path__ = []; sys.modules["fakepkg"] = pkg
base = types.ModuleType("fakepkg.base_service")
class BaseServicePlugin:
    def __init__(self, *a, **k): pass
base.BaseServicePlugin = BaseServicePlugin
sys.modules["fakepkg.base_service"] = base
spec = importlib.util.spec_from_file_location(
    "fakepkg.notify_service", ADDON + "/local_service_plugins/notify_service.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


class CM:
    """Nabootsing van command_manager: een geslaagde verzending noteert altijd in de limiter."""
    def __init__(self, bot): self.bot = bot
    async def send_dm(self, key, text, skip_user_rate_limit=False):
        await asyncio.sleep(0.01)
        self.bot.rate_limiter.record_send()   # zoals _handle_send_result
        return True
    send_channel_message = send_dm


async def main():
    bot = types.SimpleNamespace(rate_limiter=RateLimiter(10), connected=True)
    bot.command_manager = CM(bot)
    svc = ns.NotifyService.__new__(ns.NotifyService)     # zonder volledige init
    svc.bot, svc.destination, svc.target, svc.logger = bot, "room", "abc", logging.getLogger("t")
    svc._sending = False

    # zonder herstel: reden voor de storing
    await bot.command_manager.send_dm("abc", "melding")
    assert not bot.rate_limiter.can_send(), "voorwaarde: gewone verzending blokkeert 10 s"
    bot.rate_limiter.last_send = 0.0

    # met de service: melding verstuurd, limiter ongemoeid
    ok = await svc._send("melding")
    assert ok is True
    assert bot.rate_limiter.can_send(), "melding blokkeert het volgende commando nog"
    print("melding verstuurd, ping erna mag: OK")

    # antwoord aan een gebruiker telt gewoon mee
    await bot.command_manager.send_dm("abc", "pong")
    assert not bot.rate_limiter.can_send()
    print("gewoon antwoord blokkeert nog steeds 10 s: OK")

    # mislukte verzending / uitzondering laat de limiter ook ongemoeid
    bot.rate_limiter.last_send = 0.0
    async def boom(*a, **k):
        bot.rate_limiter.record_send(); raise RuntimeError("radio weg")
    bot.command_manager.send_dm = boom
    assert await svc._send("melding") is False
    assert bot.rate_limiter.can_send()
    print("uitzondering: OK")

    # geen limiter aanwezig: geen crash
    del bot.rate_limiter
    bot.command_manager.send_dm = CM(bot).send_dm
    bot.command_manager.send_dm = lambda *a, **k: asyncio.sleep(0, True)
    assert await svc._send("melding") is True
    print("ALLES OK")

asyncio.run(main())
