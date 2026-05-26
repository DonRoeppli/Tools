import asyncio
import json
import time
from base64 import b64decode

import httpx
import aiohttp

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)

# ── Challenge-Solver ──────────────────────────────────────────────────────────

def _decode(offset: int, message: str) -> str:
    return "".join(
        chr((((ord(c) * i) + offset) % 77) + 48)
        for i, c in enumerate(message)
    )

def _xor(token: str, key: str) -> str:
    raw = b64decode(token).decode()
    return "".join(chr(ord(raw[i]) ^ ord(key[i % len(key)])) for i in range(len(raw)))

def solve_challenge(session_token: str, challenge_js: str) -> str:
    text   = challenge_js.replace("\t", "").encode("ascii", "ignore").decode()
    offset = int(eval(text.split("offset = ")[1].split(";")[0]))
    inp    = text.split("this, '")[1].split("'")[0]
    return _xor(session_token, _decode(offset, inp))

# ── Client ────────────────────────────────────────────────────────────────────

class KahootClient:
    """
    on_event: async callable(event: str, data: dict) – optional
    """

    def __init__(self, on_event=None):
        self._on_event = on_event

    async def _fetch_namerator_name(self) -> str:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as http:
            r = await http.get("https://apis.kahoot.it/namerator")
            return r.json()["name"]

    async def join(self, pin: int, username: str) -> str:
        # ── 1. Session-ID ─────────────────────────────────────────────────────
        with httpx.Client(headers={"User-Agent": USER_AGENT}) as http:
            r = http.get(
                f"https://kahoot.it/reserve/session/{pin}/?{int(time.time())}"
            )
            if r.status_code == 404 or r.text == "Not found":
                raise ValueError(f"Spiel {pin} nicht gefunden.")
            if r.status_code != 200:
                raise ConnectionError(f"Session-Anfrage fehlgeschlagen: HTTP {r.status_code}")
            session_data     = r.json()
            session_token    = r.headers["x-kahoot-session-token"]
            session_id       = solve_challenge(session_token, session_data["challenge"])
            namerator_active = session_data.get("namerator", False)

        # ── 2. Namerator-Name holen (falls aktiviert) ─────────────────────────
        if namerator_active:
            username = await self._fetch_namerator_name()

        ws_url = f"wss://play.kahoot.it/cometd/{pin}/{session_id}"

        mid = 0
        def nid() -> str:
            nonlocal mid; mid += 1; return str(mid)

        async with aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT}
        ) as session:
            async with session.ws_connect(ws_url, ssl=True) as ws:

                pending: list[dict] = []

                async def send_recv(msg: dict) -> dict:
                    """Sendet eine Nachricht und wartet auf die passende Antwort (per id).
                    Nicht passende Nachrichten (z.B. Heartbeats) werden gepuffert."""
                    target_id = msg["id"]
                    await ws.send_json([msg])
                    while True:
                        raw = await asyncio.wait_for(ws.receive(), timeout=10)
                        if raw.type != aiohttp.WSMsgType.TEXT:
                            continue
                        for m in json.loads(raw.data):
                            if m.get("id") == target_id:
                                return m
                            else:
                                pending.append(m)

                # ── 3. Handshake ───────────────────────────────────────────────
                resp      = await send_recv({
                    "channel":                  "/meta/handshake",
                    "version":                  "1.0",
                    "minimumVersion":           "1.0",
                    "supportedConnectionTypes": ["websocket"],
                    "id":                       nid(),
                })
                client_id = resp["clientId"]

                # ── 4. Connect ─────────────────────────────────────────────────
                await send_recv({
                    "channel":        "/meta/connect",
                    "clientId":       client_id,
                    "connectionType": "websocket",
                    "id":             nid(),
                })

                # ── 5. Subscribe ───────────────────────────────────────────────
                for ch in ["/service/controller", "/service/player", "/service/status"]:
                    await send_recv({
                        "channel":      "/meta/subscribe",
                        "clientId":     client_id,
                        "subscription": ch,
                        "id":           nid(),
                    })

                # ── Gepufferte Heartbeats beantworten ─────────────────────────
                for m in pending:
                    if m.get("channel") == "/meta/connect":
                        await ws.send_json([{
                            "channel":        "/meta/connect",
                            "clientId":       client_id,
                            "connectionType": "websocket",
                            "id":             nid(),
                        }])
                pending.clear()

                # ── 6. Login ───────────────────────────────────────────────────
                await ws.send_json([{
                    "channel":  "/service/controller",
                    "clientId": client_id,
                    "data": {
                        "type":    "login",
                        "gameid":  pin,
                        "host":    "kahoot.it",
                        "name":    username,
                        "content": json.dumps({
                            "device": {
                                "userAgent": USER_AGENT,
                                "screen": {"width": 1920, "height": 1080},
                            },
                            "usingNamerator": namerator_active,
                        }),
                    },
                    "id": nid(),
                }])

                # ── 7. Nachrichten empfangen ───────────────────────────────────
                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        for msg in json.loads(raw.data):
                            channel = msg.get("channel", "")

                            if channel == "/meta/connect":
                                await ws.send_json([{
                                    "channel":        "/meta/connect",
                                    "clientId":       client_id,
                                    "connectionType": "websocket",
                                    "id":             nid(),
                                }])
                                continue

                            data = msg.get("data", {})
                            if isinstance(data, dict) and data.get("type") == "loginResponse":
                                if not data.get("error"):
                                    await ws.send_json([{
                                        "channel":  "/service/controller",
                                        "clientId": client_id,
                                        "data": {
                                            "id":      16,
                                            "type":    "message",
                                            "host":    "kahoot.it",
                                            "gameid":  pin,
                                            "content": json.dumps({"usingNamerator": namerator_active}),
                                        },
                                        "id": nid(),
                                    }])
                            await self._dispatch(msg)
                    elif raw.type in (aiohttp.WSMsgType.CLOSE,
                                      aiohttp.WSMsgType.ERROR,
                                      aiohttp.WSMsgType.CLOSED):
                        break

        return username

    async def _dispatch(self, msg: dict) -> None:
        if not self._on_event:
            return
        data = msg.get("data")
        if not isinstance(data, dict):
            return
        content = data.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                pass

        t = data.get("type", "")
        if   t == "loginResponse": await self._on_event("login_response",  data)
        elif t == "status" and data.get("status") == "ACTIVE":
                                   await self._on_event("game_start",       data)
        elif t == "getReady":      await self._on_event("question_ready",   content)
        elif t == "startQuestion": await self._on_event("question_start",   content)
        elif t == "showQuestion":  await self._on_event("question_end",     content)
        elif t == "endGame":       await self._on_event("game_over",        data)
