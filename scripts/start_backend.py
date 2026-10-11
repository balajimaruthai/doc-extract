"""
DocExtract — application startup script.
Starts the FastAPI backend server.
Run this before launching the desktop app in development mode.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "app" / "backend"
PORT = 37240


def find_python() -> str:
    """Find the Python executable (prefers Anaconda)."""
    candidates = [
        r"C:\Users\{}\anaconda3\python.exe".format(os.environ.get("USERNAME", "")),
        r"C:\Users\{}\miniconda3\python.exe".format(os.environ.get("USERNAME", "")),
        sys.executable,
        "python",
    ]
    for c in candidates:
        try:
            result = subprocess.run([c, "--version"], capture_output=True, timeout=3)
            if result.returncode == 0:
                return c
        except Exception:
            continue
    return "python"


def get_lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    python = find_python()
    lan_ip = get_lan_ip()
    print("=" * 60)
    print(f"[DocExtract] Starting server on 0.0.0.0:{PORT}")
    print(f"[DocExtract] Local Link:   http://127.0.0.1:{PORT}")
    print(f"[DocExtract] Offline/LAN:  http://{lan_ip}:{PORT}")
    print("=" * 60)
    print(f"[DocExtract] Python: {python}")
    print(f"[DocExtract] Press Ctrl+C to stop.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["DOCEXTRACT_DEMO"] = "1"
    env["DOCEXTRACT_HOST"] = "0.0.0.0"

    subprocess.run(
        [
            python, "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--log-level", "info",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )


if __name__ == "__main__":
    main()
