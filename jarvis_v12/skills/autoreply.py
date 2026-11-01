"""Auto-reply: Jarvis answers your Telegram messages for you while you are busy.

NO COMMANDS NEEDED: put your people in ~/jarvis/config.py once —
    AUTOREPLY_CONTACTS = ["Aziz", "Brother", "Madina"]
— and from then on Jarvis starts answering them by itself, every time he runs: he reads each new message, understands
it and replies. Nobody else (not even other saved contacts) gets an answer.
Without that line it stays OFF, and you can still manage it by voice or from your phone:
    auto reply on for Aziz          add Aziz to the list (and switch auto-reply on)
    auto reply off for Aziz         remove him
    turn on auto reply              use the list you already made
    auto reply for everyone         every private chat (asks you to confirm)
    turn off auto reply
    auto reply status               who is on the list
It works from your phone's Jarvis bot too.

Guard rails: private chats only (no groups, channels, bots) · replies are marked as written by Jarvis (config
AUTOREPLY_SIGNATURE) · never answers about money, passwords, codes or emergencies — those are sent to YOU on your phone
instead · at most 3 replies per chat per hour and 40 a day · skips a chat if you already answered it yourself · every
reply is copied to your phone so you always see what was said in your name.
Battery: when it is off nothing runs; when on it checks every 60 s (every 3 min on battery or with the screen off).
Config (optional): OWNER_NAME, AUTOREPLY_PERSONA, AUTOREPLY_SIGNATURE.
"""
import json
import os
import random
import re
import threading
import time
from collections import defaultdict, deque

import config
from .lang import detect as detect_lang

FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autoreply.json")
PER_CHAT_HOUR, PER_DAY = 3, 40
# People Jarvis answers with no setup at all (more can be added in config.py: AUTOREPLY_CONTACTS = [...]).
# Telegram names or part of a name; case and apostrophe style don't matter.
DEFAULT_CONTACTS = ["Brother", "NAVOIY-QORAKO'L O'QUV MARKAZI"]
SIGNATURE = getattr(config, "AUTOREPLY_SIGNATURE", "🤖 Jarvis (avto-javob)")

# things a bot must never answer on your behalf — you get a message on your phone instead
SENSITIVE = re.compile(
    r"\b(?:pul|money|деньг\w*|перевод\w*|оплат\w*|karta|card|карт\w*|bank|банк|qarz|долг|loan|kredit|кредит|"
    r"parol\w*|password|пароль|otp|\bkod\b|code|код|sms|token|cvv|pin|"
    r"zudlik|срочно|urgent|emergency|help me|yordam|помоги\w*|авари\w*|avariya|kasalxona|больниц\w*|hospital|"
    r"politsiya|police|полици\w*|o'lim|died|умер\w*)\b", re.I)
LEAK = re.compile(r"(?:as an ai language model|i am an ai developed|openai|anthropic|\bllama\b|system prompt)", re.I)


def _norm(name):
    """Case and apostrophe style don't matter: O'QUV = o‘quv = Oʻquv."""
    return re.sub(r"[ʻʼ‘’`´]", "'", name).casefold().strip()


def clean_reply(text):
    t = " ".join((text or "").split()).strip(" \"'`")
    t = re.sub(r"^(?:reply|answer|javob|message)\s*:\s*", "", t, flags=re.I)
    return t[:400]


