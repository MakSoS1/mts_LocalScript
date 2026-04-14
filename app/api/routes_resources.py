from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, Request

from app.schemas import ResourceResponse, VramInfo

router = APIRouter(tags=["resources"])


def _get_nvidia_vram() -> list[VramInfo]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return []
        infos: list[VramInfo] = []
        for line in proc.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            try:
                infos.append(VramInfo(
                    model=parts[0],
                    vram_used_mb=float(parts[1]),
                    vram_total_mb=float(parts[2]),
                    load_percent=float(parts[3]),
                ))
            except (ValueError, IndexError):
                continue
        return infos
    except (subprocess.SubprocessError, OSError):
        return []


def _get_ollama_vram(client) -> list[VramInfo]:
    infos: list[VramInfo] = []
    try:
        running = client.running_models()
        for model_name in running:
            try:
                resp = client._get("/api/show")
                model_info = resp.get("details", {})
                param_size = model_info.get("parameter_size", "")
                fam = model_info.get("family", "")
                vram_mb = None
                if "B" in param_size.upper():
                    try:
                        size_b = float(param_size.upper().replace("B", "").strip())
                        vram_mb = size_b * 1024
                    except ValueError:
                        pass
                infos.append(VramInfo(
                    model=model_name,
                    vram_used_mb=vram_mb,
                    available=True,
                ))
            except Exception:
                infos.append(VramInfo(model=model_name, available=True))
    except Exception:
        pass
    return infos


def _get_system_ram() -> tuple[float | None, float | None]:
    try:
        import platform
        system = platform.system()
        if system == "Windows":
            proc = subprocess.run(
                ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            free = total = None
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("FreePhysicalMemory="):
                    free = float(line.split("=", 1)[1]) / (1024 * 1024)
                elif line.startswith("TotalVisibleMemorySize="):
                    total = float(line.split("=", 1)[1]) / (1024 * 1024)
            if total:
                used = total - (free or 0)
                return used, total
        elif system == "Darwin":
            proc = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5, check=False)
            page_size = 4096
            free_pages = total_pages = 0
            for line in proc.stdout.splitlines():
                if "Pages free" in line or "Pages inactive" in line:
                    count = int(line.split(":")[-1].strip().rstrip("."))
                    free_pages += count
            proc2 = subprocess.run(["sysctl", "hw.memsize"], capture_output=True, text=True, timeout=5, check=False)
            total = float(proc2.stdout.split(":")[-1].strip()) / (1024**3) if proc2.returncode == 0 else None
            free = (free_pages * page_size) / (1024**3) if free_pages else None
            if total and free is not None:
                return total - free, total
        else:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            total = free = None
            for line in lines:
                if line.startswith("MemTotal:"):
                    total = float(line.split()[1]) / (1024 * 1024)
                elif line.startswith("MemAvailable:"):
                    free = float(line.split()[1]) / (1024 * 1024)
            if total and free is not None:
                return total - free, total
    except Exception:
        pass
    return None, None


@router.get("/resources", response_model=ResourceResponse)
def get_resources(request: Request) -> ResourceResponse:
    client = request.app.state.client
    ollama_ok = False
    running: list[str] = []
    try:
        ollama_ok, running = client.health()
    except Exception:
        pass

    nvidia = _get_nvidia_vram()
    ollama_vram = _get_ollama_vram(client) if ollama_ok else []
    all_vram = nvidia if nvidia else ollama_vram

    ram_used, ram_total = _get_system_ram()

    return ResourceResponse(
        ollama_ok=ollama_ok,
        running_models=running,
        vram=all_vram,
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
    )
