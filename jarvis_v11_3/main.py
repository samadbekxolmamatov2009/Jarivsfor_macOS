"""J.A.R.V.I.S v11.3 — wakes ONLY on "hello". English, offline.  Run: python main.py"""
import datetime
import os
import re
import subprocess
import threading
import time

import config
import stt
from brain import Brain
from ears import Mic, Listener
from skills import Skills, normalize
from voice import Voice
from wake import HelloWake, ensure_models
from hud_client import HUD
from skills.remote import Remote
from bargein import BargeIn
from skills.scheduler import Scheduler
from skills.docs import sentences as doc_sentences

LOCK = threading.RLock()          # voice and phone never run a command at the same moment

ME = config.ADDRESS_AS
END_WORDS = {"bye", "goodbye", "bye jarvis", "goodbye jarvis", "thanks bye", "thank you bye",
             "that's all", "that is all", "nothing", "never mind", "nevermind", "stop", "cancel",
             "thanks jarvis", "thank you jarvis", "no thanks", "no thank you", "thank you", "thanks"}
SLEEP_RE = re.compile(r"\b(?:go(?:es|ing)? to (?:sleep|slip|bed)|sleep mode|stop listening|"
                      r"good ?night|take a nap)\b|^(?:sleep|slip)$")
SHUTDOWN_RE = re.compile(r"^(?:jarvis )?(?:shut ?down|power off|switch off|turn (?:yourself )?off)(?: jarvis| yourself)?$|\bturn yourself off\b|\bshut yourself down\b")
TOGGLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_toggle.sh")
DEEP_SLEEP_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deep_sleep")


def deep_sleep():
    return os.path.exists(DEEP_SLEEP_FLAG)


def speech_items(reply):
    """{'say': [(text, lang)...]} or {'read': text, 'lang': .., 'intro': ..} -> [(text, lang), ...]"""
    if "say" in reply:
        return list(reply["say"])
    lang = reply.get("lang", "en")
    items = [(reply["intro"], "en")] if reply.get("intro") else []
    return items + [(s, lang) for s in doc_sentences(reply["read"])]


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def ding(sound):
    subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"])


def conversation(listener, mic, brain, voice, skills, hud, first_text=None):
    pending, wait = first_text, 6
    while True:
        if pending:
            text, pending, t0 = pending, None, time.time()
            log(f"🧑 You: {text}")
        else:
            if deep_sleep():
                return
            hud.send("listen")
            audio = listener.listen(wait_seconds=wait)
            if audio is None:
                return
            hud.send("think", "…")
            t0 = time.time()
            if wait == config.FOLLOW_UP_SECONDS:
                # follow-up without "hello": only accept clear speech, not the TV or people nearby
                text, score = stt.transcribe_scored(audio)
                if text and not score["ok"]:
                    log(f"🙉 ignored unclear background speech: '{text[:50]}'")
                    return
            else:
                text = stt.transcribe(audio)
            if not text:
                log("… didn't catch that")
                return
            log(f"🧑 You: {text}   (heard {len(audio) / 16000:.1f}s, stt {time.time() - t0:.2f}s)")

        hud.send("think", text)
        n = normalize(text)
        if SHUTDOWN_RE.search(n):
            voice.speak(f"Shutting down, {ME}. Press the Jarvis button when you need me.")
            subprocess.Popen(["/bin/bash", TOGGLE], start_new_session=True)
            time.sleep(60)
            return
        if SLEEP_RE.search(n) or n in END_WORDS:
            voice.speak(f"Very well, {ME}.")
            return

        t1 = time.time()
        with LOCK:
            reply = skills.handle(text)
            if isinstance(reply, dict) and ("read" in reply or "say" in reply):   # reading aloud, any language
                items = speech_items(reply)
                voice.speak_stream(iter(items))
                if voice.interrupted and len(items) > 3:          # remember where we stopped
                    skills.resume_items = items[max(voice.played - 1, 0):]
                    log(f"⏸  Stopped reading at sentence {voice.played} of {len(items)}")
            elif isinstance(reply, dict):                    # skill wants the brain's help
                voice.speak_stream(brain.ask_stream(reply["ask"], reply.get("ctx")))
            elif reply:
                voice.speak(reply)
            else:
                voice.speak_stream(brain.ask_stream(text))
        first = (voice.first_sound_at or time.time()) - t0
        log(f"⚡ first sound {first:.2f}s  |  total {time.time() - t1:.1f}s")

        mic.flush()
        wait = config.FOLLOW_UP_SECONDS
        ding("Pop")


def main():
    log("J.A.R.V.I.S v11.3 starting...")
    t = time.time()
    ensure_models()
    mic = Mic()
    listener = Listener(mic)
    wake = HelloWake(listener)
    stt.warmup()
    brain = Brain()
    brain.warmup()
    voice = Voice()
    skills = Skills(brain, voice)
    hud = HUD()

    def phone_handle(text):
        with LOCK:
            r = skills.handle(text)
            if isinstance(r, dict) and ("read" in r or "say" in r):
                return " ".join(t for t, _ in speech_items(r))[:3900]
            if isinstance(r, dict):
                return " ".join(brain.ask_stream(r["ask"], r.get("ctx")))
            return r or " ".join(brain.ask_stream(text))

    barge = BargeIn(mic, voice, log)
    voice.on_start = lambda: threading.Thread(target=barge.watch, daemon=True).start()

    def announce(text):
        """Scheduled/background speech: timers, focus mode, daily briefing."""
        if deep_sleep():
            return
        with LOCK:
            hud.send("speak", text)
            voice.speak(text)
            hud.send("sleep")
            mic.flush()

    skills.announce = announce

    def briefing_job():
        text = skills._briefing()
        announce(text)
        if skills.remote and skills.remote.owner:
            try:
                skills.remote.send(skills.remote.owner, "☀️ " + text)
            except Exception:
                pass

    skills.scheduler = Scheduler({"quiz": skills.post_quiz_now, "post": skills.post_text_now,
                                  "briefing": briefing_job}, log=log)
    skills.scheduler.start()
    if skills.scheduler.jobs():
        log(f"⏰ {len(skills.scheduler.jobs())} scheduled job(s) loaded")

    skills.remote = Remote(phone_handle, log=log)
    if skills.remote.start():
        log("📱 Phone control is on (Telegram bot)")
    voice.on_sentence = lambda s: hud.send("speak", s)
    log(f"✅ Loaded in {time.time() - t:.1f}s  |  brain: {brain.model}  |  voice: {voice.engine}")

    if getattr(config, "GREET_ON_START", False):
        voice.speak(f"All systems are online, {ME}.")
    mic.flush()
    log("😴 Sleeping — say 'hello' to wake me")

    while True:
        try:
            if deep_sleep():
                hud.send("sleep")
                log("🔇 Deep sleep — microphone OFF")
                mic.stop()
                while deep_sleep():
                    time.sleep(1)
                mic.start()
                log("🔊 Microphone ON — say 'hello' to wake me")
                continue

            command = wake.wait(should_stop=deep_sleep)
            if command is None:
                continue

            log("☀️  Awake")
            hud.send("listen", command)
            if not command:
                voice.speak(f"Yes, {ME}?")
                mic.flush()
                ding("Pop")
            conversation(listener, mic, brain, voice, skills, hud, first_text=command or None)
            skills.reset()
            hud.send("sleep")
            mic.flush()
            log("😴 Sleeping — say 'hello' to wake me")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"❌ Error: {e}")
            time.sleep(1)
            mic.flush()

    log("Jarvis offline.")


if __name__ == "__main__":
    main()
