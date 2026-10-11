"""Voice: Kokoro (offline, natural), macOS 'say' (instant) or edge-tts (online).
The next sentence is synthesized while the current one is playing."""
import asyncio
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from collections import deque

import numpy as np

import requests
import sounddevice as sd

import config
from skills.lang import uz_latin

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def _download(url, path):
    print(f"⬇️  Downloading {os.path.basename(path)} (first run only)...", flush=True)
    tmp = path + ".part"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    os.replace(tmp, path)


def _clean(text):
    text = text.replace("°C", " degrees").replace("°", " degrees")
    text = re.sub(r"[*#_`>~]", "", text)
    return re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]", "", text).strip()


class Voice:
    def __init__(self):
        self.engine = config.TTS_ENGINE
        self.kokoro = None
        self.lock = threading.RLock()
        self.first_sound_at = None
        self.last_text = ""
        self.stop_event = threading.Event()   # set by stop() -> silence at once
        self.speaking = False
        self.interrupted = False
        self.recent = []                      # sentences being spoken (to ignore our own echo)
        self.upcoming = deque()
        self.played = 0
        self.on_start = None                  # called when speaking starts (starts the "stop" listener)
        self.on_sentence = None      # HUD shows what Jarvis says
        if self.engine == "kokoro":
            try:
                self._load_kokoro()
            except Exception as e:
                print(f"⚠️  Kokoro failed ({e}) — using macOS voice", flush=True)
                self.engine = "say"

    def _load_kokoro(self):
        from kokoro_onnx import Kokoro
        os.makedirs(MODEL_DIR, exist_ok=True)
        for name, url in KOKORO_FILES.items():
            path = os.path.join(MODEL_DIR, name)
            if not os.path.exists(path):
                _download(url, path)
        self.kokoro = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
                             os.path.join(MODEL_DIR, "voices-v1.0.bin"))
        self.lang = "en-gb" if config.KOKORO_VOICE.startswith("b") else "en-us"
        self.kokoro.create("Ready.", voice=config.KOKORO_VOICE, lang=self.lang)   # warm-up

    # ---- synthesis (runs in main thread) ----
    def _synth(self, text, lang="en"):
        """-> (kind, value, samplerate, original_text). Uzbek/Russian use Microsoft neural voices (internet)."""
        if lang in ("uz", "ru"):
            try:
                import edge_tts
                voice = getattr(config, "UZ_VOICE", "uz-UZ-SardorNeural") if lang == "uz" else \
                    getattr(config, "RU_VOICE", "ru-RU-DmitryNeural")
                path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
                asyncio.run(edge_tts.Communicate(uz_latin(text) if lang == "uz" else text, voice).save(path))
                if os.path.exists(path) and os.path.getsize(path) > 500:
                    return ("file", path, None, text)
            except Exception as e:
                if not getattr(self, "_edge_warned", False):
                    print(f"⚠️  {lang} voice needs internet ({e}); using the English voice", flush=True)
                    self._edge_warned = True
            if lang == "ru":
                return ("say_ru", text, None, text)
            text_for_en = uz_latin(text)
        else:
            text_for_en = text
        if self.engine == "kokoro":
            samples, sr = self.kokoro.create(text_for_en, voice=config.KOKORO_VOICE,
                                             speed=config.SPEECH_SPEED, lang=self.lang)
            return ("file", self._wav(samples, sr), None, text)
        return ("say", text_for_en, None, text)

    # ---- playback (runs in player thread) ----
    def _play(self, item):
        kind, value, sr, text = item
        if self.stop_event.is_set():
            if kind == "file":
                try:
                    os.remove(value)
                except OSError:
                    pass
            return
        if self.first_sound_at is None:
            self.first_sound_at = time.time()
        self.played += 1
        self.recent.append(text)                 # what the mic can hear right now (for "stop")
        if kind == "file":
            p = subprocess.Popen(["afplay", value])
        elif kind == "say_ru":
            p = subprocess.Popen(["say", "-v", getattr(config, "RU_SAY_VOICE", "Milena"), value])
        else:
            rate = str(int(185 * config.SPEECH_SPEED))
            p = subprocess.Popen(["say", "-v", config.SAY_VOICE, "-r", rate, value])
        while p.poll() is None:
            if self.stop_event.is_set():
                p.terminate()
                break
            time.sleep(0.03)
        if kind == "file":
            try:
                os.remove(value)
            except OSError:
                pass

    def _wav(self, samples, sr):
        """Float audio -> clean 16-bit WAV: no clipping, soft 8 ms fade in/out (no clicks)."""
        x = np.asarray(samples, dtype=np.float32).flatten()
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 0.89:
            x = x * (0.89 / peak)
        fade = min(len(x) // 2, int(sr * 0.008))
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            x[:fade] *= ramp
            x[-fade:] *= ramp[::-1]
        path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sr))
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        return path

    def stop(self):
        """Interrupt: stop talking now and drop the rest of the answer."""
        self.stop_event.set()

    def recent_text(self):
        """Sentences being played now, just before and just after — our own echo, never a real 'stop'."""
        return " ".join(self.recent[-2:] + list(self.upcoming)[:1])

    def speak_stream(self, sentences, lang="en"):
        """sentences: strings or (text, lang) pairs. Only 2 sentences are prepared ahead (smooth, low CPU)."""
        with self.lock:
            self.first_sound_at = None
            self.stop_event.clear()
            self.interrupted = False
            self.recent, self.played = [], 0
            self.upcoming = deque()
            self.speaking = True
            if self.on_start:
                self.on_start()
            q = queue.Queue(maxsize=2)

            def player():
                while True:
                    item = q.get()
                    if item is None:
                        return
                    if self.upcoming:
                        self.upcoming.popleft()
                    self._play(item)

            t = threading.Thread(target=player, daemon=True)
            t.start()
            said = []
            for s in sentences:
                if self.stop_event.is_set():
                    break
                text, lg = s if isinstance(s, tuple) else (s, lang)
                if not text or not text.strip():
                    continue
                said.append(text)
                print(f"🤖 Jarvis: {text}", flush=True)
                if self.on_sentence:
                    self.on_sentence(text)
                clean = _clean(text)
                if not clean:
                    continue
                try:
                    item = self._synth(clean, lg)
                except Exception as e:
                    print("⚠️  Voice error:", e, flush=True)
                    item = ("say", clean, None, text)
                self.upcoming.append(text)
                while not self.stop_event.is_set():
                    try:
                        q.put(item, timeout=0.2)
                        break
                    except queue.Full:
                        continue
            if self.stop_event.is_set() and hasattr(sentences, "close"):
                sentences.close()                       # stop the AI from writing the rest
            while True:                                 # let the player finish (or drain after a stop)
                try:
                    q.put(None, timeout=0.2)
                    break
                except queue.Full:
                    continue
            t.join()
            self.speaking = False
            self.interrupted = self.stop_event.is_set()
            if said:
                self.last_text = " ".join(said)

    def speak(self, text):
        self.speak_stream([text])
