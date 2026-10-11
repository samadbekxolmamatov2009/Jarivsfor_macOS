"""Hands: instant Mac commands. Returns a reply string, or None -> the question goes to the Brain."""
import datetime
import os
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.parse

import requests
import config
from .math_solver import solve_math, solve_written
from . import problem_gen, screen, telegram, memory, calendar_mac, phone_call, ms_test, ms_docs, web, docs
from . import tg_call
from .tasks import TaskCommands
from .focus import Focus
from .lang import detect as detect_lang
from .when import parse_when, say_time, say_day
from .understand import simplify, looks_like_command, rewrite_with_ai
from .telegram_user import TelegramUser, speakable, parse_username, NOT_SET as TG_USER_NOT_SET

BROWSER = getattr(config, "BROWSER", "Brave Browser")
ME = config.ADDRESS_AS
NOTES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notes.txt")

APPS = {
    "brave": "Brave Browser", "browser": "Brave Browser", "safari": "Safari",
    "chrome": "Google Chrome", "telegram": "Telegram", "music": "Music", "spotify": "Spotify",
    "calculator": "Calculator", "notes": "Notes", "terminal": "Terminal", "finder": "Finder",
    "vs code": "Visual Studio Code", "vscode": "Visual Studio Code", "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code", "settings": "System Settings", "system settings": "System Settings",
    "calendar": "Calendar", "mail": "Mail", "messages": "Messages", "facetime": "FaceTime",
    "photos": "Photos", "word": "Microsoft Word", "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint", "app store": "App Store", "activity monitor": "Activity Monitor",
}
SITES = {
    "youtube": "https://youtube.com", "gmail": "https://mail.google.com", "github": "https://github.com",
    "instagram": "https://instagram.com", "claude": "https://claude.ai", "google": "https://google.com",
    "telegram web": "https://web.telegram.org", "chatgpt": "https://chatgpt.com",
}
WORD_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
             "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45,
             "fifty": 50, "sixty": 60, "ninety": 90}
NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUMS, key=len, reverse=True)) + r")"
PRE = r"^(?:hey |ok |okay )?(?:jarvis )?(?:please |can you |could you |would you |will you )*"
DURATION = re.compile(NUM + r"[ -](seconds?|secs?|minutes?|mins?|hours?|hrs?)\b")


