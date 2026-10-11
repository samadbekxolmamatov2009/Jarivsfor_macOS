"""Ears: one always-open microphone stream + Silero VAD to detect when you start/stop talking."""
import queue
from collections import deque

import numpy as np
import sounddevice as sd
from openwakeword.vad import VAD

import re

import config


def pick_input():
    """Built-in Mac microphone by default. Using AirPods/Bluetooth mics switches them to low 'phone' audio quality.
    Override in config.py:  INPUT_DEVICE = "part of the device name"   (or "default")."""
    want = str(getattr(config, "INPUT_DEVICE", "auto"))
    if want.lower() == "default":
        return None
    devices = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    for i, d in devices:
        if want.lower() != "auto" and want.lower() in d["name"].lower():
            return i
    for i, d in devices:
        if re.search(r"macbook|built-in|internal", d["name"], re.I):
            return i
    return None

RATE = 16000
FRAME = 1280                      # 80 ms
FRAME_SEC = FRAME / RATE


class Mic:
    """Single microphone stream shared by the wake word and the listener — no gaps, no lost words."""

    def __init__(self):
        self.q = queue.Queue(maxsize=600)
        dev = pick_input()
        print(f"   🎤 Microphone: {sd.query_devices(dev)['name'] if dev is not None else 'system default'}", flush=True)
        self.stream = sd.InputStream(device=dev, samplerate=RATE, channels=1, dtype="int16",
                                     blocksize=FRAME, callback=self._callback)
        self.stream.start()

    def _callback(self, indata, frames, time_info, status):
        try:
            self.q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def read(self):
        return self.q.get()

    def stop(self):
        """Fully release the microphone (orange dot disappears)."""
        self.stream.stop()
        self.flush()

    def start(self):
        self.flush()
        self.stream.start()

    def flush(self):
        """Drop buffered audio (e.g. Jarvis's own voice)."""
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                return


class Listener:
    def __init__(self, mic):
        self.mic = mic
        self.vad = VAD()

    def listen(self, wait_seconds=6):
        """Returns float32 audio of one utterance, or None if you stayed silent.
        wait_seconds=None waits forever."""
        self.vad.reset_states()
        pre = deque(maxlen=4)
        frames, started, silence, waited, speech_frames = [], False, 0.0, 0.0, 0
        max_frames = int(config.MAX_LISTEN_SECONDS / FRAME_SEC)

        while True:
            f = self.mic.read()
            quiet = float(np.sqrt(np.mean(f.astype(np.float32) ** 2))) < getattr(config, "SILENCE_RMS", 120)
            is_speech = False if quiet else self.vad.predict(f, frame_size=640) >= config.VAD_THRESHOLD

            if not started:
                pre.append(f)
                if is_speech:
                    started, speech_frames, silence = True, 1, 0.0
                    frames = list(pre)
                else:
                    waited += FRAME_SEC
                    if wait_seconds is not None and waited >= wait_seconds:
                        return None
                continue

            frames.append(f)
            if is_speech:
                speech_frames += 1
                silence = 0.0
            else:
                silence += FRAME_SEC

            if silence >= config.END_SILENCE or len(frames) >= max_frames:
                if speech_frames < 3:          # just a click/noise — keep waiting
                    waited += len(frames) * FRAME_SEC
                    started, frames, speech_frames, silence = False, [], 0, 0.0
                    if wait_seconds is not None and waited >= wait_seconds:
                        return None
                    continue
                break

        return np.concatenate(frames).astype(np.float32) / 32768.0
