"""Listen to the artisan: NaijaVox-2.0 speech recognition.

NaijaVox-2.0 (Apache-2.0) is Whisper large-v3 fine-tuned on Nigerian Pidgin,
Yoruba, Hausa, Igbo and Nigerian-accented English. A walk-through voice note
can run past Whisper's 30-second window, so long notes are cut into 28-second
pieces with a 2-second overlap and the pieces are joined.
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

from .gpu import device as _device
from .gpu import gpu

ASR_MODEL = os.getenv("KWOTA_ASR_MODEL", "Axiveri/NaijaVox-2.0")
LANG_TOKEN = {"en": "<|en|>", "pcm": "<|pcm|>", "ha": "<|ha|>", "yo": "<|yo|>", "ig": "<|ig|>"}
MAX_SECONDS = 180  # a walk-through, not a podcast

SR = 16000
PIECE = 28 * SR
STEP = 26 * SR


@lru_cache(maxsize=1)
def _asr():
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    torch.set_num_threads(max(1, os.cpu_count() or 1))
    processor = WhisperProcessor.from_pretrained(ASR_MODEL)
    on_gpu = torch.cuda.is_available() or bool(os.getenv("SPACE_ID"))
    model = WhisperForConditionalGeneration.from_pretrained(
        ASR_MODEL, torch_dtype=torch.float16 if on_gpu else torch.float32, low_cpu_mem_usage=True)
    model.to(_device()).eval()
    return processor, model


def to_16k_mono(sr: int, audio: np.ndarray) -> np.ndarray:
    audio = audio.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1.0:  # int16 from the browser mic
        audio = audio / 32768.0
    if sr != SR:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    return audio[: SR * MAX_SECONDS]


def load_file(path: str) -> tuple[int, np.ndarray]:
    """Read any voice note, including WhatsApp .opus/.ogg (needs ffmpeg)."""
    import librosa
    audio, sr = librosa.load(path, sr=SR, mono=True)
    return sr, audio


def pieces(audio: np.ndarray) -> list[np.ndarray]:
    if len(audio) <= PIECE:
        return [audio]
    return [audio[s:s + PIECE] for s in range(0, max(1, len(audio) - (PIECE - STEP)), STEP)]


def _join(texts: list[str]) -> str:
    """Join overlapping pieces, dropping words repeated across the seam."""
    out: list[str] = []
    for t in texts:
        words = t.split()
        for k in range(min(6, len(out), len(words)), 0, -1):
            if [w.lower().strip(".,") for w in out[-k:]] == [w.lower().strip(".,") for w in words[:k]]:
                words = words[k:]
                break
        out.extend(words)
    return " ".join(out)


@gpu(duration=60)
def transcribe(sr: int, audio: np.ndarray, lang: str = "pcm") -> str:
    import torch

    processor, model = _asr()
    vocab = processor.tokenizer.get_vocab()
    audio = to_16k_mono(sr, audio)
    prompt = [vocab["<|startoftranscript|>"], vocab[LANG_TOKEN.get(lang, "<|en|>")],
              vocab["<|transcribe|>"], vocab["<|notimestamps|>"]]
    texts = []
    for chunk in pieces(audio):
        feats = processor.feature_extractor(chunk, sampling_rate=SR, return_tensors="pt").input_features
        feats = feats.to(model.device, dtype=model.dtype)
        with torch.no_grad():
            out = model.generate(feats, decoder_input_ids=torch.tensor([prompt], device=model.device),
                                 max_new_tokens=220)
        texts.append(processor.tokenizer.decode(out[0], skip_special_tokens=True).strip())
    return _join(texts)
