# DocExtract — Offline Document Intelligence

> **Professional document processing and profile extraction — fully offline, no cloud.**

A desktop application that extracts structured professional profiles from documents (resumes, certificates, marksheets, experience letters) using locally-running AI models. All processing happens on-device. No internet connection required after initial setup.

---

## Features

- **100% Offline** — works with internet completely disconnected after setup
- **Multiple Document Types** — PDF, DOCX, JPG, PNG — resumes, CVs, degree certificates, marksheets, experience letters, offer letters, certificates
- **AI-Powered Extraction** — local GGUF models (Phi-3-mini, Qwen2.5, Llama 3.2) via llama-cpp-python
- **OCR Support** — Tesseract 5.x for scanned/image documents
- **Conflict Detection** — automatically detects contradictions across documents
- **Experience Calculation** — deterministic, overlap-aware experience totalling
- **Multi-Document Reconciliation** — merges data from all uploaded documents
- **Export** — PDF, JSON, CSV — all offline
- **Privacy-First** — no telemetry, no analytics, no external APIs

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 64-bit | Windows 10/11 64-bit |
| RAM | 6 GB | 8 GB+ |
| Disk | 5 GB free | 10 GB free |
| CPU | Intel/AMD x64 with AVX2 | i5+ with AVX2 |
| GPU | Optional | NVIDIA (CUDA) for faster inference |

---

## Quick Start

### Prerequisites (one-time setup)

1. **Python 3.11+** (Anaconda recommended):
   Download from [anaconda.com](https://www.anaconda.com/download)

2. **Install Python packages:**
   ```powershell
   cd "D:\Projects\offline document extraction\app\backend"
   pip install -r requirements.txt
   ```

3. **Install Tesseract OCR** (for scanned documents):
   - **With admin rights:** `winget install UB-Mannheim.TesseractOCR`
   - **Without admin:** Open Anaconda Prompt → `conda install -c conda-forge tesseract`

4. **Install a GGUF model** (required for AI extraction):
   - Download `phi-3-mini-4k-instruct-q4.gguf` (~2.2 GB) from HuggingFace
   - Place in: `models/small/`
   - See [`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md) for details

5. **If `llama.dll` is blocked by Windows:**
   ```powershell
   Get-ChildItem "C:\Users\$env:USERNAME\anaconda3\Lib\site-packages\llama_cpp\lib" -Filter "*.dll" |
     ForEach-Object { Unblock-File -Path $_.FullName }
   ```

### Running the Desktop App

Double-click `DocExtract.exe` or `DocExtract.bat`.
- **Close behavior:** When you close the window, DocExtract **continues running in the background in your Windows System Tray**, keeping the server active so teammates and clients can still connect and upload documents.
- **System Tray Menu:** Right-click the tray icon to re-open the window, copy your Team LAN link, start/stop a public Cloudflare tunnel for clients, or exit completely.

---

### Running as a Persistent Background Server (Headless)

If you want the server to run continuously in the background without keeping a window open:

- **Start Background Server:** Run `Start_Background_Server.bat` (or silently with `Start_Background_Server.vbs`).
- **Share Links with Team & Clients:** Run `Share_Server.bat`.
  - **Team (LAN / Wi-Fi):** Shares `http://<your-local-ip>:37240` so anyone on the same Wi-Fi can open the web app.
  - **Clients (Internet):** Creates a free public Cloudflare Tunnel URL (`https://xxxx.trycloudflare.com`) so external clients anywhere can upload documents and certificates.
- **Stop Server:** Run `Stop_Server.bat` to terminate all background server and tunnel processes.

---

### Running in Development Mode

**Start backend:**
```powershell
python scripts/start_backend.py
```

**Open in browser** (while backend is running):
```
http://127.0.0.1:37240/docs   ← API documentation
```

**Or start the frontend:**
```powershell
cd app/frontend
npm install
npm run dev
# Open http://localhost:1420
```

---

## Project Structure

```
D:\Projects\offline document extraction\
├── app\
│   ├── backend\              ← Python FastAPI backend
│   │   ├── api\              ← REST API routers
│   │   ├── core\             ← Config, logging, startup checks
│   │   ├── database\         ← SQLite schema + async connection
│   │   ├── documents\        ← Ingestion + classification
│   │   ├── extraction\       ← PDF + DOCX text extraction
│   │   ├── extraction_pipeline\  ← LLM-based field extraction
│   │   ├── hardware\         ← Hardware detection
│   │   ├── llm\              ← llama-cpp-python provider + model manager
│   │   ├── ocr\              ← Tesseract OCR pipeline
│   │   ├── reconciliation\   ← Multi-document profile merging
│   │   ├── export\           ← PDF/JSON/CSV export
│   │   └── tests\            ← Unit + integration tests (35 tests)
│   ├── frontend\             ← React + TypeScript UI (Vite)
│   │   └── src\
│   │       ├── api\          ← Typed API client
│   │       ├── pages\        ← Dashboard, Documents, Process, Profiles, Settings
│   │       └── assets\       ← CSS design system
│   └── desktop\              ← Tauri v2 (desktop shell)
│       └── src-tauri\        ← Rust + Tauri configuration
├── models\
│   ├── small\                ← Place GGUF files here (Phi-3-mini, etc.)
│   ├── medium\
│   └── large\
├── data\
│   ├── uploads\              ← Uploaded document storage
│   └── exports\              ← Generated exports
├── docs\
│   ├── MODEL_SETUP.md        ← Model installation guide
│   └── TROUBLESHOOTING.md    ← Common issues
└── scripts\
    └── start_backend.py      ← Development startup helper
```

---

## API Reference

The backend exposes a REST API at `http://127.0.0.1:37240/api/v1/`.
Interactive docs available at `http://127.0.0.1:37240/docs` (development mode).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/system/status` | GET | Full system status + startup checks |
| `/api/v1/system/hardware` | GET | Detected hardware profile |
| `/api/v1/system/models` | GET | Available GGUF models |
| `/api/v1/documents/` | GET | List all documents |
| `/api/v1/documents/upload` | POST | Upload a document |
| `/api/v1/documents/{id}` | DELETE | Delete a document |
| `/api/v1/processing/start` | POST | Start extraction pipeline |
| `/api/v1/processing/status/{id}` | GET | Processing status |
| `/api/v1/profiles/` | GET | List profiles |
| `/api/v1/profiles/{id}` | GET | Full profile + evidence |
| `/api/v1/profiles/{id}/correct` | PATCH | Manually correct a field |
| `/api/v1/export/{id}/json` | GET | Export as JSON |
| `/api/v1/export/{id}/csv` | GET | Export as CSV |
| `/api/v1/export/{id}/pdf` | GET | Export as PDF report |

---

## Privacy Statement

- **No network requests** — zero external API calls after setup
- **No telemetry** — no usage data collected
- **No cloud processing** — all AI inference runs locally
- **Local storage only** — documents stored in `data/uploads/` on this device
- **SQLite database** — `data/docextract.db` — local file, not synced anywhere

---

## Running Tests

```powershell
cd "D:\Projects\offline document extraction\app\backend"
python -m pytest tests/ -v
# Expected: 35 passed
```
