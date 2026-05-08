@echo off
chcp 65001 >nul
echo ========================================
echo  memsearch Windows Setup
echo  Token-optimized (ONNX local embedding)
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ first.
    pause
    exit /b 1
)

REM Check/install uv
where uv >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing uv package manager...
    python -m pip install uv --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install uv. Try: pip install uv
        pause
        exit /b 1
    )
)

REM Install memsearch with ONNX (local, free, no API key)
echo [1/3] Installing memsearch with ONNX embedding...
uv tool install "memsearch[onnx]" --quiet
if errorlevel 1 (
    echo [FALLBACK] Trying pip install...
    pip install "memsearch[onnx]"
    if errorlevel 1 (
        echo [ERROR] Installation failed. Check Python version (3.10+ required).
        pause
        exit /b 1
    )
)

REM Configure embedding to ONNX (local, no token cost)
echo [2/3] Configuring local embedding (ONNX bge-m3)...
memsearch config set embedding.provider onnx

REM Configure Milvus Lite (local .db, zero config)
echo [3/3] Configuring Milvus Lite (local storage)...
memsearch config get milvus.uri >nul 2>&1
if errorlevel 1 (
    memsearch config set milvus.uri "%USERPROFILE%\.memsearch\milvus.db"
)

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo  Next steps:
echo  1. Install OpenCode plugin (if using OpenCode):
echo     Add to %%APPDATA%%\..\Local\opencode\opencode.json:
echo     "plugin": ["@zilliz/memsearch-opencode"]
echo.
echo  2. Or install Claude Code plugin:
echo     /plugin marketplace add zilliztech/memsearch
echo     /plugin install memsearch
echo.
echo  3. Run sync task to enable auto-sync:
echo     register-task.bat
echo.
pause