# ------------------------------------------------------------------ helpers
def normalize(text):
    t = text.lower()
    for ch in "‘’ʻʼ`":
        t = t.replace(ch, "'")
    t = re.sub(r"(?<!\d)[.,](?!\d)|[!?;\"]|(?<!\d):|:(?!\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _osa(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()


def _notify(text):
    safe = text.replace('"', "'")
    _osa(f'display notification "{safe}" with title "Jarvis" sound name "Glass"')


def _open_url(url):
    if subprocess.run(["open", "-a", BROWSER, url], capture_output=True).returncode != 0:
        subprocess.run(["open", url])


def parse_duration(t):
    total = 0.0
    for m in DURATION.finditer(t):
        n = m.group(1)
        n = float(n) if n[0].isdigit() else WORD_NUMS[n]
        unit = m.group(2)[0]
        total += n * {"s": 1, "m": 60, "h": 3600}[unit]
    if "half an hour" in t:
        total += 1800
    return int(total)


def say_duration(sec):
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    for n, word in ((h, "hour"), (m, "minute"), (s, "second")):
        if n:
            parts.append(f"{n} {word}{'s' if n != 1 else ''}")
    return " and ".join(parts) if parts else "0 seconds"


def _clean_target(s):
    s = re.sub(r"^(the|my|up)\s+", "", s.strip())
    s = re.sub(r"\s+(app|application|for me|please|now)$", "", s)
    return s.strip()


SKIP_PATHS = ("/Library/", "/venv/", "/.cache/", "/node_modules/", "/.Trash/", "/site-packages/", "/.git/")


def find_files(query):
    """Spotlight search in your home folder, newest first."""
    home = os.path.expanduser("~")
    words = sorted(re.findall(r"[a-z0-9]+", query.lower()), key=len, reverse=True)
    for q in [query] + words:
        if len(q) < 3:
            continue
        out = subprocess.run(["mdfind", "-onlyin", home, "-name", q],
                             capture_output=True, text=True, timeout=8).stdout.splitlines()
        hits = [p for p in out if p and not any(x in p for x in SKIP_PATHS)
                and not os.path.basename(p).startswith(".")]
        if hits:
            return sorted(hits, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return []


def clipboard():
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------ skills
class Skills:
    def __init__(self, brain, voice):
        self.brain = brain
        self.voice = voice
        self.timers = []
        self.stopwatch = None
        self.pending = None          # (action, time) waiting for "yes"
        self.last_file = None        # last generated worksheet
        self.last_title = ""
        self.tg = TelegramUser()
        self.awaiting = None         # (callback, time): next thing you say goes to this callback
        self.remote = None           # phone control (set by main.py)
        self.scheduler = None        # scheduled posts / briefing (set by main.py)
        self.announce = lambda text: self.voice.speak(text)   # main.py replaces with a HUD-aware version
        self.focus = Focus(lambda text: self.announce(text))
        self.resume_items = None     # what's left after "stop" while reading a document
        self.power = None            # battery saver (set by main.py)
        self.tasks = TaskCommands(self, parse_duration)

    def reset(self):
        """Called when a conversation ends, so a half-finished question never lingers."""
        self.awaiting = None

    # ---------- timers & reminders ----------
    def _schedule(self, seconds, message):
        def fire():
            _notify(message)
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
            self.announce(message)
        t = threading.Timer(seconds, fire)
        t.daemon = True
        t.start()
        self.timers = [x for x in self.timers if x.is_alive()] + [t]

    def _timer(self, t):
        sec = parse_duration(t)
        if not sec:
            return f"For how long, {ME}? Say for example, set a timer for five minutes."
        self._schedule(sec, f"{ME.capitalize()}, your {say_duration(sec)} timer is done.")
        return f"Timer set for {say_duration(sec)}."

    def _reminder(self, t):
        rest = re.search(r"remind me (.+)", t).group(1)
        sec = parse_duration(rest)
        m = re.search(r"\bto (.+)", rest)
        task = m.group(1) if m else rest
        task = re.sub(r"\b(in|after)\s+" + NUM + r".*?\b(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
                      "", task).strip()
        if not sec:
            return "When should I remind you? For example, remind me in ten minutes to call mom."
        self._schedule(sec, f"Reminder, {ME}: {task}.")
        return f"I'll remind you to {task} in {say_duration(sec)}."

    def _cancel_timers(self):
        n = sum(1 for x in self.timers if x.is_alive())
        for x in self.timers:
            x.cancel()
        self.timers = []
        return "All timers cancelled." if n else "There are no active timers."

    # ---------- info ----------
    def _battery(self):
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
        pct = re.search(r"(\d+)%", out)
        if not pct:
            return "I couldn't read the battery status."
        state = "charging" if "charging;" in out and "discharging" not in out else \
                "fully charged" if "charged" in out else "on battery"
        left = re.search(r"(\d+):(\d+) remaining", out)
        extra = f", about {int(left.group(1))} hours and {int(left.group(2))} minutes left" \
            if left and state == "on battery" else ""
        return f"Battery is at {pct.group(1)} percent, {state}{extra}."

    def _weather(self, t):
        m = re.search(r"weather (?:in|for|at) ([a-z][a-z \-]+)", t)
        city = m.group(1).strip() if m else config.CITY
        try:
            r = requests.get(f"https://wttr.in/{urllib.parse.quote(city)}",
                             params={"format": "%C|%t|%f", "m": ""}, timeout=5)
            cond, temp, feels = r.text.strip().split("|")
            num = lambda x: re.sub(r"[^\d\-]", "", x).lstrip("+")
            return (f"In {city.title()} it's {cond.lower()}, {num(temp)} degrees, "
                    f"feels like {num(feels)}.")
        except Exception:
            return "I can't reach the weather service right now."

    # ---------- media ----------
    def _media(self, action):
        for app in ("Spotify", "Music"):
            if _osa(f'application "{app}" is running') == "true":
                _osa(f'tell application "{app}" to {action}')
                return app
        if action == "play":
            _osa('tell application "Music" to play')
            return "Music"
        return None

    def _youtube_play(self, query):
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        try:
            html = requests.get("https://www.youtube.com/results", params={"search_query": query},
                                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"},
                                timeout=4).text
            m = re.search(r'"videoId":"([\w-]{11})"', html)
            if m:
                url = "https://www.youtube.com/watch?v=" + m.group(1)
        except Exception:
            pass
        _open_url(url)
        return f"Playing {query} on YouTube."

    # ---------- apps ----------
    def _open(self, target):
        target = _clean_target(target)
        for key, url in SITES.items():
            if target == key or target.startswith(key + " "):
                _open_url(url)
                return f"Opening {key.title()}."
        app = APPS.get(target) or next((v for k, v in APPS.items() if k in target), None) or target.title()
        if subprocess.run(["open", "-a", app], capture_output=True).returncode == 0:
            return f"{app} is open."
        if re.search(r"\.(com|org|net|uz|io|ai)\b", target):
            _open_url("https://" + target.replace(" ", ""))
            return f"Opening {target}."
        return f"I couldn't find an app called {target}."

    def _quit(self, target):
        target = _clean_target(target)
        app = APPS.get(target) or next((v for k, v in APPS.items() if k in target), None) or target.title()
        _osa(f'tell application "{app}" to quit')
        return f"{app} closed."

    # ---------- new in v5 ----------
    def _files(self, query, open_it):
        query = re.sub(r"\b(?:file|files|document|folder|called|named|the|my|a)\b", " ", query).strip()
        if not query:
            return "Which file should I look for?"
        hits = find_files(query)
        if not hits:
            return f"I couldn't find any file matching {query}."
        name = os.path.basename(hits[0])
        subprocess.run(["open", hits[0]] if open_it else ["open", "-R", hits[0]])
        more = f" I found {len(hits)} matches; this is the most recent." if len(hits) > 1 else ""
        return (f"Opening {name}." if open_it else f"Found {name}. I've shown it in Finder.") + more

    def _briefing(self):
        now = datetime.datetime.now()
        h = now.hour
        part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
        parts = [f"Good {part}, {ME}. It's {now.strftime('%-I:%M %p')}, {now.strftime('%A, %B %-d')}."]
        w = self._weather("")
        if "can't reach" not in w:
            parts.append(w)
        parts.append(self._battery())
        try:
            evs = calendar_mac.events(now.date(), 1)
            if evs:
                parts.append("Today: " + ", ".join(f"{t} at {say_time(s.hour, s.minute)}" for s, t, _ in evs[:4]) + ".")
        except Exception:
            pass
        soon = []
        for fact in memory.facts():
            w = parse_when(fact)
            if w["date"] and 0 <= (w["date"] - now.date()).days <= 7:
                soon.append(memory.as_you(fact))
        if soon:
            parts.append("Coming up: " + "; ".join(soon[:3]) + ".")
        try:
            if self.tg.ready():
                n = len(self.tg.unread())
                if n:
                    parts.append(f"You have unread Telegram messages in {n} chat{'s' if n > 1 else ''}.")
        except Exception:
            pass
        line = self.tasks.briefing_line()
        if line:
            parts.append(line)
        active = sum(1 for x in self.timers if x.is_alive())
        if active:
            parts.append(f"You have {active} active timer{'s' if active > 1 else ''}.")
        if os.path.exists(NOTES_FILE):
            lines = [l.split("] ", 1)[-1].strip() for l in open(NOTES_FILE, encoding="utf-8") if l.strip()]
            if lines:
                parts.append(f"Your latest note: {lines[-1]}.")
        return " ".join(parts)

    def _storage(self):
        du = shutil.disk_usage(os.path.expanduser("~"))
        return f"You have {du.free // 10**9} gigabytes free out of {du.total // 10**9}."

    # ---------- v6: work skills ----------
    def _confirm(self, question, action):
        self.pending = (action, time.time())
        return question + " Say yes to confirm."

    def _screen_solve(self, whole=False):
        if not whole:
            self.voice.speak("Select the problem with your mouse.")
        path = screen.capture(select=not whole)
        if not path:
            return "Cancelled."
        try:
            lines = screen.ocr(path)
        except Exception as e:
            print("⚠️  OCR error:", e, flush=True)
            return "I couldn't read the screen. Please make sure pyobjc is installed."
        if not lines:
            return ("I couldn't read any text there. If this keeps happening, allow Screen Recording "
                    "for python in System Settings, then restart me.")
        print("   OCR:", " | ".join(lines)[:300], flush=True)
        results = []
        for line in lines:
            ans = solve_written(line)
            if ans:
                results.append((line.strip(), ans))
            if len(results) >= 6:
                break
        if not results:
            joined = solve_written(" ".join(lines))
            if joined:
                results = [(" ".join(lines), joined)]
        if results:
            subprocess.run(["pbcopy"], input="\n".join(f"{q}  →  {a}" for q, a in results), text=True)
            if len(results) == 1:
                return f"{results[0][1]} I've copied it to your clipboard."
            said = " ".join(f"Number {i}: {a}" for i, (_, a) in enumerate(results, 1))
            return said + " I've copied all the answers to your clipboard."
        text = "\n".join(lines)[:1500]
        return {"ask": "This text was read from the user's screen:\n\n" + text +
                "\n\nIf it contains a math problem, solve it and state the final answer. "
                "Otherwise summarize it. Use at most three spoken sentences."}

    def _screen_read(self, t):
        path = screen.capture(select=False)
        if not path:
            return "Cancelled."
        try:
            lines = screen.ocr(path)
        except Exception:
            return "I couldn't read the screen."
        if not lines:
            return "I don't see any text. Screen Recording permission may be missing for python."
        text = "\n".join(lines)
        if "read" in t and len(text) < 300:
            return text
        return {"ask": "This is the text currently on the user's screen:\n\n" + text[:2500] +
                "\n\nSummarize what it is about in two or three spoken sentences."}

    def _worksheet(self, t):
        topic, grade, n = problem_gen.parse_request(t)
        problems = problem_gen.make_problems(topic, grade, n)
        path, title = problem_gen.build_docx(topic, grade, problems)
        try:
            pdf = ms_docs.worksheet_pdf(path, title, grade, problems)
        except Exception as e:
            print("⚠️  PDF:", e, flush=True)
            pdf = path
        self.last_file, self.last_title = pdf, f"{title}, {grade}-sinf"
        subprocess.Popen(["open", path])
        name = {"fractions": "fraction", "percentages": "percentage", "equations": "equation",
                "quadratic": "quadratic equation", "powers": "power", "mixed": "mixed"}.get(topic, topic)
        return (f"Done. {len(problems)} {name} problems for grade {grade}, with an answer key. "
                f"They're in the Jarvis Tests folder on your Desktop.")

    def _telegram(self, t, text):
        if not telegram.ready():
            return telegram.NOT_SET
        if re.search(r"\b(?:clipboard|copied)\b", t):
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            preview = " ".join(clip.split()[:8])
            return self._confirm(f"I'll post the text you copied, {len(clip)} characters, starting with: {preview}.",
                                 lambda: (telegram.post_text(clip), "Posted to your channel.")[1])
        if re.search(r"\b(?:test|worksheet|file|document|problems|quiz)\b", t):
            if not self.last_file or not os.path.exists(self.last_file):
                return "I haven't made a test yet. Ask me to make one first."
            path = self.last_file
            caption = f"📝 {self.last_title}"
            return self._confirm(f"I'll post the latest test, {self.last_title}, to your channel.",
                                 lambda: (telegram.post_file(path, caption), "The test is posted.")[1])
        m = re.search(r"(?:channel|telegram)[\s,:]+(?:saying |that )?(.+)$", text, re.I)
        if m and len(m.group(1).split()) >= 2:
            msg = m.group(1).strip()
            return self._confirm(f"I'll post: {msg}.", lambda: (telegram.post_text(msg), "Posted.")[1])
        return "What should I post? Say: post my clipboard to the channel, or post the test to the channel."

    # ---------- v7: personal Telegram ----------
    def _tg_messages(self):
        if not self.tg.ready():
            return TG_USER_NOT_SET
        try:
            chats = self.tg.unread()
        except Exception as e:
            return f"I couldn't reach Telegram: {e}."
        if not chats:
            return "No new messages."
        names = ", ".join(speakable(n) for n, _, _ in chats[:5])
        say = [(f"You have unread messages from {names}.", "en")]
        for name, count, text in chats[:3]:
            say += [(f"{speakable(name)} wrote:", "en"), (text[:300], detect_lang(text))]
        return {"say": say}

    def _tg_read_chat(self, who):
        if not self.tg.ready():
            return TG_USER_NOT_SET
        d = self.tg.find(who)
        if not d:
            return f"I couldn't find {who} in your Telegram chats."
        msgs = self.tg.last_messages(d, 3)
        if not msgs:
            return f"There are no messages with {speakable(d.name)}."
        say = []
        for out, m in msgs:
            say += [("You wrote:" if out else f"{speakable(d.name)} wrote:", "en"), (m[:300], detect_lang(m))]
        return {"say": say}

    def _tg_send(self, rest, what="text", strict=True):
        """rest = spoken words after the verb, e.g. 'aziz i will be late'."""
        if not self.tg.ready():
            return TG_USER_NOT_SET if strict else None
        rest = re.sub(r"^(?:the|my)\s+", "", rest.strip(), flags=re.I)
        if what != "text":
            rest = re.sub(r"\s+(?:group|chat)$", "", rest, flags=re.I)
        words = rest.split()
        try:
            if what == "text":
                d, msg = self.tg.split_name_message(words)
            else:
                d, msg = self.tg.find(rest), ""
        except Exception as e:
            return f"I couldn't reach Telegram: {e}." if strict else None
        if not d:
            return f"I couldn't find {words[0] if what == 'text' and words else rest} in your Telegram chats." \
                if strict else None
        if what == "clipboard":
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            preview = " ".join(clip.split()[:8])
            who = speakable(d.name)
            return self._confirm(f"Send the text you copied to {who}? It starts with: {speakable(preview)}.",
                                 lambda: (self.tg.send(d, clip), f"Sent to {who}.")[1])
        if what == "file":
            if not self.last_file or not os.path.exists(self.last_file):
                return "I haven't made a test yet."
            path, cap = self.last_file, f"📝 {self.last_title}"
            who = speakable(d.name)
            return self._confirm(f"Send the latest test, {self.last_title}, to {who}?",
                                 lambda: (self.tg.send(d, cap, file=path), f"Sent to {who}.")[1])
        who = speakable(d.name)
        if not msg:
            return f"What should I tell {who}? Say it in one go, for example: tell {who.split()[0]} I'll be late."
        return self._confirm_send(d, msg)

    # ---------- v8: open chat & spelled usernames ----------
    def _ask(self, question, callback):
        self.awaiting = (callback, time.time())
        return question

    def _telegram_window_chat(self):
        """Name of the chat open in the Telegram app window (needs Accessibility permission)."""
        title = subprocess.run(["osascript", "-e",
                                'tell application "System Events" to if exists process "Telegram" then '
                                'get name of front window of process "Telegram"'],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        title = re.sub(r"\s*[–—-]\s*telegram$|^\(\d+\)\s*", "", title, flags=re.I).strip()
        if not title or title.lower() in ("telegram", "chats", "settings", "contacts", "missing value"):
            return None
        return self.tg.find(title)

    def _this_chat(self):
        """(dialog, how) — the open chat if we can see it, otherwise your most recent chat."""
        try:
            d = self._telegram_window_chat()
            if d:
                return d, "open"
        except Exception:
            pass
        return self.tg.top_chat(), "recent"

    def _confirm_send(self, d, msg, how="open"):
        who = speakable(d.name)
        lead = f"Your most recent chat is {who}. Send there: " if how == "recent" else f"Send to {who}: "
        shown = msg if msg[-1:] in ".!?" else msg + "."
        return self._confirm(lead + shown, lambda: (self.tg.send(d, msg), f"Sent to {who}.")[1])

    def _to_this_chat(self, msg):
        if not self.tg.ready():
            return TG_USER_NOT_SET
        d, how = self._this_chat()
        if not d:
            return "I can't tell which chat is open."
        if msg == "__clipboard__":
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            who = speakable(d.name)
            lead = f"Your most recent chat is {who}. Send your copied text there?" if how == "recent" \
                else f"Send the text you copied to {who}?"
            return self._confirm(lead, lambda: (self.tg.send(d, clip), f"Sent to {who}.")[1])
        if not msg:
            return self._ask(f"What should I send to {speakable(d.name)}?",
                             lambda text, t: self._confirm_send(d, text.strip(), how))
        return self._confirm_send(d, msg, how)

    def _to_username(self, spoken, msg=None):
        if not self.tg.ready():
            return TG_USER_NOT_SET
        name = parse_username(spoken) if spoken else None
        if not name:
            return self._ask("Please spell the username.", lambda text, t: self._to_username(text, msg))
        d = self.tg.by_username(name)
        if not d:
            return f"I couldn't find the username {' '.join(name)}. Please check the spelling."
        who = speakable(d.name)
        if msg == "__clipboard__":
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            return self._confirm(f"Found {who}. Send your copied text?",
                                 lambda: (self.tg.send(d, clip), f"Sent to {who}.")[1])
        if msg:
            return self._confirm_send(d, msg)
        return self._ask(f"Found {who}. What should I say?",
                         lambda text, t: self._confirm_send(d, text.strip()))

    # ---------- v9: memory ----------
    def _remember(self, fact):
        fact = memory.add(fact)
        return f"Got it. I'll remember that {memory.as_you(fact)}."

    def _recall(self):
        f = memory.facts()
        if not f:
            return "You haven't asked me to remember anything yet."
        last = f[-5:]
        cap = lambda x: x[:1].upper() + x[1:]
        return "You told me: " + ". ".join(cap(memory.as_you(x)) for x in last) + "."

    # ---------- v9: calendar ----------
    def _calendar_list(self, t):
        w = parse_when(t)
        day = w["date"] or datetime.date.today()
        span = 7 if re.search(r"\bthis week\b|\bweek\b", t) else 1
        try:
            evs = calendar_mac.events(day, span)
        except Exception as e:
            print("⚠️  Calendar:", e, flush=True)
            return "I couldn't read your calendar. Please allow Jarvis to control Calendar in System Settings."
        when = "this week" if span == 7 else say_day(day)
        if not evs:
            return f"Nothing on your calendar {when}."
        items = []
        for start, title, allday in evs[:6]:
            at = "all day" if allday else "at " + say_time(start.hour, start.minute)
            items.append(f"{title} {at}" + (f" on {start.strftime('%A')}" if span == 7 else ""))
        n = len(evs)
        return f"{when.capitalize()} you have {n} event{'s' if n > 1 else ''}: " + ", ".join(items) + "."

    def _calendar_add(self, text, t):
        w = parse_when(t)
        title = t
        for piece in w["spans"]:
            title = title.replace(piece, " ")
        title = re.sub(r"^(?:add|put|schedule|create|make|set)\b|\b(?:to|in|on|into) (?:my |the )?calendar\b|"
                       r"\bcalendar\b|\ban? event\b|\bcalled\b|\bnamed\b", " ", title)
        title = re.sub(r"^\s*(?:a|an|the|new|my)\s+", " ", re.sub(r"\s+", " ", title)).strip(" ,.")
        title = title[:1].upper() + title[1:] if title else "Event"

        def confirm(when_info):
            day = when_info["date"] or datetime.date.today()
            start = datetime.datetime.combine(day, datetime.time(when_info["hour"], when_info["minute"]))
            mins = when_info["minutes"]
            dur = "" if mins == 60 else f" for {mins} minutes"
            return self._confirm(f"Add {title} {say_day(day)} at {say_time(start.hour, start.minute)}{dur}?",
                                 lambda: f"Added to your {calendar_mac.add(title, start, mins)} calendar.")

        if not w["has_time"]:
            day = w["date"]
            def got_time(answer, t2):
                w2 = parse_when(("at " if re.match(r"^\d", answer) else "") + answer)
                if not w2["has_time"]:
                    return "Sorry, I didn't catch the time. Please try again."
                if day:
                    w2["date"] = day
                w2["minutes"] = w["minutes"]
                return confirm(w2)
            return self._ask(f"At what time should I add {title}?", got_time)
        return confirm(w)

    # ---------- v11: Milliy Sertifikat test ----------
    def _ms_test(self):
        variant = random.randint(100, 999)
        items = ms_test.make_test(variant)
        path = ms_docs.ms_docx(items, variant)
        try:
            pdf = ms_docs.ms_pdf(items, variant, path)
        except Exception as e:
            print("⚠️  PDF:", e, flush=True)
            pdf = path
        self.last_file, self.last_title = pdf, f"Milliy Sertifikat, matematika, variant {variant}"
        subprocess.Popen(["open", pdf])
        return (f"Done. Milliy Sertifikat practice test, variant {variant}: 32 multiple choice, 3 matching and "
                "10 open questions, with an answer key. Word and PDF files are in the Jarvis Tests folder.")

    # ---------- v11: channel quiz & schedule ----------
    def post_quiz_now(self):
        item = ms_test.one_quiz()
        n = self.scheduler.next_quiz_number() if self.scheduler else 1
        telegram.post_quiz(f"🧮 Kunlik masala #{n}\n\n{item['q']}",
                           [f"{'ABCD'[k]}) {o}" for k, o in enumerate(item["options"])], item["answer"],
                           f"To'g'ri javob: {'ABCD'[item['answer']]}) {item['answer_text']}")
        return f"Quiz number {n} is posted to your channel."

    def post_text_now(self, text):
        telegram.post_text(text)

    def _need_time(self, what, then):
        return self._ask(f"At what time should I {what}?", lambda ans, t2: then(parse_when(
            ("at " if re.match(r"^\d", ans) else "") + ans)))

    def _schedule_quiz(self, t):
        if not telegram.ready():
            return telegram.NOT_SET
        if not self.scheduler:
            return "The scheduler isn't running."
        def go(w):
            if not w["has_time"]:
                return "Sorry, I didn't catch the time."
            hhmm = f"{w['hour']:02d}:{w['minute']:02d}"
            return self._confirm(f"Post a math quiz to your channel every day at {say_time(w['hour'], w['minute'])}?",
                                 lambda: (self.scheduler.add("quiz", hhmm, replace=True),
                                          f"Done. A new quiz will be posted every day at {say_time(w['hour'], w['minute'])}.")[1])
        w = parse_when(t)
        return go(w) if w["has_time"] else self._need_time("post the daily quiz", go)

    def _schedule_post(self, t):
        if not telegram.ready():
            return telegram.NOT_SET
        clip = clipboard()
        if not clip:
            return "Your clipboard is empty. Copy the post first."
        def go(w):
            if not w["has_time"]:
                return "Sorry, I didn't catch the time."
            day = w["date"] or datetime.date.today()
            hhmm = f"{w['hour']:02d}:{w['minute']:02d}"
            preview = " ".join(clip.split()[:6])
            return self._confirm(f"Post your copied text, starting with {speakable(preview)}, {say_day(day)} at "
                                 f"{say_time(w['hour'], w['minute'])}?",
                                 lambda: (self.scheduler.add("post", hhmm, text=clip, once=day.isoformat()),
                                          f"Scheduled for {say_day(day)} at {say_time(w['hour'], w['minute'])}.")[1])
        w = parse_when(t)
        return go(w) if w["has_time"] else self._need_time("post it", go)

    def _schedule_briefing(self, t):
        w = parse_when(t)
        if not w["has_time"]:
            return self._need_time("give you the morning briefing", lambda w2: self._schedule_briefing(
                f"at {w2['hour']}:{w2['minute']:02d}") if w2["has_time"] else "Sorry, I didn't catch the time.")
        self.scheduler.add("briefing", f"{w['hour']:02d}:{w['minute']:02d}", replace=True)
        return f"Done. I'll give you a briefing every day at {say_time(w['hour'], w['minute'])}."

    def _schedule_list(self):
        jobs = self.scheduler.jobs() if self.scheduler else []
        if not jobs:
            return "Nothing is scheduled."
        names = {"quiz": "daily channel quiz", "briefing": "daily briefing", "post": "one-time channel post"}
        out = []
        for j in jobs:
            h, m = map(int, j["time"].split(":"))
            when = say_time(h, m) + (f" {say_day(datetime.date.fromisoformat(j['once']))}" if j.get("once") else " every day")
            out.append(f"{names[j['kind']]} at {when}")
        return "Scheduled: " + "; ".join(out) + "."

    # ---------- v11: documents ----------
    def _pick_document(self, t):
        m = re.search(r"\b(?:file|document|pdf)\s+(?:called|named)\s+(.+)$", t)
        if m:
            hits = find_files(m.group(1))
            return (hits[0], None) if hits else (None, "named")
        path, problem = docs.selected_file()
        if path or problem in ("permission", "not a document"):
            return path, problem
        return docs.newest_document(), "newest"

    def _document(self, t, summarize):
        path, problem = self._pick_document(t)
        if problem == "permission":
            return ("I'm not allowed to see what's selected in Finder. Please open System Settings, Privacy and "
                    "Security, Automation, and allow python to control Finder. Then ask me again.")
        if problem == "not a document":
            return "The selected item isn't a PDF, Word or text file. Please select a document in Finder."
        if not path:
            return ("I couldn't find a document. Click a PDF or Word file in Finder so it's selected, "
                    "then say: read this file.")
        try:
            text = docs.read_text(path)
        except Exception as e:
            return f"I couldn't read {os.path.basename(path)}: {e}"
        if len(text) < 20:
            return f"{os.path.basename(path)} has no readable text. It may be a scanned document."
        name = os.path.splitext(os.path.basename(path))[0]
        lg = detect_lang(text)
        print(f"   📄 {path}  ({lg}, {len(text)} characters)", flush=True)
        spoken_name = re.sub(r"[_\-]+", " ", name)
        if summarize:
            return {"ask": f"Document name: {name}\n\n{text[:12000]}\n\nSummarize this document in three or four "
                           "short spoken sentences. Say what it is and the main points.", "ctx": 8192}
        where = "" if problem != "newest" else " from your latest files"
        return {"read": text, "lang": lg, "intro": f"Reading {spoken_name}{where}. Say stop anytime, "
                                                   "and continue reading to go on."}

    # ---------- v10: phone calls ----------
    def _call(self, target, via=""):
        via = "facetime" if "face" in via else "telegram" if "telegram" in via else "phone"
        target = re.sub(r"^(?:the |my )", "", target.strip(" ."))
        aliases = {k.lower(): v for k, v in getattr(config, "TELEGRAM_CONTACTS", {}).items()}
        target = aliases.get(target.lower(), target)          # "mom" -> "Onajon"
        number = phone_call.parse_phone(target)
        if via == "telegram":
            if not self.tg.ready():
                return TG_USER_NOT_SET
            d = self.tg.find(target)
            if not d:
                return f"I couldn't find {target} in your Telegram chats."
            user = getattr(d.entity, "username", None)
            if not user:
                return f"{speakable(d.name)} has no Telegram username, so I can't open the chat directly."
            phone_call.open_telegram_chat(user)
            res = tg_call.press_call()
            print(f"   📞 Telegram call button: {res}", flush=True)
            if res == "pressed":
                return f"Calling {speakable(d.name)} on Telegram."
            ph = getattr(d.entity, "phone", None)
            if ph:                                        # button not reachable: offer a normal call instead
                number = "+" + ph.lstrip("+")
                return self._confirm(f"I opened the chat but couldn't press Telegram's call button. "
                                     f"Call {speakable(d.name)}, {phone_call.say_number(number)}, through your iPhone instead?",
                                     lambda: (phone_call.call(number, "phone"), "Calling. If your Mac asks, press Call.")[1])
            return f"I've opened your chat with {speakable(d.name)} in Telegram. Press the phone icon to call."
        name = None
        if not number:
            try:
                found = phone_call.find_contact(target)
            except Exception as e:
                print("⚠️  Contacts:", e, flush=True)
                found = None
            if found:
                name, number = found
            if not number and self.tg.ready():            # fall back to the phone number in Telegram
                try:
                    d = self.tg.find(target)
                    ph = getattr(d.entity, "phone", None) if d else None
                    if ph:
                        name, number = d.name, "+" + ph.lstrip("+")
                except Exception:
                    pass
        if not number:
            return f"I couldn't find a phone number for {target}. You can say the number, for example: call 90 123 45 67."
        who = speakable(name) if name else "this number"
        how = "FaceTime" if via == "facetime" else "your iPhone"
        return self._confirm(f"Call {who}, {phone_call.say_number(number)}, through {how}?",
                             lambda: (phone_call.call(number, via), "Calling. If your Mac asks, press Call.")[1])

    # ---------- v9: phone ----------
    def _connect_phone(self):
        if not self.remote:
            return "Phone control needs your bot token in config dot py. Then restart me."
        code = self.remote.new_pair_code()
        name = f" at {self.remote.bot_name}" if self.remote.bot_name else ""
        _notify(f"Send this code to your Jarvis bot{name}: {code}")
        return (f"Open your Jarvis bot{name} in Telegram and send this code: {' '.join(code)}. "
                "I've also shown it on the screen. It works for 10 minutes.")

    # ---------- main router ----------
    def handle(self, text):
        """Understands non-native English: exact match -> simplified phrasing -> AI rewrite."""
        reply = self._route(text)
        if reply is not None:
            return reply
        easy = simplify(text)
        if easy.lower() != text.lower().strip(" ?.!"):
            reply = self._route(easy)
            if reply is not None:
                print(f"   🔁 understood as: {easy}", flush=True)
                return reply
        if looks_like_command(easy):
            guess = rewrite_with_ai(easy)
            if guess and guess.lower() != easy.lower():
                reply = self._route(guess)
                if reply is not None:
                    print(f"   🧠 understood as: {guess}", flush=True)
                    return reply
        return None

    def _route(self, text):
        t = normalize(text)
        now = datetime.datetime.now()

        # waiting for an answer to my question ("spell the username", "what should I say")?
        if self.awaiting:
            callback, since = self.awaiting
            self.awaiting = None
            if time.time() - since < 45:
                if re.match(r"^(?:cancel|never ?mind|forget it|stop)\b", t):
                    return "Okay, cancelled."
                return callback(text.strip(" ."), t)

        # waiting for "yes"?
        if self.pending:
            action, since = self.pending
            self.pending = None
            if time.time() - since < 30:
                if re.match(r"^(?:yes|yeah|yep|yup|sure|do it|go ahead|confirm|post it|send it|ok|okay)\b", t):
                    try:
                        return action()
                    except Exception as e:
                        return f"Sorry, that failed: {e}."
                return "Okay, cancelled."

        # help
        if re.search(r"what can you do|what are your (commands|skills|features)|help me with commands", t):
            return ("I keep your task list and remind you on your Mac and your phone, send timed Telegram messages, "
                    "save battery, "
                    "I can make Milliy Sertifikat practice tests, post daily quizzes to your channel, answer questions "
                    "from the internet, give exchange rates, read or summarize documents, run focus mode, "
                    "call people through your iPhone, remember facts for you, read and add calendar events, take commands from your phone, "
                    "send and read your Telegram messages, solve the math problem on your screen, make "
                    "worksheets with answer keys, post to your Telegram channel, do exact math and solve equations, find and open your files, read or summarize "
                    "what you copied, give a daily briefing, tell the time, weather, battery and storage, "
                    "set timers, reminders and a stopwatch, take notes, open apps, control Brave and music, "
                    "change the volume, and answer questions.")

        # battery saver
        if re.search(r"\b(?:eco(?: mode)?|battery[ -]?sav(?:er|ing)|power[ -]?sav(?:er|ing)|save (?:my )?battery)\b", t) \
                and self.power:
            if re.search(r"\b(?:off|disable|stop|cancel)\b", t):
                self.power.set_mode("off")
            elif re.search(r"\b(?:auto|automatic|automatically)\b", t):
                self.power.set_mode("auto")
            elif re.search(r"\b(?:on|enable|start|activate|turn on|switch on)\b", t):
                self.power.set_mode("on")
            return self.power.describe()

        # tasks, saved reminders, timed Telegram messages
        r = self.tasks.route(t, re.sub(r"\s+", " ", re.sub(r"(?<!\d)[,!?;:](?!\d)", " ", text)).strip())
        if r is not None:
            return r

        # Milliy Sertifikat test
        if re.search(r"\b(?:ms|m s|mock|certificate|sertifikat|milliy sertifikat|national certificate|full)\s+"
                     r"(?:test|exam|variant)\b", t) and re.search(r"\b(?:make|generate|create|prepare|give|build|new)\b", t):
            return self._ms_test()

        # scheduled channel posts & briefing
        if re.search(r"\b(?:quiz|problem|question)\b", t) and re.search(r"\b(?:every ?day|daily|each day|every morning|every evening)\b", t) \
                and re.search(r"\b(?:post|send|publish|put|share)\b", t):
            return self._schedule_quiz(t)
        if re.search(r"\b(?:post|send|publish)\b", t) and re.search(r"\b(?:quiz|problem of the day)\b", t) and \
                re.search(r"\bchannel\b|\bnow\b", t):
            if not telegram.ready():
                return telegram.NOT_SET
            return self._confirm("Post a new math quiz to your channel now?", self.post_quiz_now)
        if re.search(r"\b(?:post|send|publish)\b.*\bclipboard\b", t) and \
                (parse_when(t)["has_time"] or re.search(r"\b(?:tonight|tomorrow|later)\b", t)):
            return self._schedule_post(t)
        if re.search(r"\bbriefing\b|\bbrief me\b", t) and re.search(r"\b(?:every|daily|each|set|change|move|schedule)\b", t):
            return self._schedule_briefing(t)
        if re.search(r"\b(?:stop|cancel|remove|turn off|delete)\b.*\b(?:daily quiz|quiz|daily problem)\b", t):
            n = self.scheduler.remove("quiz") if self.scheduler else 0
            return "The daily quiz is stopped." if n else "There was no daily quiz scheduled."
        if re.search(r"\b(?:stop|cancel|remove|turn off|delete)\b.*\bbriefing\b", t):
            n = self.scheduler.remove("briefing") if self.scheduler else 0
            return "The daily briefing is off." if n else "There was no daily briefing scheduled."
        if re.search(r"\b(?:stop|cancel|remove|delete)\b.*\bscheduled posts?\b", t):
            n = self.scheduler.remove("post") if self.scheduler else 0
            return f"Cancelled {n} scheduled post{'s' if n != 1 else ''}." if n else "There were no scheduled posts."
        if re.search(r"\bwhat(?:'s| is) scheduled\b|\bscheduled (?:posts|jobs|things)\b|\bshow (?:the |my )?schedule(?:d)? (?:posts|jobs)\b", t):
            return self._schedule_list()

        # continue reading after "stop"
        if re.search(r"^(?:continue|go on|keep going|keep reading|continue reading|resume|resume reading|read on)$", t):
            if self.resume_items:
                items, self.resume_items = self.resume_items, None
                return {"say": items}
            return "There's nothing to continue."

        # screen
        if re.search(r"\b(?:solve|check|answer|do)\b.*\bscreen\b", t) or \
                re.match(PRE + r"(?:solve|check) (?:this|that|these|it)(?: problem| one)?$", t):
            return self._screen_solve(whole=bool(re.search(r"\b(?:whole|entire|full)\b", t)))
        if re.search(r"\b(?:read|what(?:'s| is) on|summari[sz]e|explain)\b (?:me )?(?:my |the )?(?:whole )?screen\b", t):
            return self._screen_read(t)

        # worksheets
        if re.search(r"\b(?:make|generate|create|prepare|give me|write)\b", t) and \
                re.search(r"\b(?:problems?|questions?|exercises?|examples?|tasks?|test|quiz|worksheet)\b", t):
            return self._worksheet(t)

        # personal Telegram  (patterns run on the original text so messages keep their case)
        orig = re.sub(r"\s+", " ", re.sub(r"(?<!\d)[,!?;:](?!\d)", " ", text)).strip()
        M = lambda pat: re.match(PRE + pat, orig, re.I)
        THIS = r"(?:this|the current|current|the open|my current|the same) chat"
        if M(r"(?:send|paste|forward) (?:my |the )?(?:clipboard|copied text|what i copied) (?:to|in|into) " + THIS):
            return self._to_this_chat("__clipboard__")
        m = M(r"(?:send|write|type|reply|say)(?: a)?(?: message| text)?(?: to| in| into)? " + THIS + r"[\s,:.]*(?:saying |that )?(.*)$")
        if m:
            return self._to_this_chat(m.group(1).strip(" ."))
        m = M(r"(?:send|forward) (?:my |the )?(?:clipboard|copied text|what i copied) to (?:the )?(?:username|user name|user) ?(.*)$")
        if m:
            return self._to_username(m.group(1), "__clipboard__")
        m = M(r"(?:send|write)(?: a)?(?: message| text)?(?: to)? (?:the )?(?:username|user name) ?(.*)$")
        if m:
            parts = re.split(r"\b(?:saying|message|and say)\b", m.group(1), maxsplit=1, flags=re.I)
            spoken, msg = parts[0], (parts[1] if len(parts) > 1 else "")
            return self._to_username(spoken, msg.strip(" ,:.") or None)

        m = M(r"(?:read (?:my )?(?:messages|chat) (?:from|with)|what did) (.+?)(?: write| say| send)?\.?$")
        if m:
            return self._tg_read_chat(m.group(1))
        if re.search(r"\b(?:any|new|unread) (?:telegram )?messages\b|\bread my messages\b|"
                     r"\bcheck (?:my )?(?:telegram|messages)\b|\bdo i have (?:any )?(?:new )?messages\b", t):
            return self._tg_messages()
        m = M(r"(?:send|forward) (?:my |the )?(?:clipboard|copied text|what i copied) to (.+?)\.?$")
        if m:
            return self._tg_send(m.group(1), "clipboard")
        m = M(r"(?:send|forward) (?:the |my )?(?:latest |last )?(?:test|worksheet|file) to (?!(?:my |the )?channel)(.+?)\.?$")
        if m:
            return self._tg_send(m.group(1), "file")
        m = M(r"(?:send (?:a )?(?:telegram )?(?:message|text)? ?to|message|text|write to) (?!(?:my |the )?channel)(.+)")
        if m:
            return self._tg_send(m.group(1), "text")
        m = M(r"tell (?!me\b|us\b|a\b|the\b)(.+)")
        if m:
            r = self._tg_send(m.group(1), "text", strict=False)
            if r:
                return r

        # telegram channel
        if re.search(r"\b(?:how many )?(?:subscribers|members|followers)\b", t):
            if not telegram.ready():
                return telegram.NOT_SET
            try:
                return f"Your channel has {telegram.subscribers()} subscribers."
            except Exception as e:
                return f"Telegram said: {e}."
        if re.search(r"\b(?:post|send|share|publish)\b", t) and re.search(r"\bchannel\b", t):
            return self._telegram(t, text)

        # internet
        m = re.search(r"\b(dollar|dollars|usd|euro|euros|eur|ruble|rouble|rubles|rub|yuan|pound|tenge|lira|won|yen|dirham)\b", t)
        if m and re.search(r"\b(?:rate|price|kurs|cost|how much|worth|exchange)\b", t):
            code = web.CURRENCIES[m.group(1)]
            try:
                rate, diff, date, name, nominal = web.currency(code)
            except Exception as e:
                print("⚠️  CBU:", e, flush=True)
                return "I couldn't reach the Central Bank website right now."
            change = "" if not diff else f", {'up' if diff > 0 else 'down'} {web.say_money(abs(diff))} since the last rate"
            return f"The Central Bank rate for {nominal} {name} is {web.say_money(rate)} soum{change}."
        m = M(r"(?:search|look up|check|find|google)(?: it)? (?:on |in )?(?:the )?(?:internet|web|online)(?: for| about)? (.+)") \
            or M(r"(?:ask|search) (?:the )?internet (?:about |for )?(.+)") \
            or M(r"(?:what(?:'s| is) the )?(?:latest|recent|today'?s) news(?: about| on)? ?(.*)") \
            or re.match(r"^(who won .+|what happened .+|what(?:'s| is) happening .+|what(?:'s| is) the latest .+)$", t)
        if m:
            q = (m.group(1) or "").strip(" ?.") or "latest news"
            if re.search(r"news", t) and "news" not in q:
                q = f"latest news {q}".strip()
            prompt = web.answer_prompt(q)
            return {"ask": prompt, "ctx": 6144} if prompt else "I couldn't reach the internet right now."

        # documents
        if re.search(r"\b(?:summari[sz]e|explain|what(?:'s| is) in)\b.*\b(?:file|document|pdf)\b", t):
            return self._document(t, summarize=True)
        if re.search(r"\bread\b.*\b(?:file|document|pdf)\b", t) and "clipboard" not in t:
            return self._document(t, summarize=False)

        # focus mode
        if re.search(r"\b(?:start|begin|turn on|enable)\b.*\b(?:focus|pomodoro|study mode|work mode)\b|^focus mode$", t):
            m = re.search(r"\bfor (\d+) ?(?:minutes?|mins?)\b", t)
            work = int(m.group(1)) if m else 25
            self.focus.start(work=work, brk=5 if work <= 30 else 10, cycles=4)
            return (f"Focus mode on: {work} minutes of work, then a break, 4 rounds. I closed Telegram. "
                    "Say stop focus mode to end.")
        if re.search(r"\b(?:stop|end|cancel|turn off|finish)\b.*\b(?:focus|pomodoro)\b", t):
            return "Focus mode is off." if self.focus.stop() else "Focus mode wasn't on."
        if re.search(r"\bhow (?:much|long)\b.*\b(?:focus|pomodoro|break|left)\b", t) and self.focus.active():
            mins = self.focus.remaining() // 60
            return f"{mins} minutes left in this {self.focus.phase}, round {self.focus.cycle} of {self.focus.cycles}."

        # memory
        if re.search(r"\bwhat (?:do you|did i ask you to) (?:remember|know about me)\b|\bwhat have i told you\b", t):
            return self._recall()
        if re.search(r"^(?:please )?forget (?:everything|all facts|all that i told you)\b", t):
            return self._confirm("Forget everything I remember about you?", lambda: (memory.clear(), "Done. My memory is empty.")[1])
        m = M(r"forget(?: that| about)? (?!(?:our |the |this )?(?:conversation|chat|history)\b)(.+?)\.?$")
        if m:
            gone = memory.forget(m.group(1))
            return "Okay, I've forgotten that." if gone else "I don't remember anything like that."
        m = M(r"remember(?: that)? (.+?)\.?$")
        if m and not re.match(r"^(?:do|did) you remember", t):
            return self._remember(m.group(1))

        # calendar
        if re.search(r"\b(?:calendar|schedule|agenda|plans|events?|meetings?|lessons?|appointments?)\b", t) and \
                re.search(r"^(?:what|whats|what's|do i have|any|show|read|tell me|check)\b", t):
            return self._calendar_list(t)
        m = M(r"(?:add|put|schedule|create)(?: an?| the| new)? (.+)")
        if m and not re.search(r"\b(?:timer|reminder|note|volume)\b", t) and \
                (re.search(r"\bcalendar\b", t) or parse_when(t)["date"] or parse_when(t)["has_time"]):
            return self._calendar_add(text, t)

        # phone
        if re.search(r"\b(?:connect|pair|link) (?:my |the )?(?:phone|telegram)\b", t):
            return self._connect_phone()
        m = M(r"(?:call|phone|ring|dial)(?: to)? (.+?)(?: (?:on|via|with|using|through|in) "
              r"(telegram|facetime|face time|phone|mobile|iphone))?\.?$")
        if m and not re.search(r"\bme\b", m.group(1).split()[0] if m.group(1).split() else ""):
            return self._call(m.group(1), (m.group(2) or "").lower())

        # repeat
        if re.search(r"\b(?:repeat that|say that again|what did you say|come again)\b", t):
            return self.voice.last_text or "I haven't said anything yet."

        # daily briefing
        if re.search(r"^(?:good morning|daily briefing|morning briefing|brief me|give me (?:a |my )?briefing)", t):
            return self._briefing()

        # stopwatch
        if re.search(r"\bstart (?:a |the )?stop ?watch\b", t):
            self.stopwatch = time.time()
            return "Stopwatch started."
        if re.search(r"\b(?:stop|check|how long)\b.*\bstop ?watch\b|\bstop ?watch\b.*\b(?:stop|time)\b", t):
            if not self.stopwatch:
                return "The stopwatch isn't running."
            sec = int(time.time() - self.stopwatch)
            if "stop" in t.split():
                self.stopwatch = None
            return f"{say_duration(sec)}."

        # storage
        if re.search(r"\b(?:storage|disk space|free space)\b", t):
            return self._storage()

        # clipboard
        if re.search(r"\b(?:summari[sz]e|explain)\b.*\b(?:clipboard|what i copied|copied text)\b", t):
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            verb = "Summarize" if "summar" in t else "Explain simply"
            return {"ask": f"{verb} this text in two or three spoken sentences:\n\n{clip[:3000]}"}
        if re.search(r"\b(?:read|what(?:'s| is) (?:in )?)(?: me)? (?:my |the )?clipboard\b|\bwhat did i copy\b", t):
            clip = clipboard()
            if not clip:
                return "Your clipboard is empty."
            return {"read": clip[:6000], "lang": detect_lang(clip)}

        # time & date
        if re.search(r"\bwhat time is it\b|\bwhat(?:'s| is) the time(?: now| right now| please)?$|\btell me the time\b|\bcurrent time\b|^time$", t):
            return f"It's {now.strftime('%-I:%M %p')}."
        if re.search(r"\bwhat(?:'s| is)? (?:the |today'?s )?date\b|\bwhat day\b|\btoday'?s date\b", t):
            return f"Today is {now.strftime('%A, %B %-d')}."

        # timers & reminders
        if re.search(r"\bcancel (?:the |all |my )?(?:timers?|reminders?|alarms?)\b", t):
            return self._cancel_timers()
        if re.search(r"\bremind me\b", t):
            return self._reminder(t)
        if re.search(r"\b(?:set |start )?(?:a |an )?timer\b", t):
            return self._timer(t)

        # notes
        m = re.search(r"\b(?:take|make|write|add) (?:a )?note(?: that)? (.+)|\bnote that (.+)", t)
        if m:
            note = (m.group(1) or m.group(2)).strip()
            with open(NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{now:%Y-%m-%d %H:%M}] {note}\n")
            return "Noted."
        if re.search(r"\b(?:read|what are|show) (?:me )?(?:my )?notes\b", t):
            if not os.path.exists(NOTES_FILE):
                return "You have no notes yet."
            lines = [l.split("] ", 1)[-1].strip() for l in open(NOTES_FILE, encoding="utf-8") if l.strip()]
            last = lines[-3:]
            return f"Your latest notes: " + ". ".join(last) + "." if last else "You have no notes yet."

        # info
        if re.search(r"\bbattery (?:level|status|percent|percentage|life)\b|\bhow much battery\b|\bmy battery\b|^battery$", t):
            return self._battery()
        if re.search(r"\bweather\b|\btemperature outside\b", t):
            return self._weather(t)

        # volume
        m = re.search(r"\bvolume (?:to |at )?(\d{1,3})", t)
        if m:
            v = max(0, min(100, int(m.group(1))))
            _osa(f"set volume without output muted")
            _osa(f"set volume output volume {v}")
            return f"Volume at {v} percent."
        if re.search(r"\bunmute\b", t):
            _osa("set volume without output muted")
            return "Sound is back."
        if re.search(r"\bmute\b", t):
            _osa("set volume with output muted")
            return "Muted."
        if re.search(r"volume up|turn (?:it )?up|louder", t):
            cur = int(_osa("output volume of (get volume settings)") or 50)
            _osa(f"set volume output volume {min(100, cur + 15)}")
            return "Volume up."
        if re.search(r"volume down|turn (?:it )?down|quieter|lower the volume", t):
            cur = int(_osa("output volume of (get volume settings)") or 50)
            _osa(f"set volume output volume {max(0, cur - 15)}")
            return "Volume down."

        # appearance & system
        if re.search(r"\bdark mode\b", t):
            val = "false" if re.search(r"\b(off|disable|turn off)\b", t) else "true"
            _osa(f'tell application "System Events" to tell appearance preferences to set dark mode to {val}')
            return "Dark mode on." if val == "true" else "Dark mode off."
        if re.search(r"\blight mode\b", t):
            _osa('tell application "System Events" to tell appearance preferences to set dark mode to false')
            return "Light mode on."
        if re.search(r"\block (?:the |my )?(?:screen|computer|mac|laptop)\b", t):
            subprocess.Popen(["pmset", "displaysleepnow"])
            return f"Locking the screen, {ME}."

        # memory
        if re.search(r"\b(?:forget|clear|reset) (?:our |the |this )?(?:conversation|chat|memory|history)\b", t):
            self.brain.clear()
            return "Done. Fresh start."

        # browser tabs
        if re.search(r"\bnew tab\b", t):
            _osa(f'tell application "{BROWSER}" to tell front window to make new tab')
            return "New tab."
        if re.search(r"\bclose (?:the |this )?tab\b", t):
            _osa(f'tell application "{BROWSER}" to close active tab of front window')
            return "Tab closed."
        if re.search(r"\b(?:reload|refresh)\b", t):
            _osa(f'tell application "{BROWSER}" to reload active tab of front window')
            return "Reloaded."
        if re.search(r"\bgo back\b", t):
            _osa(f'tell application "{BROWSER}" to go back active tab of front window')
            return "Going back."
        if re.search(r"\bgo forward\b", t):
            _osa(f'tell application "{BROWSER}" to go forward active tab of front window')
            return "Going forward."

        # media
        if re.search(r"\b(?:pause|stop) (?:the )?(?:music|song|playback)\b|^pause$", t):
            return "Paused." if self._media("pause") else "Nothing is playing."
        if re.search(r"\b(?:next|skip) (?:the )?(?:song|track)\b|^skip$", t):
            return "Next track." if self._media("next track") else "Nothing is playing."
        if re.search(r"\bprevious (?:song|track)\b", t):
            return "Previous track." if self._media("previous track") else "Nothing is playing."
        if re.search(r"\b(?:play|resume) (?:some |the |my )?music\b|^resume$", t):
            app = self._media("play")
            return f"Playing on {app}."

        # files
        m = re.match(PRE + r"(?:find|locate|where is|search for|show me) (?:the |my )?(.+?\b(?:file|files|document|folder)\b.*)", t) \
            or re.match(PRE + r"(?:find|locate) (?:my |the )?(.+)", t)
        if m:
            return self._files(m.group(1), open_it=False)
        m = re.match(PRE + r"open (?:the |my )?(?:file|document) (?:called |named )?(.+)", t)
        if m:
            return self._files(m.group(1), open_it=True)

        # exact math
        ans = solve_math(text)
        if ans:
            return ans

        # youtube
        m = re.search(r"\bplay (.+?) on youtube\b|\bsearch youtube for (.+)|\byoutube (?:search )?(.+)", t)
        if m:
            q = next(g for g in m.groups() if g)
            return self._youtube_play(q) if "play" in t else self._search_youtube(q)
        m = re.match(PRE + r"play (?!a game)(.+)", t)
        if m:
            return self._youtube_play(m.group(1))

        # web search
        m = re.match(PRE + r"(?:search|google|look up)(?: for| the web for)? (.+)", t)
        if m:
            q = m.group(1)
            _open_url("https://www.google.com/search?q=" + urllib.parse.quote(q))
            return f"Searching for {q}."

        # apps
        m = re.match(PRE + r"(?:open|launch|start) (.+)", t)
        if m:
            return self._open(m.group(1))
        m = re.match(PRE + r"(?:quit|close) (.+)", t)
        if m:
            return self._quit(m.group(1))

        return None

    def _search_youtube(self, q):
        _open_url("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
        return f"Searching YouTube for {q}."
