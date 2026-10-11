"""
System API — health, startup status, hardware info, model manager.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from hardware.detector import get_hardware_info
from llm.model_manager import get_model_manager_status
from core.config import settings

router = APIRouter()


@router.get("/status")
async def get_system_status(request: Request):
    """Return overall system readiness status."""
    startup = getattr(request.app.state, "startup_status", {})
    return {
        "status": "ready" if startup.get("overall_ready") else "setup_required",
        "offline_mode": True,
        "version": "1.0.0",
        "checks": startup,
    }


@router.get("/hardware")
async def get_hardware():
    """Return detected hardware information."""
    hw = get_hardware_info()
    return {
        "os": hw.os_name,
        "cpu": hw.cpu_brand,
        "cpu_cores": hw.cpu_cores,
        "cpu_threads": hw.cpu_threads,
        "cpu_flags": hw.cpu_flags,
        "ram_total_gb": hw.ram_total_gb,
        "ram_available_gb": hw.ram_available_gb,
        "gpu": {
            "name": hw.gpu.name if hw.gpu else None,
            "vendor": hw.gpu.vendor.value if hw.gpu else None,
            "vram_mb": hw.gpu.vram_mb if hw.gpu else None,
            "cuda_available": hw.gpu.cuda_available if hw.gpu else False,
        } if hw.gpu else None,
        "profile": hw.profile.value,
        "recommended_model_tier": hw.recommended_model_tier,
    }


@router.get("/models")
async def get_models():
    """Return available local models."""
    return get_model_manager_status(settings.MODELS_DIR)


@router.get("/privacy")
async def privacy_statement():
    """Return the privacy statement for display in the UI."""
    return {
        "statement": (
            "Documents are processed locally on this device. "
            "No document content, personal information, or metadata "
            "is transmitted to any external service. "
            "All AI processing uses locally installed models."
        ),
        "network_access": False,
        "telemetry": False,
        "cloud_processing": False,
    }
