"""Gemma, the open-weight model that drafts the quote and reads the photos.

Backends (pick with KWOTA_LLM=local|ollama|hf|aistudio, or leave unset):
  * local    - Gemma 3 via transformers in-process. Default on a Hugging Face
               ZeroGPU Space; works on any CUDA machine. Reads photos too.
  * ollama   - fully local on the artisan's own laptop: `ollama pull gemma3:4b`.
               Reads photos too.
  * hf       - Hugging Face Inference router, HF_TOKEN (text only).
  * aistudio - Google AI Studio hosted Gemma, GEMINI_API_KEY (text only).
"""
from __future__ import annotations

import base64
import io
import os
from functools import lru_cache

import requests

from .gpu import gpu

LOCAL_MODEL = os.getenv("KWOTA_LOCAL_MODEL", "unsloth/gemma-3-12b-it")  # ungated mirror of google/gemma-3-12b-it

PHOTO_PROMPT = (
    "These are photos an artisan took while inspecting a job at a customer's home in Nigeria. "
    "In one or two plain sentences, describe the work visible (for example: water stain on "
    "ceiling, cracked floor tiles in bathroom, rusted tap). Do not guess sizes, counts or prices."
)


def backend() -> str:
    b = os.getenv("KWOTA_LLM", "").lower()
    if b:
        return b
    if os.getenv("SPACE_ID"):
        return "local"
    if os.getenv("GEMINI_API_KEY"):
        return "aistudio"
    if os.getenv("HF_TOKEN"):
        return "hf"
    return "ollama"


@lru_cache(maxsize=1)
def _local():
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(LOCAL_MODEL)
    model = AutoModelForImageTextToText.from_pretrained(
        LOCAL_MODEL, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    return processor, model.eval()


@gpu(duration=45)
def _generate_local(system: str, prompt: str, images=None, max_new_tokens: int = 600) -> str:
    import torch

    processor, model = _local()
    model.to("cuda" if torch.cuda.is_available() else "cpu")
    content = [{"type": "image", "image": im} for im in (images or [])[:4]]
    content.append({"type": "text", "text": prompt})
    messages = [
        {"role": "system", "content": [{"type": "text", "text": system}]},
        {"role": "user", "content": content},
    ]
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt").to(model.device)
    n = inputs["input_ids"].shape[-1]
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return processor.decode(out[0][n:], skip_special_tokens=True).strip()


def _b64(im) -> str:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def generate(system: str, prompt: str, images=None) -> str:
    b = backend()
    if b == "local":
        return _generate_local(system, prompt, images)
    if b == "ollama":
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        msg = {"role": "user", "content": prompt}
        if images:
            msg["images"] = [_b64(im) for im in images[:4]]
        r = requests.post(f"{host}/api/chat", json={
            "model": os.getenv("KWOTA_MODEL", "gemma3:4b"), "stream": False,
            "options": {"temperature": 0}, "format": "json" if not images else "",
            "messages": [{"role": "system", "content": system}, msg],
        }, timeout=300)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    if b == "hf":
        r = requests.post("https://router.huggingface.co/v1/chat/completions",
                          headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
                          json={"model": os.getenv("KWOTA_MODEL", "google/gemma-3-27b-it"),
                                "temperature": 0, "max_tokens": 700,
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": prompt}]},
                          timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    if b == "aistudio":
        model = os.getenv("KWOTA_MODEL", "gemma-3-27b-it")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"role": "user", "parts": [{"text": system + "\n\n" + prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": 700}},
            timeout=120)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    raise ValueError(f"Unknown KWOTA_LLM backend {b!r}")


def available() -> bool:
    """Cheap check so the app can say which engine drafted the quote."""
    b = backend()
    if b == "local":
        return True
    if b == "ollama":
        try:
            requests.get(os.getenv("OLLAMA_HOST", "http://localhost:11434"), timeout=2)
            return True
        except requests.RequestException:
            return False
    return bool(os.getenv("HF_TOKEN") if b == "hf" else os.getenv("GEMINI_API_KEY"))


def describe_photos(images) -> str:
    """One or two sentences of scope from the photos; '' when no vision backend."""
    if not images or backend() not in ("local", "ollama"):
        return ""
    try:
        return generate("You describe building and repair work plainly.", PHOTO_PROMPT, images)
    except Exception as e:
        print(f"Photo description failed: {e}", flush=True)
        return ""
