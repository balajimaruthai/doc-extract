// DocExtract — Tauri v2 main library
// Launches the Python FastAPI backend as a sidecar process.

use std::sync::Mutex;
use tauri::{AppHandle, Manager, State};

/// Holds the Python backend child process handle
struct BackendProcess(Mutex<Option<std::process::Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            // Launch Python backend in a background thread
            std::thread::spawn(move || {
                launch_backend(&handle);
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // When the main window is destroyed, kill the backend
            if let tauri::WindowEvent::Destroyed = event {
                let state: State<BackendProcess> = window.state();
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        eprintln!("[DocExtract] Backend process terminated.");
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_backend_status])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn launch_backend(handle: &AppHandle) {
    // Resolve path to the Python executable and main.py
    // In production, these would be bundled as sidecar resources.
    // In development, we look for the local Python installation.
    let backend_dir = find_backend_dir(handle);

    let python = find_python();

    eprintln!("[DocExtract] Starting backend: {} main.py (in {:?})", python, backend_dir);

    let child_result = std::process::Command::new(&python)
        .arg("-m")
        .arg("uvicorn")
        .arg("main:app")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg("37240")
        .arg("--log-level")
        .arg("warning")
        .current_dir(&backend_dir)
        .env("PYTHONPATH", &backend_dir)
        .spawn();

    match child_result {
        Ok(child) => {
            eprintln!("[DocExtract] Backend started (PID: {})", child.id());
            let state: State<BackendProcess> = handle.state();
            let mut guard = state.0.lock().unwrap();
            *guard = Some(child);
        }
        Err(e) => {
            eprintln!("[DocExtract] ERROR: Failed to start backend: {}", e);
            eprintln!("[DocExtract] Python path attempted: {}", python);
        }
    }
}

fn find_python() -> String {
    // Try these Python executables in order
    let candidates = [
        "C:\\Users\\Zynee\\anaconda3\\python.exe",
        "C:\\Users\\Zynee\\miniconda3\\python.exe",
        "python",
        "python3",
    ];

    for candidate in &candidates {
        if let Ok(output) = std::process::Command::new(candidate)
            .arg("--version")
            .output()
        {
            if output.status.success() {
                eprintln!("[DocExtract] Found Python: {}", candidate);
                return candidate.to_string();
            }
        }
    }

    // Fallback — let the OS resolve it
    "python".to_string()
}

fn find_backend_dir(handle: &AppHandle) -> std::path::PathBuf {
    // In development: relative to the executable's parent directory
    // In production: bundled in resources
    let exe_dir = handle
        .path()
        .resource_dir()
        .unwrap_or_else(|_| std::path::PathBuf::from("."));

    // Try development path: up from src-tauri → app → backend
    let dev_backend = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .join("backend");

    if dev_backend.exists() {
        return dev_backend;
    }

    // Bundled path
    exe_dir.join("backend")
}

#[tauri::command]
async fn get_backend_status() -> Result<String, String> {
    // Simple ping to the backend health endpoint
    // Used by the frontend to know when the backend is ready
    match reqwest::get("http://127.0.0.1:37240/health").await {
        Ok(resp) if resp.status().is_success() => Ok("ready".to_string()),
        Ok(resp) => Err(format!("Backend HTTP {}", resp.status())),
        Err(e) => Err(format!("Backend not reachable: {}", e)),
    }
}
