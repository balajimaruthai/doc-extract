# DocExtract — Troubleshooting Guide

## Common Issues

---

### ❌ "No GGUF model found"

**Symptom:** Settings page shows "No model installed". AI extraction doesn't work.

**Fix:** Place a `.gguf` file in the `models/small/` directory.
- See [`docs/MODEL_SETUP.md`](MODEL_SETUP.md) for the recommended model.
- The app will never download a model automatically.

---

### ❌ "Tesseract OCR not found"

**Symptom:** Settings page shows Tesseract issue. OCR for scanned documents doesn't work.

> **Note:** PDF text extraction still works for digital PDFs even without Tesseract. Only scanned/image documents need OCR.

**Fix — Option A (Requires Administrator):**

1. Open PowerShell **as Administrator**
2. Run: `winget install UB-Mannheim.TesseractOCR --accept-source-agreements`
3. Restart the application

**Fix — Option B (No Admin Rights):**

1. Open Anaconda Prompt (not PowerShell)
2. Run: `conda install -c conda-forge tesseract`
3. Restart the application

**Fix — Option C (Manual):**

1. Download installer: https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe
2. Ask your IT admin to install it to `C:\Program Files\Tesseract-OCR\`
3. Restart the application

---

### ❌ "Failed to load shared library llama.dll" — WinError 4551

**Symptom:** AI extraction fails. Error in Python console about Application Control policy.

**Cause:** Windows blocked the DLL download during llama-cpp-python install.

**Fix:**
```powershell
# Run in regular PowerShell (no admin needed)
Get-ChildItem "C:\Users\$env:USERNAME\anaconda3\Lib\site-packages\llama_cpp\lib" -Filter "*.dll" |
  ForEach-Object { Unblock-File -Path $_.FullName; Write-Host "Unblocked: $($_.Name)" }
```
Then restart the application.

---

### ❌ Backend doesn't start / "Connecting to local services" hangs forever

**Check 1 — Is Python available?**
```powershell
python --version
```
If not found: Open Anaconda Prompt and run `conda activate base`

**Check 2 — Test backend manually:**
```powershell
cd "D:\Projects\offline document extraction\app\backend"
python -m uvicorn main:app --host 127.0.0.1 --port 37240
```
Look for error messages in the console output.

**Check 3 — Port conflict (another app using 37240):**
```powershell
netstat -aon | findstr 37240
```
If something is using port 37240, close it or change the backend port in `app/backend/core/config.py`.

---

### ❌ Document upload fails with "File type not supported"

Only these formats are accepted:
- **PDF** (`.pdf`)
- **Word Documents** (`.docx`, `.doc`)
- **Images** (`.jpg`, `.jpeg`, `.png`)

Make sure the file extension matches the actual file content.

---

### ❌ Document processing fails / stuck at "Processing"

**Check the backend console** for error details.

**Common causes:**
- No LLM model installed (see Model Setup)
- Out of memory — close other applications and retry
- Corrupt document — try a different file

**Manual retry:** Delete the failed document and re-upload it.

---

### ❌ Profile shows wrong information

Use the **edit button** (pencil icon) next to any field in the Profile Detail view to manually correct extracted values. All corrections are tracked with an audit trail.

For data conflicts between documents, use the **Conflicts** section in the Profile Detail view to choose which source is correct.

---

### ❌ Export fails

- **JSON export:** No dependencies — should always work if a profile exists
- **PDF export:** Requires the profile to have at least some data
- **CSV export:** No dependencies — should always work

Check the backend console for specific errors.

---

## Getting Help

1. Check the backend console output first (most errors are described there)
2. Review `logs/docextract.log` in the project directory
3. See [`docs/MODEL_SETUP.md`](MODEL_SETUP.md) for AI model issues
