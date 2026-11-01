"""python3 tests/test_lite.py   — no Telegram, no internet: the brain is tested with fakes."""
import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lite  # noqa: E402
from lite import Msg, Responder, Sender, Settings, allowed  # noqa: E402

fails = 0


def check(cond, label):
    global fails
    print(("PASS " if cond else "FAIL ") + label)
    fails += (not cond)


class FakeTG:
    def __init__(self):
        self.msgs, self.sent, self.next = [], [], 1000
        self.on_sleep = None

    def add(self, text="", out=False, kind="text", id=None):
        self.next += 1
        self.msgs.append(Msg(id or self.next, out, text, kind))
        return self.msgs[-1].id

    async def recent(self, chat, n):
        return list(self.msgs[-n:])

    async def send(self, chat, text):
        self.sent.append(text)
        return self.add(text, out=True)


async def instant(_):
    return None


def make(claude=None, **kw):
    tg, notes = FakeTG(), []

    async def notify(t):
        notes.append(t)
    d = tempfile.mkdtemp()
    st = Settings(grace=0, contacts_file=os.path.join(d, "c.txt"), info_file=os.path.join(d, "i.txt"), **kw)
    r = Responder(st, tg, notify, claude, sleep=instant, log=lambda m: None)
    return r, tg, notes, st


def run(coro):
    return asyncio.run(coro)


bro = Sender(name="Brother", id=1)

# ---- who is allowed
c = ["Brother", "NAVOIY-QORAKO'L O'QUV MARKAZI", "@aziz_u", "+998 90 123 45 67", "id:777", "Otabek Akam"]
check(allowed(Sender(name="Brother"), c) and allowed(Sender(name="my brother 🙂"), c), "name match, both directions")
check(allowed(Sender(name="Navoiy-Qorakoʻl Oʻquv Markazi"), c), "Telegram's ʻ apostrophes and capitals match")
check(allowed(Sender(name="x", username="Aziz_U"), c) and allowed(Sender(name="x", phone="998901234567"), c) and allowed(Sender(name="x", id=777), c), "@username, phone and id lines")
check(not allowed(Sender(name="Stranger"), c) and not allowed(Sender(name="Brother", bot=True), c) and not allowed(Sender(name=""), c), "strangers, bots, nameless are not")

# ---- a normal answer
seen = []


async def fake_claude(system, user):
    seen.append((system, user))
    return "Darslar 15:00 da boshlanadi."


r, tg, notes, st = make(fake_claude)
tg.add("old message from yesterday", id=1)                    # before Jarvis saw anything
mid = tg.add("dars soat nechada?")
run(r.on_message(5, mid, bro))
check(len(tg.sent) == 1 and tg.sent[0].startswith("Darslar 15:00") and tg.sent[0].endswith("🤖 Jarvis (avto-javob)"), "answers with the signature")
check("dars soat nechada?" in seen[0][1] and "is writing to Zufarbek, not to you" in seen[0][0] and "siz" in seen[0][0], "Claude gets the message, owner rule and tone notes")
check("old message" in seen[0][1] and notes and "I answered Brother" in notes[0], "context included, phone notified")
n = len(tg.sent)
run(r.on_message(5, mid, bro))
check(len(tg.sent) == n, "the same message is never answered twice")

# ---- burst of messages = one answer
r, tg, notes, st = make(fake_claude)
tg.add("hello", id=1)
a = tg.add("are you there")
b = tg.add("bro")
seen.clear()
run(r.on_message(5, a, bro))
check(len(tg.sent) == 1 and "are you there" in seen[0][1] and "bro" in seen[0][1], "several quick messages -> one answer covering all")

# ---- you answered yourself
r, tg, notes, st = make(fake_claude)
mid = tg.add("salom")
tg.add("qalaysan, men shu yerdaman", out=True)                 # you, from your phone
run(r.on_message(5, mid, bro))
check(not tg.sent, "you replied yourself during the wait -> Jarvis stays quiet")

# ---- messages that arrive while it is busy are not lost
r, tg, notes, st = make(fake_claude)
first = tg.add("birinchi")
orig = r.process
state = {"n": 0}


async def slow_process(chat, sender):
    state["n"] += 1
    if state["n"] == 1:
        asyncio.get_running_loop().create_task(r.on_message(chat, tg.add("ikkinchi (kech keldi)"), sender))
        await asyncio.sleep(0)
    return await orig(chat, sender)


r.process = slow_process
run(r.on_message(5, first, bro))
check(len(tg.sent) >= 1 and state["n"] >= 1, "late message does not crash / deadlock")

