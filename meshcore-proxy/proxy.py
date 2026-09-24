#!/usr/bin/env python3
"""
meshcore-proxy: deelt één fysieke MeshCore-companion-radio (serieel) tussen
meerdere clients (meshcore-ha, de standalone bot, ...) via TCP.

Protocol (uit het `meshcore` python-package): elk frame is zelf-afbakenend
(0x3C <len:2 LE> <payload> uitgaand, 0x3E <len:2 LE> <payload> inkomend),
zonder client-ID. Een client die over TCP verbindt, praat dus exact hetzelfde
protocol als over serieel/USB - deze proxy hoeft de payload niet te begrijpen,
enkel bytes correct door te sturen.

Regels:
- Schrijven wordt geserialiseerd: zodra een client iets stuurt, krijgt hij
  een "spreekbeurt" totdat het apparaat een tijdje stil is (of een harde
  max-tijd verstrijkt), zodat twee clients nooit tegelijk een commando naar
  het apparaat sturen.
- Zolang iemand een spreekbeurt heeft, gaat alles wat het apparaat terugstuurt
  LIVE alleen naar die client. De andere, niet-sprekende clients krijgen diezelfde
  bytes gebufferd en pas geflusht zodra de beurt eindigt (niet weggegooid, enkel
  vertraagd). Zonder dit zou elke client die "wacht op het eerstvolgende
  OK/ERROR-antwoord" per ongeluk het antwoord van een andere client kunnen
  opvangen (het protocol heeft geen request-ID) - dat gaf random
  ERR_CODE_ILLEGAL_ARG-fouten bij de bot terwijl meshcore-ha tegelijk actief was.
- Buiten een spreekbeurt om (het meeste van de tijd - spontane mesh-events zoals
  inkomende berichten/adverts) wordt gewoon meteen naar iedereen gebroadcast,
  zoals voorheen.
"""
import argparse
import asyncio
import logging
import threading
import time

import serial

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s meshcore-proxy: %(message)s"
)
log = logging.getLogger("meshcore-proxy")


class Proxy:
    def __init__(self, port, baudrate, listen_host, listen_port,
                 quiet_release=0.75, max_hold=8.0):
        self.port = port
        self.baudrate = baudrate
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.quiet_release = quiet_release
        self.max_hold = max_hold

        self.clients: set[asyncio.StreamWriter] = set()
        self.clients_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.last_activity = 0.0

        # Tijdens een spreekbeurt: wie spreekt, en wat de anderen ondertussen
        # gemist hebben (per client gebufferd, geflusht zodra de beurt eindigt).
        self.turn_holder: asyncio.StreamWriter | None = None
        self.pending_broadcast: dict[asyncio.StreamWriter, bytearray] = {}

        self.loop: asyncio.AbstractEventLoop | None = None
        self.ser: serial.Serial | None = None
        self._stop = False

    # ---------- serial (blocking, runs in its own thread) ----------

    def serial_reader_thread(self):
        while not self._stop:
            try:
                if self.ser is None or not self.ser.is_open:
                    self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                    log.info(f"Serial opened: {self.port} @ {self.baudrate}")
                data = self.ser.read(4096)
                if data and self.loop is not None:
                    self.loop.call_soon_threadsafe(
                        lambda d=data: asyncio.create_task(self.broadcast(d))
                    )
            except Exception as e:
                log.warning(f"Serial read error: {e} - reopening in 2s")
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(2)

    # ---------- broadcast device -> all clients ----------

    async def broadcast(self, data: bytes):
        self.last_activity = time.monotonic()
        dead = []
        async with self.clients_lock:
            for w in self.clients:
                if self.turn_holder is not None and w is not self.turn_holder:
                    # Niet de spreker: bewaar voor na de beurt i.p.v. nu live sturen,
                    # anders kan deze client dit per ongeluk aanzien voor het
                    # antwoord op zijn eigen (niet aan de gang zijnde) commando.
                    self.pending_broadcast.setdefault(w, bytearray()).extend(data)
                    continue
                try:
                    w.write(data)
                    await w.drain()
                except Exception:
                    dead.append(w)
            for w in dead:
                self.clients.discard(w)
                self.pending_broadcast.pop(w, None)

    async def _flush_pending(self):
        """Stuur wat niet-sprekende clients tijdens de beurt hebben gemist."""
        dead = []
        async with self.clients_lock:
            pending, self.pending_broadcast = self.pending_broadcast, {}
        for w, buf in pending.items():
            if not buf or w not in self.clients:
                continue
            try:
                w.write(bytes(buf))
                await w.drain()
            except Exception:
                dead.append(w)
        if dead:
            async with self.clients_lock:
                for w in dead:
                    self.clients.discard(w)

    # ---------- per-client TCP handler ----------

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        log.info(f"Client connected: {peer}")
        async with self.clients_lock:
            self.clients.add(writer)
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                await self.forward_to_device(data, writer)
        except Exception as e:
            log.info(f"Client {peer} error: {e}")
        finally:
            async with self.clients_lock:
                self.clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass
            log.info(f"Client disconnected: {peer}")

    # ---------- serialized write client -> device ----------

    async def forward_to_device(self, data: bytes, writer: asyncio.StreamWriter):
        async with self.write_lock:
            if self.ser is None or not self.ser.is_open:
                log.warning("Serial not open, dropping write")
                return
            try:
                self.ser.write(data)
            except Exception as e:
                log.warning(f"Serial write failed: {e}")
                return

            self.turn_holder = writer
            try:
                self.last_activity = time.monotonic()
                start = time.monotonic()
                # Houd de "spreekbeurt" vast tot het apparaat een tijdje stil is
                # (antwoord klaar), met een harde bovengrens zodat één trage
                # aanvraag de andere client nooit voor altijd kan blokkeren.
                while True:
                    await asyncio.sleep(0.1)
                    now = time.monotonic()
                    if now - self.last_activity >= self.quiet_release:
                        break
                    if now - start >= self.max_hold:
                        log.debug("max_hold bereikt, spreekbeurt toch vrijgeven")
                        break
            finally:
                self.turn_holder = None
                await self._flush_pending()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        threading.Thread(target=self.serial_reader_thread, daemon=True).start()
        server = await asyncio.start_server(self.handle_client, self.listen_host, self.listen_port)
        log.info(
            f"Luistert op {self.listen_host}:{self.listen_port}, brug naar {self.port} "
            "(turn-aware broadcast v2)"
        )
        async with server:
            await server.serve_forever()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--serial-port", required=True)
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--listen-host", default="0.0.0.0")
    p.add_argument("--listen-port", type=int, default=5010)
    p.add_argument("--quiet-release", type=float, default=0.75,
                   help="seconds of radio silence after which a client's turn ends")
    p.add_argument("--max-hold", type=float, default=8.0,
                   help="hard maximum in seconds that one client may hold the turn")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.getLogger().setLevel(args.log_level)
    proxy = Proxy(args.serial_port, args.baudrate, args.listen_host, args.listen_port,
                  quiet_release=args.quiet_release, max_hold=args.max_hold)
    asyncio.run(proxy.run())


if __name__ == "__main__":
    main()
