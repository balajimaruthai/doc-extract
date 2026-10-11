# DocExtract — Model Setup Guide

## Overview

DocExtract requires a locally installed **GGUF model** for AI-powered information extraction. The model runs entirely offline — no internet connection is needed after setup.

---

## Recommended Model

**Phi-3-mini-4k-instruct Q4_K_M** (best choice for this hardware configuration)

| Property | Value |
|----------|-------|
| File size | ~2.2 GB |
| RAM usage | ~3.0 GB |
| VRAM usage | ~2.5 GB (with GPU offload) |
| Context length | 4096 tokens |
| Quality | Excellent for structured extraction |
| Quantization | Q4_K_M (balanced quality/size) |

---

## Installation Steps (Offline-Compatible)

### Step 1 — Download the model (requires internet, one-time)

Download from Hugging Face (do this while you have internet access):

```
Model: microsoft/Phi-3-mini-4k-instruct-gguf
File: Phi-3-mini-4k-instruct-q4.gguf
Size: ~2.2 GB
URL: https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf
```

**Alternative models (if Phi-3 is unavailable):**

| Model | Size | RAM | Notes |
|-------|------|-----|-------|
| Qwen2.5-1.5B-Instruct Q4_K_M | ~1.0 GB | ~1.5 GB | Very fast, lower accuracy |
| Qwen2.5-3B-Instruct Q4_K_M | ~1.8 GB | ~2.5 GB | Good balance |
| Llama-3.2-3B-Instruct Q4_K_M | ~1.9 GB | ~2.5 GB | Good alternative |

### Step 2 — Place the model file

Place the downloaded `.gguf` file in:
```
D:\Projects\offline document extraction\models\small\
```

Example:
```
models\
  small\
    phi-3-mini-4k-instruct-q4.gguf   ← Place here
  medium\
  large\
```

### Step 3 — Restart the application

The model manager will automatically detect the file on next startup.

---

## GPU Acceleration

Your system has: **RTX 2050 (4 GB VRAM)**

GPU acceleration is configured automatically:
- **Small models (≤2.2 GB):** 20 layers offloaded to GPU — fast inference
- **If GPU memory runs low:** Automatically falls back to CPU

To force CPU-only (if GPU causes issues):
```
Set environment variable: DOCEXTRACT_LLM_N_GPU_LAYERS=0
```

---

## Verifying the Model Works

After installation, check the **Settings** page in the application. The model status should show:

```
✓ Ready — phi-3-mini-4k-instruct-q4 (2.2 GB, small tier)
```

If it shows an error, check:
1. The `.gguf` file is in `models/small/`
2. The file is not corrupted (check file size)
3. Sufficient RAM is available (close other applications)

---

## Tesseract OCR Setup

**Required for:** Scanned PDFs, image documents (JPG, PNG)

### Option A — Conda (No Admin Rights Needed)
```
conda install -c conda-forge tesseract
```

### Option B — Standard Installer (Requires Admin)
1. Download: https://github.com/UB-Mannheim/tesseract/releases
2. File: `tesseract-ocr-w64-setup-5.4.0.20240606.exe`
3. Run installer as Administrator
4. Install to: `C:\Program Files\Tesseract-OCR\`

### Verify installation:
```
tesseract --version
```
Expected output: `tesseract 5.4.0 ...`

---

## Troubleshooting

### "No GGUF model found"
- Check the file is in `models/small/` (not `models/` root)
- Check the file extension is `.gguf` (not `.bin`)
- Ensure file size matches expected (~2.2 GB for Phi-3-mini)

### "Failed to load shared library llama.dll"
Run in PowerShell:
```powershell
Get-ChildItem "C:\Users\$env:USERNAME\anaconda3\Lib\site-packages\llama_cpp\lib" -Filter "*.dll" |
  ForEach-Object { Unblock-File -Path $_.FullName }
```
Then restart the application.

### "Out of memory" error
- Close other applications to free RAM
- Use a smaller model (Qwen2.5-1.5B)
- Set `DOCEXTRACT_LLM_N_GPU_LAYERS=0` to use CPU only

### Low inference accuracy
- Try Qwen2.5-3B or Llama-3.2-3B instead of Phi-3-mini
- Ensure the document text quality is good (check OCR confidence)