# ---- voice
r, tg, notes, st = make(fake_claude)
v = tg.add("", kind="voice")
seen.clear()
run(r.on_message(5, v, bro))
check(len(tg.sent) == 1 and "Zufarbek Jumayev hozir band" in tg.sent[0] and "o'zi javob yozadi" in tg.sent[0] and not seen, "voice message -> fixed reply, no AI call")
v2 = tg.add("", kind="voice")
run(r.on_message(5, v2, bro))
check(len(tg.sent) == 1 and any("another voice message" in x for x in notes), "second voice within 30 min -> not answered, you are told")
p = tg.add("", kind="other")
run(r.on_message(5, p, bro))
check(len(tg.sent) == 1 and any("file/photo" in x for x in notes), "photo without text -> you are told, nothing sent")

# ---- sensitive / ping-pong / limits
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("menga pul o'tkazib ber, karta raqamingni ayt"), bro))
check(not tg.sent and any("won't answer" in x for x in notes), "money -> no answer, you are told")
run(r.on_message(5, tg.add("🤖 Jarvis (avto-javob): hozir band"), bro))
check(not tg.sent, "another auto-reply bot is ignored")
r, tg, notes, st = make(fake_claude)
for i in range(5):
    run(r.on_message(5, tg.add(f"savol {i}"), bro))
check(len(tg.sent) == 3 and any("limit reached" in x for x in notes), "max 3 replies per chat per hour")

# ---- no key / Claude down -> fixed sentences in the right language
r, tg, notes, st = make(None)
run(r.on_message(5, tg.add("nima gap, qalaysan, ishlar yaxshimi"), bro))
check("sun'iy intellekt" in tg.sent[0] and "Zufarbek" in tg.sent[0], "no Claude key -> correct Uzbek sentence")


async def broken(system, user):
    raise ConnectionError("offline")


r, tg, notes, st = make(broken)
run(r.on_message(5, tg.add("hello bro how are you"), bro))
check("AI assistant" in tg.sent[0], "Claude fails -> English sentence")

# ---- files and the prompt
r, tg, notes, st = make(fake_claude)
open(st.info_file, "w").write("# izoh\nNarx: 100 000 so'm")
check("Narx: 100 000 so'm" in r.info() and "izoh" not in r.info() and "Brother — Zufarbekning do'sti" in r.info(), "info.txt is read fresh, comments ignored, tone notes built in")
check(lite.read_lines("/nonexistent") == [], "missing file is fine")
env = tempfile.mktemp()
open(env, "w").write('OWNER_FULL_NAME=Zufarbek Jumayev\n# c\nX="q"\n')
for k in ("OWNER_FULL_NAME", "X"):
    os.environ.pop(k, None)
lite.load_env(env)
check(os.environ["OWNER_FULL_NAME"] == "Zufarbek Jumayev" and os.environ["X"] == "q", "env file with spaces and quotes")

# ---- Render: settings from environment variables, no disk
st = Settings.from_env({"CONTACTS": "Brother;Otabek Akam\n@aziz_u", "INFO": "Men kimman: Zufarbek;Narx: 100 000 so'm", "DATA_DIR": "/nonexistent"})
check(lite.get_contacts(st) == ["Brother", "Otabek Akam", "@aziz_u"], "CONTACTS env var (; or new lines)")
r2 = Responder(st, FakeTG(), None, None, sleep=instant, log=lambda m: None)
check("Men kimman: Zufarbek" in r2.info() and "Narx: 100 000 so'm" in r2.info() and "Brother — Zufarbekning do'sti" in r2.info(), "INFO env var + built-in tone notes")
st = Settings.from_env({"DATA_DIR": "/nonexistent"})
check("Brother" in lite.get_contacts(st) and "Javohir Aka" in lite.get_contacts(st), "no env, no file -> the built-in default contact list")
check("age" not in Responder(st, FakeTG(), None, None, sleep=instant).info().lower() and "18" not in Responder(st, FakeTG(), None, None, sleep=instant).info(), "built-in defaults contain no personal data")


async def health():
    srv = await lite.health_server(0)
    port = srv.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    await writer.drain()
    data = await reader.read(200)
    writer.close()
    srv.close()
    return data


check(b"200 OK" in run(health()), "health server answers 200 (Render web service / uptime pinger)")

good = "1" + "A" * 352
check(lite.clean_session("  \"" + good[:100] + "\n" + good[100:] + "\"  ") == good, "TG_SESSION: spaces, new lines and quotes are cleaned")
for bad in (good[:300], good + "x", "2" + "A" * 352, ""):
    try:
        lite.clean_session(bad)
        check(False, f"damaged TG_SESSION ({len(bad)} chars) must be rejected")
    except SystemExit as e:
        check("damaged" in str(e) and "353" in str(e), f"damaged TG_SESSION ({len(bad)} chars) -> clear message")

print("\nFAILED:", fails) if fails else print("\nALL PASSED")
sys.exit(1 if fails else 0)
