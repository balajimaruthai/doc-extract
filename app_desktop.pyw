"""
DocExtract - Native Windows Desktop Application
Offline Document Intelligence platform powered by PySide6 QtWebEngine and FastAPI.
Features background server persistence, LAN team sharing, and instant Cloudflare tunnel for clients.
"""
import sys
import os
import re
import socket
import logging
import subprocess
import threading
import urllib.request
from pathlib import Path

# Resolve PROJECT_ROOT reliably whether running from source or PyInstaller
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "app" / "backend").exists():
        PROJECT_ROOT = exe_dir
    elif (exe_dir.parent / "app" / "backend").exists():
        PROJECT_ROOT = exe_dir.parent
    else:
        PROJECT_ROOT = Path(r"D:\Projects\offline document extraction")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent

LOG_FILE = PROJECT_ROOT / "desktop_app.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logging.info(f"Starting DocExtract desktop app. PROJECT_ROOT: {PROJECT_ROOT}, frozen: {getattr(sys, 'frozen', False)}")

BACKEND_DIR = PROJECT_ROOT / "app" / "backend"
ICON_PATH = PROJECT_ROOT / "app" / "desktop" / "src-tauri" / "icons" / "icon.ico"
CLOUDFLARED_EXE = PROJECT_ROOT / "cloudflared.exe"
PORT = 37240
URL = f"http://127.0.0.1:{PORT}"

backend_proc = None
tunnel_proc = None
tunnel_url = None


def get_lan_ip() -> str:
    """Get the local network IPv4 address for teammates to connect."""
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


def get_python_exe() -> str:
    """Find a valid python.exe to run backend (avoiding pythonw which drops stdout)."""
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


def is_backend_running() -> bool:
    try:
        req = urllib.request.urlopen(f"{URL}/health", timeout=1.2)
        return req.status == 200
    except Exception:
        return False


