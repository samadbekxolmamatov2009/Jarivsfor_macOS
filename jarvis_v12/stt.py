"""Speech-to-text: English-only Whisper on Apple Silicon (MLX)."""
import re
import numpy as np
import mlx_whisper
import config

PROMPT = ("Hey Jarvis. What time is it? Open Brave. Set a timer for five minutes. "
          "What's 17 times 23? Remind me to call mom. Find my math test file.")
HALLUCINATIONS = {"", "you", "thanks for watching", "thank you for watching",
                  "subtitles by the amara org community"}


WAKE_CHECK_MODEL = getattr(config, "WAKE_CHECK_MODEL", "mlx-community/whisper-tiny.en-mlx")


def _run(audio, prompt=PROMPT, model=None):
    return mlx_whisper.transcribe(
        audio, path_or_hf_repo=model or config.WHISPER_MODEL, language="en", temperature=0.0,
        condition_on_previous_text=False, initial_prompt=prompt, verbose=None)


def _clean(text):
    text = (text or "").strip()
    return "" if re.sub(r"[^a-z ]", "", text.lower()).strip() in HALLUCINATIONS else text


def warmup():
    _run(np.zeros(16000, dtype=np.float32))


_fast_failed = False


def transcribe_fast(audio):
    """Tiny English model (74 MB) just for hearing 'stop' while Jarvis talks."""
    global _fast_failed
    if not _fast_failed:
        try:
            r = mlx_whisper.transcribe(audio, path_or_hf_repo=getattr(config, "BARGE_IN_MODEL",
                                       "mlx-community/whisper-tiny.en-mlx"), language="en", temperature=0.0,
                                       condition_on_previous_text=False, verbose=None)
            return _clean(r.get("text", ""))
        except Exception as e:
            print("⚠️  tiny model unavailable, using the main one:", e, flush=True)
            _fast_failed = True
    return transcribe(audio, prompt=None)


def transcribe(audio, prompt=PROMPT):
    return _clean(_run(audio, prompt).get("text", ""))


def transcribe_scored(audio, model=None):
    """No prompt (no bias) + how sure Whisper is. model=None -> main model."""
    r = _run(audio, None, model)
    segs = r.get("segments") or []
    logprob = sum(s.get("avg_logprob", -9) for s in segs) / len(segs) if segs else -9
    no_speech = max((s.get("no_speech_prob", 1) for s in segs), default=1)
    ok = no_speech < getattr(config, "WAKE_MAX_NO_SPEECH", 0.6) and \
        logprob > getattr(config, "WAKE_MIN_LOGPROB", -1.0)
    return _clean(r.get("text", "")), {"ok": ok, "logprob": logprob, "no_speech": no_speech}