class AutoReply(threading.Thread):
    def __init__(self, skills, brain, power, lock, log=print, path=FILE):
        super().__init__(daemon=True)
        self.s, self.brain, self.power, self.lock, self.log = skills, brain, power, lock, log
        self.path = path
        self.poke = threading.Event()
        self.mode = "off"                     # off | list | all
        self.names = []                       # people you allowed
        self.seen = {}                        # chat -> signature of the last message already handled
        self.sent = defaultdict(deque)        # chat -> times of our replies
        self.day = deque()                    # times of all our replies
        self._load()

    # ---------------- settings ----------------
    def _load(self):
        explicit = False                      # did you switch it on/off yourself (voice / phone)?
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("mode") in ("off", "list", "all"):
                self.mode = d["mode"]
                explicit = True
            self.names = [str(n) for n in d.get("names", [])]
        except (OSError, ValueError):
            pass
        cfg = getattr(config, "AUTOREPLY_CONTACTS", None) or []
        for n in list(DEFAULT_CONTACTS) + ([cfg] if isinstance(cfg, str) else list(cfg)):
            if n and n.lower() not in (x.lower() for x in self.names):
                self.names.append(str(n))
        if self.names and not explicit:           # contacts are in config.py -> works with no command at all
            self.mode = "list"

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"mode": self.mode, "names": self.names}, f, ensure_ascii=False)
        os.replace(tmp, self.path)
        self.poke.set()

    def allowed(self, name):
        if self.mode == "all":
            return True
        low = _norm(name)
        # "Aziz" in your list matches the chat "Aziz Karimov" (and the other way round)
        return self.mode == "list" and any(_norm(n) in low or low in _norm(n) for n in self.names if n.strip())

    # ---------------- voice / phone commands ----------------
    def route(self, t, orig):
        """-> reply text, or None when the sentence is not about auto-reply."""
        if not re.search(r"\bauto[ -]?repl(?:y|ies|ying)\b|\bautoresponder\b", t):
            return None
        s = self.s
        if not s.tg.ready():
            return "Auto-reply needs your Telegram account connected first."
        who = re.search(r"\b(?:for|to|with)\s+(?!everyone\b|everybody\b|all\b)(.+)$", t)
        who = re.sub(r"^(?:the |my |a )", "", who.group(1)).strip() if who else ""
        everyone = bool(re.search(r"\b(?:everyone|everybody|all (?:chats|people|contacts))\b", t))
        off = re.search(r"\b(?:off|stop|disable|cancel|remove|delete)\b", t)

        if re.search(r"\b(?:status|who|list|which|is it on|is on)\b", t) and not (who and not off):
            return self.describe()
        if off:
            if who:
                d = s.tg.find(who)
                name = d.name if d else who
                before = len(self.names)
                self.names = [n for n in self.names if n.lower() != name.lower()]
                self._save()
                return f"I won't answer {name} anymore." if len(self.names) < before else f"{name} wasn't on the list."
            self.mode = "off"
            self._save()
            return "Auto-reply is off. I won't answer anyone."
        if everyone:
            return s._confirm("I will answer every private chat in your name, with a note that it's me. Turn it on for everyone?",
                              lambda: (self._set("all"), "Auto-reply is on for everyone. Say turn off auto-reply to stop.")[1])
        if who:
            d = s.tg.find(who)
            if not d:
                return f"I couldn't find {who} in your Telegram chats."
            if getattr(d, "is_user", True) is False:
                return "I only answer private chats, not groups or channels."
            if d.name not in self.names:
                self.names.append(d.name)
            self._set("list")
            return f"Auto-reply is on for {d.name}. I'll answer their messages and copy every reply to your phone."
        if self.names:
            self._set("list")
            return f"Auto-reply is on for {len(self.names)} {'person' if len(self.names) == 1 else 'people'}: " + ", ".join(self.names[:5]) + "."
        return s._ask("Who should I answer for? Say a name, or everyone.",
                      lambda ans, t2: self.route("auto reply on for " + ans if not re.search(r"\beveryone\b", ans.lower())
                                                 else "auto reply for everyone", orig))

    def _set(self, mode):
        self.mode = mode
        self._save()

    def describe(self):
        if self.mode == "off":
            return "Auto-reply is off." + (f" Your list has {', '.join(self.names[:5])}." if self.names else "")
        if self.mode == "all":
            return "Auto-reply is on for everyone."
        return "Auto-reply is on for " + (", ".join(self.names) or "nobody yet") + "."

    # ---------------- the watcher ----------------
    def interval(self):
        slow = self.power.eco() or self.power.screen_off()
        return 180 if slow else 60

    def run(self):
        while True:
            self.poke.clear()
            if self.mode == "off":
                self.poke.wait(900)               # nothing to do: sleep until it is switched on
                continue
            if self.poke.wait(self.interval()):
                continue
            try:
                self.tick()
            except Exception as e:
                self.log(f"❌ Auto-reply: {e}")

    def _budget(self, chat, now):
        for q in (self.sent[chat], self.day):
            while q and now - q[0] > (3600 if q is self.sent[chat] else 86400):
                q.popleft()
        return len(self.sent[chat]) < PER_CHAT_HOUR and len(self.day) < PER_DAY

    def tick(self):
        s = self.s
        if not s.tg.ready():
            return
        with self.lock:
            chats = s.tg.unread()
        for name, count, text in chats:
            sig = f"{count}|{text}"
            if self.seen.get(name) == sig:
                continue
            if not self.allowed(name):
                continue
            self.seen[name] = sig
            self.handle_chat(name, text)

    def notify(self, text):
        r = getattr(self.s, "remote", None)
        if r and getattr(r, "owner", None):
            try:
                r.send(r.owner, text)
            except Exception:
                pass

    def handle_chat(self, name, text):
        s, now = self.s, time.time()
        if SIGNATURE and SIGNATURE.split()[0] in text:
            return                                # another auto-reply bot: never chat with it (no ping-pong)
        with self.lock:
            d = s.tg.find(name)
        if not d or getattr(d, "is_user", True) is False or getattr(getattr(d, "entity", None), "bot", False):
            return                                # groups, channels and bots are never answered
        if self.mode == "all" and getattr(getattr(d, "entity", None), "contact", True) is False:
            return                                # "everyone" still means saved contacts only
        if SENSITIVE.search(text):
            self.notify(f"⚠️ {name} wrote something I won't answer for you:\n{text[:300]}")
            return
        if not self._budget(name, now):
            self.notify(f"ℹ️ Auto-reply limit reached for {name}. Their message:\n{text[:300]}")
            return
        reply = self.compose(d, name, text)
        if not reply:
            self.notify(f"ℹ️ {name} wrote, I had no good answer:\n{text[:300]}")
            return
        time.sleep(random.uniform(5, 15))         # not instant, like a person
        with self.lock:
            last = s.tg.last_messages(d, 1)
            if last and last[-1][0]:              # you answered yourself in the meantime
                return
            s.tg.send(d, f"{reply}\n\n{SIGNATURE}" if SIGNATURE else reply)
        self.sent[name].append(time.time())
        self.day.append(time.time())
        self.log(f"🤖 Auto-replied to {name}")
        self.notify(f"🤖 I answered {name} for you.\n\n{name}: {text[:300]}\nMe: {reply}")

    def compose(self, d, name, text):
        owner = getattr(config, "OWNER_NAME", "the owner")
        persona = getattr(config, "AUTOREPLY_PERSONA", "")
        try:
            with self.lock:
                history = self.s.tg.last_messages(d, 6)
        except Exception:
            history = []
        convo = "\n".join(f"{'Me' if out else name}: {m[:200]}" for out, m in history)
        if str(getattr(config, "AUTOREPLY_LANG", "auto")).lower() == "en":
            lang = "English"                       # config.py: AUTOREPLY_LANG = "en" -> always English
        else:
            lang = {"uz": "Uzbek (Latin letters)", "ru": "Russian", "en": "English"}.get(detect_lang(text), "the same language")
        prompt = (
            f"You are the personal AI assistant of {owner}. You answer Telegram messages for {owner} while they are busy. {persona}\n"
            f"Reply to {name} in {lang}, friendly and natural, 1-2 short sentences. Rules: you are an AI assistant, "
            f"say so if asked; never promise or agree to anything for {owner} (meetings, money, favours); never share "
            f"personal information; if the question needs {owner} personally, say {owner} will answer as soon as they are free. "
            f"Output ONLY the message text.\n\nRecent chat (for context):\n{convo}\n\nNew message from {name}: {text}\n\nYour reply:")
        with self.lock:
            out = " ".join(self.brain.ask_stream(prompt))
        out = clean_reply(out)
        return "" if (not out or LEAK.search(out)) else out