def start_backend():
    global backend_proc
    if is_backend_running():
        logging.info("Backend is already running.")
        return None

    python_exe = get_python_exe()
    logging.info(f"Spawning backend with {python_exe} in {BACKEND_DIR} on 0.0.0.0:{PORT}...")

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

    try:
        backend_proc = subprocess.Popen(
            [python_exe, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
            cwd=str(BACKEND_DIR),
            env=env,
            startupinfo=startupinfo,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info(f"Backend process spawned, PID: {backend_proc.pid}")
        return backend_proc
    except Exception as e:
        logging.exception(f"Failed to spawn backend process: {e}")
        return None


def stop_backend():
    global backend_proc
    if backend_proc:
        logging.info("Terminating backend process...")
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=2)
        except Exception:
            try:
                backend_proc.kill()
            except Exception:
                pass
        backend_proc = None


def stop_tunnel():
    global tunnel_proc, tunnel_url
    if tunnel_proc:
        logging.info("Terminating Cloudflare tunnel...")
        try:
            tunnel_proc.terminate()
            tunnel_proc.wait(timeout=2)
        except Exception:
            try:
                tunnel_proc.kill()
            except Exception:
                pass
        tunnel_proc = None
        tunnel_url = None


def main():
    global backend_proc, tunnel_proc, tunnel_url

    try:
        from PySide6.QtCore import QUrl, QTimer, Qt
        from PySide6.QtGui import QIcon, QAction, QGuiApplication
        from PySide6.QtWidgets import (
            QApplication,
            QMainWindow,
            QMessageBox,
            QSystemTrayIcon,
            QMenu,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except Exception as e:
        logging.exception(f"Failed to import PySide6: {e}")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Error initializing GUI library:\n{e}", "DocExtract Error", 0x10)
        except Exception:
            pass
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("DocExtract")
    app.setQuitOnLastWindowClosed(False)  # Crucial: Keeps background server active when window is closed

    lan_ip = get_lan_ip()
    lan_url = f"http://{lan_ip}:{PORT}"

    icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else app.style().standardIcon(app.style().StandardPixmap.SP_DriveNetIcon)
    app.setWindowIcon(icon)

    # Main Window Definition
    class DocExtractWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("DocExtract - Offline Document Intelligence")
            self.resize(1340, 860)

            # Center window
            screen_geo = app.primaryScreen().geometry()
            x = (screen_geo.width() - 1340) // 2
            y = (screen_geo.height() - 860) // 2
            self.move(max(0, x), max(0, y))
            self.setWindowIcon(icon)

            self.web_view = QWebEngineView()
            self.setCentralWidget(self.web_view)

            self.first_close_notified = False

        def closeEvent(self, event):
            # Instead of exiting, hide window and keep backend running for teammates & clients
            event.ignore()
            self.hide()
            if not self.first_close_notified and tray_icon.isSystemTrayAvailable():
                tray_icon.showMessage(
                    "DocExtract is Still Running in the Background",
                    f"Server remains online for team & clients at:\n{lan_url}\nRight-click this tray icon to open or quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                self.first_close_notified = True

    window = DocExtractWindow()

    # System Tray Menu & Actions
    tray_icon = QSystemTrayIcon(icon, app)
    tray_menu = QMenu()

    def show_window():
        window.show()
        window.raise_()
        window.activateWindow()

    action_show = QAction("Open DocExtract", tray_menu)
    action_show.triggered.connect(show_window)
    tray_menu.addAction(action_show)

    tray_menu.addSeparator()

    # LAN URL copy
    def copy_lan_url():
        QGuiApplication.clipboard().setText(lan_url)
        tray_icon.showMessage("Link Copied", f"Team LAN URL copied to clipboard:\n{lan_url}", QSystemTrayIcon.MessageIcon.Information, 3000)

    action_lan = QAction(f"Copy Team URL ({lan_url})", tray_menu)
    action_lan.triggered.connect(copy_lan_url)
    tray_menu.addAction(action_lan)

    # Localhost URL copy
    def copy_local_url():
        QGuiApplication.clipboard().setText(URL)
        tray_icon.showMessage("Link Copied", f"Local URL copied to clipboard:\n{URL}", QSystemTrayIcon.MessageIcon.Information, 3000)

    action_local = QAction(f"Copy Local URL ({URL})", tray_menu)
    action_local.triggered.connect(copy_local_url)
    tray_menu.addAction(action_local)

    tray_menu.addSeparator()

    # Cloudflare Public Tunnel
    action_tunnel = QAction("Start Public Sharing (for Clients)...", tray_menu)
    action_copy_tunnel = QAction("Copy Public Client URL", tray_menu)
    action_copy_tunnel.setEnabled(False)

    def copy_tunnel_link():
        global tunnel_url
        if tunnel_url:
            QGuiApplication.clipboard().setText(tunnel_url)
            tray_icon.showMessage("Public Link Copied", f"Public URL for clients copied:\n{tunnel_url}", QSystemTrayIcon.MessageIcon.Information, 3000)

    action_copy_tunnel.triggered.connect(copy_tunnel_link)

    def toggle_tunnel():
        global tunnel_proc, tunnel_url
        if tunnel_proc is None:
            if not CLOUDFLARED_EXE.exists():
                QMessageBox.warning(window, "Cloudflare Tunnel", "cloudflared.exe not found in project directory.")
                return

            action_tunnel.setText("Starting Public Tunnel...")
            action_tunnel.setEnabled(False)

            def run_tunnel_thread():
                global tunnel_proc, tunnel_url
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

                    found = False
                    for line in tunnel_proc.stdout:
                        m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                        if m:
                            tunnel_url = m.group(0)
                            found = True
                            logging.info(f"Cloudflare Tunnel started: {tunnel_url}")
                            # Update UI
                            QTimer.singleShot(0, lambda: on_tunnel_started(tunnel_url))
                            break
                    if not found and tunnel_proc:
                        QTimer.singleShot(0, lambda: on_tunnel_failed())
                except Exception as e:
                    logging.exception(f"Failed to run cloudflared: {e}")
                    QTimer.singleShot(0, lambda: on_tunnel_failed())

            def on_tunnel_started(url_str):
                action_tunnel.setText("Stop Public Sharing (Tunnel Active)")
                action_tunnel.setEnabled(True)
                action_copy_tunnel.setEnabled(True)
                action_copy_tunnel.setText(f"Copy Public Client URL ({url_str})")
                QGuiApplication.clipboard().setText(url_str)
                tray_icon.showMessage(
                    "Public Tunnel Active!",
                    f"Clients can now upload documents from anywhere:\n{url_str}\n(Link copied to clipboard!)",
                    QSystemTrayIcon.MessageIcon.Information,
                    6000,
                )

            def on_tunnel_failed():
                action_tunnel.setText("Start Public Sharing (for Clients)...")
                action_tunnel.setEnabled(True)
                action_copy_tunnel.setEnabled(False)
                tray_icon.showMessage("Tunnel Error", "Could not establish Cloudflare tunnel.", QSystemTrayIcon.MessageIcon.Warning, 4000)

            threading.Thread(target=run_tunnel_thread, daemon=True).start()
        else:
            stop_tunnel()
            action_tunnel.setText("Start Public Sharing (for Clients)...")
            action_copy_tunnel.setEnabled(False)
            action_copy_tunnel.setText("Copy Public Client URL")
            tray_icon.showMessage("Public Sharing Stopped", "Client public tunnel has been disconnected.", QSystemTrayIcon.MessageIcon.Information, 3000)

    action_tunnel.triggered.connect(toggle_tunnel)
    tray_menu.addAction(action_tunnel)
    tray_menu.addAction(action_copy_tunnel)

    tray_menu.addSeparator()

    # Complete Exit
    def exit_completely():
        stop_tunnel()
        stop_backend()
        tray_icon.hide()
        app.quit()

    action_exit = QAction("Exit & Stop Server Completely", tray_menu)
    action_exit.triggered.connect(exit_completely)
    tray_menu.addAction(action_exit)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.setToolTip(f"DocExtract Server\nTeam URL: {lan_url}")
    tray_icon.activated.connect(lambda reason: show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick or reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray_icon.show()

    # Splash Screen HTML
    splash_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            margin: 0;
            background-color: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }
        .spinner {
            width: 48px;
            height: 48px;
            border: 4px solid #334155;
            border-top: 4px solid #38bdf8;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 24px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        h1 { font-size: 24px; font-weight: 600; margin: 0 0 8px 0; }
        p { color: #94a3b8; font-size: 14px; margin: 0; }
    </style>
</head>
<body>
    <div class="spinner"></div>
    <h1>DocExtract</h1>
    <p>Initializing offline document intelligence engine...</p>
</body>
</html>"""

    start_backend()

    attempts = [0]
    timer = None

    def check_and_load():
        attempts[0] += 1
        if is_backend_running():
            logging.info("Backend is healthy, navigating web view to URL.")
            if timer:
                timer.stop()
            window.web_view.setUrl(QUrl(URL))
        elif attempts[0] > 40:
            if timer:
                timer.stop()
            logging.error("Backend failed to respond after 20 seconds.")
            QMessageBox.critical(
                window,
                "Backend Startup Timeout",
                "The DocExtract backend could not be reached.\nPlease verify your local environment or check desktop_app.log.",
            )

    if is_backend_running():
        window.web_view.setUrl(QUrl(URL))
    else:
        window.web_view.setHtml(splash_html)
        timer = QTimer()
        timer.setInterval(500)
        timer.timeout.connect(check_and_load)
        timer.start()

    window.show()
    logging.info(f"Main window displayed. LAN URL: {lan_url}")

    exit_code = app.exec()

    # Clean up on process exit
    stop_tunnel()
    stop_backend()

    logging.info("DocExtract application closed.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


