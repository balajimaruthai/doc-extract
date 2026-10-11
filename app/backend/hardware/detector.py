"""
Hardware detection and capability assessment.
Used to select appropriate model profile and inference parameters.
No network calls. Reads local system information only.
"""
import logging
import os
import platform
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


class HardwareProfile(str, Enum):
    LOW_RESOURCE = "low_resource"       # < 8 GB RAM, CPU only
    STANDARD = "standard"               # 8–16 GB RAM, optional GPU
    HIGH_PERFORMANCE = "high_performance"  # 32 GB+ RAM, dedicated GPU


class GPUVendor(str, Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"
    NONE = "none"


@dataclass
class GPUInfo:
    vendor: GPUVendor
    name: str
    vram_mb: int
    cuda_available: bool
    cuda_version: Optional[str]
    vulkan_available: bool
    recommended_n_gpu_layers: int


@dataclass
class HardwareInfo:
    os_name: str
    os_version: str
    cpu_brand: str
    cpu_cores: int
    cpu_threads: int
    cpu_flags: list[str]
    has_avx: bool
    has_avx2: bool
    has_avx512: bool
    ram_total_gb: float
    ram_available_gb: float
    gpu: Optional[GPUInfo]
    profile: HardwareProfile
    recommended_n_threads: int
    recommended_model_tier: str  # "small", "medium", "large"


def detect_hardware() -> HardwareInfo:
    """
    Detect all hardware capabilities. Entirely local — no network calls.
    """
    logger.info("Running hardware detection...")

    # OS
    os_name = platform.system()
    os_version = platform.version()

    # CPU
    try:
        import cpuinfo
        cpu_data = cpuinfo.get_cpu_info()
        cpu_brand = cpu_data.get("brand_raw", platform.processor())
        cpu_flags = cpu_data.get("flags", [])
    except Exception:
        cpu_brand = platform.processor()
        cpu_flags = []

    cpu_cores = psutil.cpu_count(logical=False) or 1
    cpu_threads = psutil.cpu_count(logical=True) or 1
    has_avx = "avx" in cpu_flags
    has_avx2 = "avx2" in cpu_flags
    has_avx512 = "avx512f" in cpu_flags

    # RAM
    vm = psutil.virtual_memory()
    ram_total_gb = round(vm.total / (1024**3), 1)
    ram_available_gb = round(vm.available / (1024**3), 1)

    # GPU
    gpu_info = _detect_gpu()

    # Profile assignment
    profile = _assign_profile(ram_total_gb, gpu_info)

    # Threading: use N-2 logical threads (leave some for OS + UI)
    recommended_n_threads = max(1, min(cpu_threads - 2, 10))

    # Model tier
    recommended_model_tier = _recommend_model_tier(ram_total_gb, gpu_info)

    info = HardwareInfo(
        os_name=os_name,
        os_version=os_version,
        cpu_brand=cpu_brand,
        cpu_cores=cpu_cores,
        cpu_threads=cpu_threads,
        cpu_flags=[f for f in cpu_flags if f in ("avx", "avx2", "avx512f", "fma", "sse4_2")],
        has_avx=has_avx,
        has_avx2=has_avx2,
        has_avx512=has_avx512,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        gpu=gpu_info,
        profile=profile,
        recommended_n_threads=recommended_n_threads,
        recommended_model_tier=recommended_model_tier,
    )

    logger.info(
        f"Hardware: {cpu_brand} | RAM: {ram_total_gb}GB | "
        f"GPU: {gpu_info.name if gpu_info else 'None'} | "
        f"Profile: {profile.value}"
    )
    return info


def _detect_gpu() -> Optional[GPUInfo]:
    """Detect GPU via nvidia-smi or system APIs. No network calls."""
    # Try NVIDIA first (via pynvml or subprocess)
    nvidia = _detect_nvidia()
    if nvidia:
        return nvidia

    # Fallback: detect Intel iGPU (no acceleration for LLM)
    return _detect_intel_igpu()


def _detect_nvidia() -> Optional[GPUInfo]:
    """Detect NVIDIA GPU capabilities."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0].strip():
            return None

        parts = [p.strip() for p in lines[0].split(",")]
        gpu_name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
        vram_mb = int(parts[1]) if len(parts) > 1 else 0

        # Check CUDA availability
        cuda_available = False
        cuda_version = None
        try:
            cuda_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=cuda_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            if cuda_result.returncode == 0:
                cv = cuda_result.stdout.strip()
                if cv and cv != "N/A":
                    cuda_available = True
                    cuda_version = cv
        except Exception:
            pass

        # Also check via llama-cpp-python
        try:
            from llama_cpp import llama_backend_init
            cuda_available = True
        except Exception:
            pass

        # Recommend GPU layers based on VRAM
        n_gpu_layers = _recommend_gpu_layers(vram_mb)

        return GPUInfo(
            vendor=GPUVendor.NVIDIA,
            name=gpu_name,
            vram_mb=vram_mb,
            cuda_available=cuda_available,
            cuda_version=cuda_version,
            vulkan_available=False,
            recommended_n_gpu_layers=n_gpu_layers,
        )

    except FileNotFoundError:
        logger.debug("nvidia-smi not found — no NVIDIA GPU detected")
        return None
    except Exception as e:
        logger.debug(f"NVIDIA detection failed: {e}")
        return None


def _detect_intel_igpu() -> Optional[GPUInfo]:
    """Detect Intel iGPU — limited acceleration capability."""
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-WmiObject Win32_VideoController | Where-Object {$_.Name -like '*Intel*'} | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "Intel" in result.stdout:
            return GPUInfo(
                vendor=GPUVendor.INTEL,
                name=result.stdout.strip().split("\n")[0],
                vram_mb=128,  # Shared memory — not reliable for LLM
                cuda_available=False,
                cuda_version=None,
                vulkan_available=False,
                recommended_n_gpu_layers=0,  # CPU only for Intel iGPU
            )
    except Exception:
        pass
    return None


def _recommend_gpu_layers(vram_mb: int) -> int:
    """
    Recommend number of GPU layers based on available VRAM.
    Conservative estimates for stability.
    """
    if vram_mb >= 8000:   # 8 GB+
        return 35         # Full model in GPU
    elif vram_mb >= 6000:  # 6 GB
        return 28
    elif vram_mb >= 4000:  # 4 GB (RTX 2050)
        return 20         # Partial offload for small models
    elif vram_mb >= 2000:  # 2 GB
        return 10
    else:
        return 0          # CPU only


def _assign_profile(ram_total_gb: float, gpu: Optional[GPUInfo]) -> HardwareProfile:
    """Assign hardware profile based on RAM and GPU."""
    if ram_total_gb >= 32:
        return HardwareProfile.HIGH_PERFORMANCE
    elif ram_total_gb >= 16:
        return HardwareProfile.STANDARD
    elif ram_total_gb >= 8:
        # 8 GB — standard only if GPU helps significantly
        if gpu and gpu.vendor == GPUVendor.NVIDIA and gpu.vram_mb >= 4000:
            return HardwareProfile.STANDARD
        return HardwareProfile.LOW_RESOURCE
    else:
        return HardwareProfile.LOW_RESOURCE


def _recommend_model_tier(ram_total_gb: float, gpu: Optional[GPUInfo]) -> str:
    """Recommend model size tier."""
    if ram_total_gb >= 32:
        return "large"
    elif ram_total_gb >= 16:
        return "medium"
    else:
        return "small"


# Singleton — detected once at startup
_hardware_info: Optional[HardwareInfo] = None


def get_hardware_info() -> HardwareInfo:
    """Return cached hardware info (detected once at startup)."""
    global _hardware_info
    if _hardware_info is None:
        _hardware_info = detect_hardware()
    return _hardware_info
