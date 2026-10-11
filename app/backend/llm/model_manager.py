"""
Model manager — detects available GGUF models, validates them,
reports status. Never downloads models.
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    name: str
    path: str
    size_gb: float
    tier: str                        # "small", "medium", "large"
    format: str                      # "gguf"
    is_available: bool
    estimated_ram_gb: float          # Conservative estimate
    estimated_vram_gb: float
    status: str                      # "ready", "missing", "too_large"
    notes: str = ""


# Known model configurations (name patterns → estimated requirements)
KNOWN_MODELS: dict[str, dict] = {
    "phi-3-mini": {"ram_gb": 3.0, "vram_gb": 2.5, "tier": "small"},
    "phi-3": {"ram_gb": 3.0, "vram_gb": 2.5, "tier": "small"},
    "qwen2.5-1.5b": {"ram_gb": 1.5, "vram_gb": 1.2, "tier": "small"},
    "qwen2.5-3b": {"ram_gb": 2.5, "vram_gb": 2.0, "tier": "small"},
    "llama-3.2-1b": {"ram_gb": 1.2, "vram_gb": 1.0, "tier": "small"},
    "llama-3.2-3b": {"ram_gb": 2.5, "vram_gb": 2.0, "tier": "small"},
    "mistral-7b": {"ram_gb": 5.0, "vram_gb": 4.5, "tier": "medium"},
    "llama-3.1-8b": {"ram_gb": 6.0, "vram_gb": 5.0, "tier": "medium"},
    "llama-3-8b": {"ram_gb": 6.0, "vram_gb": 5.0, "tier": "medium"},
}


def scan_models(models_dir: Path) -> list[ModelInfo]:
    """
    Scan the models directory for GGUF files.
    Returns a list of ModelInfo for all found and expected models.
    """
    found: list[ModelInfo] = []

    for tier in ["small", "medium", "large"]:
        tier_dir = models_dir / tier
        if not tier_dir.exists():
            continue

        for gguf_file in sorted(tier_dir.glob("*.gguf")):
            info = _build_model_info(gguf_file, tier)
            found.append(info)

    # Also check root models directory
    for gguf_file in sorted(models_dir.glob("*.gguf")):
        info = _build_model_info(gguf_file, "small")
        found.append(info)

    if not found:
        logger.warning(
            f"No GGUF models found in {models_dir}. "
            "See docs/MODEL_SETUP.md for installation instructions."
        )
    else:
        logger.info(f"Found {len(found)} model(s): {[m.name for m in found]}")

    return found


def _build_model_info(gguf_path: Path, tier: str) -> ModelInfo:
    """Build ModelInfo for a single GGUF file."""
    name = gguf_path.stem
    size_bytes = gguf_path.stat().st_size if gguf_path.exists() else 0
    size_gb = round(size_bytes / (1024**3), 2)

    # Estimate RAM/VRAM from known models or file size
    ram_gb, vram_gb = _estimate_requirements(name.lower(), size_gb)

    # Check if system has enough total RAM (not available — llama-cpp pages on demand
    # and uses VRAM, so we check total with a 1 GB OS headroom)
    try:
        import psutil
        total_ram_gb = psutil.virtual_memory().total / (1024**3)
        # Allow if total RAM ≥ required RAM (with 1 GB headroom for OS)
        if ram_gb > (total_ram_gb - 1.0):
            status = "too_large"
            notes = (
                f"Requires ~{ram_gb:.1f} GB RAM but system only has "
                f"{total_ram_gb:.1f} GB total. Try a smaller model."
            )
        else:
            status = "ready"
            notes = ""
    except Exception:
        status = "ready"
        notes = ""

    return ModelInfo(
        name=name,
        path=str(gguf_path),
        size_gb=size_gb,
        tier=tier,
        format="gguf",
        is_available=True,
        estimated_ram_gb=ram_gb,
        estimated_vram_gb=vram_gb,
        status=status,
        notes=notes,
    )


def _estimate_requirements(name_lower: str, size_gb: float) -> tuple[float, float]:
    """Estimate RAM and VRAM requirements."""
    for pattern, specs in KNOWN_MODELS.items():
        if pattern in name_lower:
            return specs["ram_gb"], specs["vram_gb"]

    # Fallback: estimate from file size (Q4 quantized models use ~1.3x file size in RAM)
    estimated_ram = round(size_gb * 1.3, 1)
    estimated_vram = round(size_gb * 1.1, 1)
    return estimated_ram, estimated_vram


def get_best_model(models_dir: Path) -> Optional[ModelInfo]:
    """
    Return the best available model for this hardware.
    Prefers small models for 8 GB RAM systems.
    """
    models = scan_models(models_dir)
    ready_models = [m for m in models if m.status == "ready"]

    if not ready_models:
        return None

    # Prefer small tier, then medium, then large
    for tier in ["small", "medium", "large"]:
        tier_models = [m for m in ready_models if m.tier == tier]
        if tier_models:
            # Return largest model in tier (best quality that fits)
            return max(tier_models, key=lambda m: m.size_gb)

    return ready_models[0]


def get_model_manager_status(models_dir: Path) -> dict:
    """Return a status dict for the UI model manager panel."""
    models = scan_models(models_dir)
    best = get_best_model(models_dir)

    model_list = [
        {
            "name": m.name,
            "path": m.path,
            "size_gb": m.size_gb,
            "tier": m.tier,
            "format": m.format,
            "is_available": m.is_available,
            "estimated_ram_gb": m.estimated_ram_gb,
            "estimated_vram_gb": m.estimated_vram_gb,
            "status": m.status,
            "notes": m.notes,
        }
        for m in models
    ]

    if not model_list:
        model_list = [
            {
                "name": "Built-in Rule & Pattern Engine",
                "path": "built-in",
                "size_gb": 0.01,
                "tier": "small",
                "format": "native",
                "is_available": True,
                "estimated_ram_gb": 0.05,
                "estimated_vram_gb": 0.0,
                "status": "ready",
                "notes": "Lightweight built-in extraction engine — optimal for cloud containers and low-memory environments.",
            }
        ]

    return {
        "models": model_list,
        "best_model": best.name if best else "Built-in Rule & Pattern Engine",
        "best_model_path": best.path if best else "built-in",
        "has_any_model": True,
        "setup_required": False,
        "setup_instructions": "",
    }
