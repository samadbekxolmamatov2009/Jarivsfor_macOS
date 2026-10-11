"""While Jarvis is talking, listen for a short 'stop' from you and go quiet at once.
The mic also hears Jarvis himself, so words he is saying right now don't count."""
import queue
import re
import time
from collections import deque

import numpy as np

import stt
from ears import FRAME_SEC

STOP_WORDS = {"stop", "enough", "wait", "quiet", "silence", "shut", "pause", "halt"}
WINDOW_SEC, EVERY_SEC = 1.6, 1.0


class BargeIn:
    def __init__(self, mic, voice, log=print, power=None):
        self.mic, self.voice, self.log, self.power = mic, voice, log, power

    def watch(self):
        buf = deque(maxlen=int(WINDOW_SEC / FRAME_SEC))
        last = time.time()
        every = self.power.barge_gap(EVERY_SEC) if self.power else EVERY_SEC     # battery saver: check less often
        started = time.time()
        while self.voice.speaking or time.time() - started < 1.0:
            try:
                buf.append(self.mic.q.get(timeout=0.2))
            except queue.Empty:
                continue
            if not self.voice.speaking or time.time() - last < every or len(buf) < buf.maxlen // 2:
                continue
            last = time.time()
            audio = np.concatenate(buf).astype(np.float32) / 32768.0
            if float(np.abs(audio).max()) < 0.02:          # silence — nothing to check
                continue
            try:
                heard = stt.transcribe_fast(audio).lower()
            except Exception:
                continue
            words = set(re.findall(r"[a-z]+", heard))
            own = set(re.findall(r"[a-z]+", self.voice.recent_text().lower()))
            if (words & STOP_WORDS) - own:
                self.voice.stop()
                self.log(f"✋ Interrupted by you ('{heard.strip()}')")
                return
