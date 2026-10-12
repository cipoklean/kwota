"""Hugging Face ZeroGPU support: borrow a GPU only while a model runs.

Off Spaces (or without the `spaces` package) the decorator does nothing and
everything runs on whatever torch finds: CUDA if present, else CPU.
"""
try:
    import spaces

    def gpu(fn=None, duration: int = 60):
        if fn is None:
            return lambda f: spaces.GPU(duration=duration)(f)
        return spaces.GPU(duration=duration)(fn)
except Exception:
    def gpu(fn=None, duration: int = 60):
        if fn is None:
            return lambda f: f
        return fn


def device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"
