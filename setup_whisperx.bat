@echo off
setlocal
cd /d "%~dp0"

echo ===== WhisperX venv (Python 3.12 + CUDA 12.1) =====
echo.
echo - Requer: Python 3.12 no launcher (py -3.12) e GPU NVIDIA com CUDA 12.1
echo - Token HF deve estar em HUGGINGFACE_HUB_TOKEN (para diarize)
echo.

set "PY_LAUNCHER=py -3.12"
%PY_LAUNCHER% -V >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python 3.12 nao encontrado via "py -3.12".
  echo Instale o Python 3.12 e tente novamente.
  exit /b 2
)

set "VENV_DIR=%cd%\venv_whisperx"
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [1/4] Criando venv em %VENV_DIR% ...
  %PY_LAUNCHER% -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERRO] Falhou ao criar venv.
    exit /b 2
  )
)

set "PY=%VENV_DIR%\Scripts\python.exe"
echo [2/4] Atualizando pip...
"%PY%" -m pip install --upgrade pip

echo [3/4] Instalando torch/vision/audio CUDA 12.1...
"%PY%" -m pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
if errorlevel 1 (
  echo [ERRO] Falhou ao instalar torch/vision/audio.
  exit /b 2
)

echo [4/4] Instalando dependencias do WhisperX (pinadas)...
"%PY%" -m pip install -r requirements_whisperx_local.txt
if errorlevel 1 (
  echo [ERRO] Falhou ao instalar dependencias do WhisperX.
  exit /b 2
)

echo.
echo [OK] venv_whisperx pronto. Use:
echo   "%PY%" transcribe_pro_karaoke_docker.py ...
echo.
endlocal
