"""
DocExtract Sharing and Background Server Helper
Allows teammates on the local network (LAN) and external clients (Cloudflare Tunnel)
to access DocExtract and upload documents and certificates.
"""
import os
import sys
import re
import time
import socket
import subprocess
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "app" / "backend"
CLOUDFLARED_EXE = PROJECT_ROOT / "cloudflared.exe"
PORT = 37240

def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

def is_backend_running() -> bool:
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1.5)
        return req.status == 200
    except Exception:
        return False

def find_python() -> str:
    candidates = [
        Path(r"C:\Users\Zynee\anaconda3\python.exe"),
        Path(sys.base_prefix) / "python.exe",
        Path(sys.prefix) / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    import shutil
    py = shutil.which("python")
    if py:
        return py
    return sys.executable

def start_backend_if_needed():
    if is_backend_running():
        print("[+] DocExtract backend server is already RUNNING.")
        return None
    
    python_exe = find_python()
    print(f"[+] Starting DocExtract backend server on 0.0.0.0:{PORT}...")
    
    env = os.environ.copy()
    env["DOCEXTRACT_DEMO"] = "1"
    env["DOCEXTRACT_HOST"] = "0.0.0.0"

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=str(BACKEND_DIR),
        env=env,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    
    for _ in range(30):
        time.sleep(0.5)
        if is_backend_running():
            print("[+] DocExtract backend server started successfully!")
            return proc
            
    print("[!] Warning: Backend is still initializing...")
    return proc

def main():
    print("=" * 65)
    print("       DocExtract - Team & Client Sharing Center")
    print("=" * 65)
    
    start_backend_if_needed()
    
    lan_ip = get_lan_ip()
    local_url = f"http://127.0.0.1:{PORT}"
    lan_url = f"http://{lan_ip}:{PORT}"
    
    print("\n" + "-" * 65)
    print("1. Local Browser Access (This Computer): ")
    print(f"   -> {local_url}")
    print("-" * 65)
    print("2. Teammate Access (Same Wi-Fi / LAN Network): ")
    print(f"   -> {lan_url}")
    print("   (Anyone connected to your Wi-Fi/Office network can open this)")
    print("-" * 65)
    
    if not CLOUDFLARED_EXE.exists():
        print("[!] cloudflared.exe not found. Public internet sharing disabled.")
        input("\nPress Enter to exit...")
        return

    print("3. Client Access (Anywhere on the Internet via Cloudflare Tunnel): ")
    choice = input("   Do you want to generate a Public HTTPS URL for clients? (y/n): ").strip().lower()
    
    if choice in ("y", "yes"):
        print("\n[*] Creating secure public tunnel with Cloudflare...")
        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            tunnel_proc = subprocess.Popen(
                [str(CLOUDFLARED_EXE), "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            
            tunnel_url = None
            start_t = time.time()
            for line in tunnel_proc.stdout:
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    tunnel_url = m.group(0)
                    break
                if time.time() - start_t > 20:
                    break
            
            if tunnel_url:
                print("\n" + "*" * 65)
                print("   [+] PUBLIC CLIENT LINK READY!")
                print(f"   Share this link with your clients or teammates:")
                print(f"   -> {tunnel_url}")
                print("*" * 65)
                print("\nClients can open this link on mobile or desktop to upload")
                print("documents and certificates directly to your DocExtract server.")
                print("\nTunnel is active. Press Ctrl+C in this window to stop sharing.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nStopping public tunnel...")
                    tunnel_proc.terminate()
            else:
                print("[x] Could not retrieve tunnel URL. Check your internet connection.")
                if tunnel_proc:
                    tunnel_proc.terminate()
        except Exception as e:
            print(f"[x] Error starting tunnel: {e}")
    else:
        print("\nDocExtract server is running. You can close this window at any time.")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
