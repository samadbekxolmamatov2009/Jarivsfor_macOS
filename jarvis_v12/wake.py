"""Wake word: ONLY "hello" (or "hello Jarvis", "wake up") at the START of a short phrase.
You can also say it all at once: "Hello Jarvis, what time is it?"
"""
import re
import time
from openwakeword.utils import download_models
import stt

NAMES = r"(?:jarvis|jarvi[sz]|jervis|jarves|jarvus|javis|jarbis|charvis|jarvice)"
HELLO_RE = re.compile(r"^\W*(?:oh[\s,]+|hey[\s,]+)?(?:hello|hallo|hullo|wake up)\b"
                      r"(?:[\s,]+(?:there|" + NAMES + r"))?[\s,.!?]*", re.I)
MIN_AUDIO = int(16000 * 0.25)
MAX_AUDIO = 16000 * 6


def ensure_models():
    download_models(["hey_jarvis"])          # also fetches the VAD model (first run only)


def find_hello(text):
    m = HELLO_RE.match(text)
    if not m:
        return None
    after = text[m.end():].strip(" ,.!?")
    return after if len(after) > 2 else ""


class HelloWake:
    def __init__(self, listener, power=None):
        self.listener = listener
        self.power = power                     # battery saver (optional)

    def wait(self, should_stop=None):
        """Returns the command said after 'hello' ('' if none), or None if interrupted."""
        while True:
            if should_stop and should_stop():
                return None
            audio = self.listener.listen(wait_seconds=2)
            if audio is None or not (MIN_AUDIO <= len(audio) <= MAX_AUDIO):
                continue
            level = getattr(stt.config, "WAKE_MIN_LEVEL", 0.025)
            if self.power:
                level = self.power.wake_level(level)
            if float(abs(audio).max()) < level:
                continue                       # too quiet = far away (TV, next room): don't even check
            try:                               # battery: tiny model (74 MB) just to hear "hello"
                text, score = stt.transcribe_scored(audio, stt.WAKE_CHECK_MODEL)
            except Exception:
                text, score = stt.transcribe_scored(audio)
            if not text:
                continue
            command = find_hello(text)
            if command is None:
                if self.power:                 # battery: noisy room -> check less often
                    self.power.note_miss()
                    gap = self.power.check_gap()
                    if gap:
                        time.sleep(gap)
                continue                       # not a wake phrase — nothing is kept
            if not score["ok"]:
                print(f"   (unsure '{text}' — ignored, confidence {score['logprob']:.2f}, "
                      f"no-speech {score['no_speech']:.2f})", flush=True)
                continue
            print(f"   (heard '{text}', confidence {score['logprob']:.2f})", flush=True)
            if command:                        # "hello jarvis, <command>": read the command accurately once
                again = find_hello(stt.transcribe(audio))
                command = again if again else command
            return command
