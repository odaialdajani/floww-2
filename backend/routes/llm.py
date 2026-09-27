"""
backend/routes/llm.py

LLM analysis routes — OpenRouter, Gemini, and turboQuantDC KV cache compression.
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Models the turboquant endpoint may load without operator opt-in.
# Anything else requires FLOWW_LLM_MODEL_ALLOWLIST=org/name,org2/name2.
_TURBOQUANT_DEFAULT_MODEL = "Qwen/Qwen2.5-3B-Instruct"
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")


def _allowed_turboquant_models() -> set[str]:
    raw = os.environ.get("FLOWW_LLM_MODEL_ALLOWLIST", "")
    names = {m.strip() for m in raw.split(",") if m.strip()}
    names.add(_TURBOQUANT_DEFAULT_MODEL)
    return names


def _validate_turboquant_model(model_name: str) -> None:
    """Fail-closed model gate: well-formed HF id AND allowlisted.

    Runs before any heavy import so rejection is testable offline.
    trust_remote_code stays False at the load site, so even an
    allowlisted model cannot execute remote custom code.
    """
    if not model_name or not _MODEL_ID_RE.fullmatch(model_name):
        raise HTTPException(status_code=422, detail={
            "error": "bad_model_name",
            "message": "model_name must be a HuggingFace id like org/name.",
        })
    if model_name not in _allowed_turboquant_models():
        raise HTTPException(status_code=403, detail={
            "error": "model_not_allowlisted",
            "message": ("Model is not allowlisted. Add it to "
                        "FLOWW_LLM_MODEL_ALLOWLIST to enable it."),
        })


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TradeAnalysisRequest(BaseModel):
    ticker: str
    spot: float
    regime: str = "NEUTRAL"
    net_gex: float = 0.0
    prediction: str = "HOLD"
    confidence: float = 0.5


class GenerateRequest(BaseModel):
    prompt: str
    system_prompt: str = "You are a market analyst."
    max_tokens: int = 512
    provider: str | None = None  # override per-request


# Module-level model cache (models are expensive to load)
_MODEL_CACHE: dict[str, tuple] = {}


class TurboQuantGenerateRequest(BaseModel):
    prompt: str
    model_name: str = "Qwen/Qwen2.5-3B-Instruct"
    system_prompt: str = ""
    max_new_tokens: int = 128
    preset: str = "balanced"
    bits: int = 4


# ---------------------------------------------------------------------------
# LLM Routes
# ---------------------------------------------------------------------------

@router.post("/llm/analyze-trade")
async def llm_analyze_trade(request: TradeAnalysisRequest):
    """Analyze a trade opportunity using the configured LLM provider."""
    try:
        from services.llm import analyze_trade_with_llm
        result = await analyze_trade_with_llm(
            ticker=request.ticker,
            spot=request.spot,
            regime=request.regime,
            net_gex=request.net_gex,
            prediction=request.prediction,
            confidence=request.confidence,
        )
        return result
    except ImportError:
        raise HTTPException(503, "LLM service not configured") from None
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.post("/llm/generate")
async def llm_generate(request: GenerateRequest):
    """Generate text using the configured LLM provider (OpenRouter by default)."""
    try:
        from services.llm import get_llm_service
        llm = get_llm_service()
        result = llm.generate(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            max_tokens=request.max_tokens,
        )
        return result
    except ImportError:
        raise HTTPException(503, "LLM service not configured") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.get("/llm/providers")
async def llm_providers():
    """List available LLM providers and their configuration status."""
    try:
        from services.llm import get_llm_service
        llm = get_llm_service()
        return {
            "providers": llm.available_providers,
            "current": llm.provider,
            "configured": llm.is_configured,
        }
    except Exception as e:
        raise HTTPException(500, str(e)) from e


# ---------------------------------------------------------------------------
# turboQuantDC KV Cache Routes
# ---------------------------------------------------------------------------

@router.get("/turboquant/status")
async def turboquant_status():
    """Get turboQuantDC KV cache compression service status."""
    from services.turboquant_cache import get_turboquant_service
    service = get_turboquant_service()
    return service.status()


@router.get("/turboquant/presets")
async def turboquant_presets():
    """List available turboQuantDC quality presets."""
    from services.turboquant_cache import get_turboquant_service
    service = get_turboquant_service()
    return {
        "available": service.available,
        "presets": service.presets,
        "default": service.default_preset,
    }


@router.post("/turboquant/generate")
async def turboquant_generate(request: TurboQuantGenerateRequest):
    """Generate text using a local HuggingFace model with turboQuantDC compressed KV cache.

    This loads a model locally and uses turboQuantDC's GenerationCache to compress
    the KV cache by 3-5x, reducing VRAM usage while maintaining <0.5% quality loss.

    Requires: turboquantdc, transformers, accelerate, and optionally bitsandbytes.
    """
    # Model gate first: no allowlist hit, no downloads, no imports.
    _validate_turboquant_model(request.model_name)
    try:
        from services.turboquant_cache import get_turboquant_service
        service = get_turboquant_service()

        if not service.available:
            raise HTTPException(
                503,
                "turboQuantDC not installed. Install: pip install turboquantdc[all]"
            )

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise HTTPException(503, "transformers/torch not installed") from None

        # Load model + tokenizer (cached to avoid re-loading on every request)
        cache_key = request.model_name
        if cache_key not in _MODEL_CACHE:
            tokenizer = AutoTokenizer.from_pretrained(
                request.model_name, trust_remote_code=False,
                revision="main",  # noqa: B615
            )
            model = AutoModelForCausalLM.from_pretrained(
                request.model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=False,
                revision="main",  # noqa: B615 — allowlisted model name only
            )
            _MODEL_CACHE[cache_key] = (model, tokenizer)
        model, tokenizer = _MODEL_CACHE[cache_key]

        # Create compressed KV cache
        cache = service.create_cache(preset=request.preset, bits=request.bits)

        # Tokenize and generate
        inputs = tokenizer(request.prompt, return_tensors="pt").to(model.device)
        compression_used = True

        try:
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    past_key_values=cache,
                    max_new_tokens=request.max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                )
        except (TypeError, AttributeError, IndexError) as e:
            # turboQuantDC cache not compatible with this model/transformers version
            # Fall back to standard generation
            logger.warning(f"turboQuantDC cache incompatible, using standard generation: {e}")
            compression_used = False
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=request.max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                )

        generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        stats = service.get_compression_stats(cache) if compression_used else {"available": True, "compatible": False}

        return {
            "generated_text": generated,
            "model": request.model_name,
            "preset": request.preset,
            "compression_used": compression_used,
            "compression_stats": stats,
            "input_tokens": inputs["input_ids"].shape[1],
            "output_tokens": outputs.shape[1] - inputs["input_ids"].shape[1],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}") from e
