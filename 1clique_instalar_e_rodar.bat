@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TRANSCRITOR PRO + KARAOKE (1 CLIQUE)
rem  - Mantém outputs antigos (SRT/TXT/JSON/logs) + novos (.ASS + .MP4)
rem  - Usa seu Python 3.10+ (venv local)
rem  - Karaoke "perfeito" usa WhisperX via Docker (sem mexer no seu Python)
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   TRANSCRITOR PRO + KARAOKE (1 CLIQUE)
echo   Pasta: "%cd%"
echo ============================================================
echo.

rem ====== AJUSTE OPCIONAL (se quiser forçar valores) ======
rem  (Se deixar vazio, o script tenta auto-detectar)
set "LANG=pt"
set "THREADS=8"
set "MODEL_HINT=ggml-medium"
set "WHISPERX_IMAGE=ghcr.io/jim60105/whisperx:no_model"
set "WHISPERX_MODEL=medium"

rem  Karaoke:
rem    AUTO = tenta WhisperX docker se Docker estiver ok; se não, usa approx
rem    WHISPERX = força whisperx (precisa Docker)
rem    APPROX = aproximação (não precisa Docker)
set "KARAOKE_MODE=AUTO"

rem  Ative diarização só se o token HF estiver em variável de ambiente
rem  (Recomendado: configurar no Windows: HUGGINGFACE_HUB_TOKEN)
set "DIARIZE=auto"

rem ============================================================
rem Pastas padrão (mesma pasta da aplicação)
set "INPUT_DIR=%cd%\input"
set "OUTPUT_DIR=%cd%\output"

if not exist "%INPUT_DIR%" mkdir "%INPUT_DIR%" >nul 2>&1
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1

rem ============================================================
rem 1) Descobrir Python 3.10+ (usa o primeiro encontrado no launcher)
set "PY_LAUNCHER="
for %%V in (3.12 3.11 3.10) do (
  if not defined PY_LAUNCHER (
    py -%%V -c "import sys; assert sys.version_info[:2]>=(3,10)" >nul 2>&1
    if not errorlevel 1 set "PY_LAUNCHER=py -%%V"
  )
)
if not defined PY_LAUNCHER (
  echo [ERRO] Nao achei Python 3.10+ via launcher "py".
  echo        Instale Python 3.10+ e ative o launcher (py.exe).
  pause
  exit /b 2
)

rem ============================================================
rem 2) Criar/usar venv
set "VENV_DIR=%cd%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [1/6] Criando venv em "%VENV_DIR%"...
  %PY_LAUNCHER% -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERRO] Falhou ao criar o venv.
    pause
    exit /b 2
  )
)

echo [2/6] Instalando/atualizando dependencias do projeto...
"%VENV_PY%" -m pip install -U pip >nul 2>&1

if exist "%cd%\requirements_transcribe_pro_karaoke.txt" (
  "%VENV_PY%" -m pip install -r "%cd%\requirements_transcribe_pro_karaoke.txt"
) else (
  rem fallback: instala tqdm diretamente
  "%VENV_PY%" -m pip install tqdm>=4.66.0
)

if errorlevel 1 (
  echo [ERRO] Falhou ao instalar dependencias.
  pause
  exit /b 2
)

rem ============================================================
rem 3) Detectar ffmpeg
set "FFMPEG=ffmpeg"
if exist "%cd%\ffmpeg.exe" set "FFMPEG=%cd%\ffmpeg.exe"
if exist "%cd%\ffmpeg\bin\ffmpeg.exe" set "FFMPEG=%cd%\ffmpeg\bin\ffmpeg.exe"
if exist "%cd%\tools\ffmpeg\bin\ffmpeg.exe" set "FFMPEG=%cd%\tools\ffmpeg\bin\ffmpeg.exe"

"%FFMPEG%" -version >nul 2>&1
if errorlevel 1 (
  echo [ERRO] FFmpeg nao encontrado.
  echo        Coloque ffmpeg no PATH ou em:
  echo          - "%cd%\ffmpeg.exe"
  echo          - "%cd%\ffmpeg\bin\ffmpeg.exe"
  echo          - "%cd%\tools\ffmpeg\bin\ffmpeg.exe"
  pause
  exit /b 2
)

rem ============================================================
rem 4) Detectar whisper-cli.exe e model (ggml/gguf)
set "WHISPER_CLI="
set "MODEL_PATH="

rem Tenta achar whisper-cli.exe (primeiro match)
for /r "%cd%" %%F in (whisper-cli.exe) do (
  if not defined WHISPER_CLI (
    set "WHISPER_CLI=%%F"
  )
)

if not defined WHISPER_CLI (
  echo [ERRO] Nao achei "whisper-cli.exe" dentro da pasta do projeto.
  echo        Coloque o whisper-cli.exe aqui dentro (em alguma subpasta).
  pause
  exit /b 2
)

rem Preferir model "ggml-medium.bin" se existir
for /r "%cd%" %%M in (ggml-medium.bin) do (
  if not defined MODEL_PATH set "MODEL_PATH=%%M"
)

rem Se nao achou, tenta qualquer ggml-*.bin
if not defined MODEL_PATH (
  for /r "%cd%" %%M in (ggml-*.bin) do (
    if not defined MODEL_PATH set "MODEL_PATH=%%M"
  )
)

rem Se ainda nao achou, tenta *.gguf
if not defined MODEL_PATH (
  for /r "%cd%" %%M in (*.gguf) do (
    if not defined MODEL_PATH set "MODEL_PATH=%%M"
  )
)

if not defined MODEL_PATH (
  echo [ERRO] Nao achei nenhum modelo (ggml-*.bin / ggml-medium.bin / *.gguf).
  echo        Coloque seu modelo em alguma subpasta (ex.: ./models/).
  pause
  exit /b 2
)

echo.
echo ========= Detectado =========
echo whisper-cli: "%WHISPER_CLI%"
echo model:       "%MODEL_PATH%"
echo ffmpeg:      "%FFMPEG%"
echo input:       "%INPUT_DIR%"
echo output:      "%OUTPUT_DIR%"
echo ============================
echo.

rem ============================================================
rem 5) Decidir karaoke engine
set "KARAOKE_ENGINE=approx"
set "WHISPERX_DOCKER_OK=0"

if /I "%KARAOKE_MODE%"=="APPROX" (
  set "KARAOKE_ENGINE=approx"
) else (
  rem Testa Docker
  docker --version >nul 2>&1
  if not errorlevel 1 (
    rem Testa acesso a GPU no docker (melhor esforço)
    docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi >nul 2>&1
    if not errorlevel 1 (
      set "WHISPERX_DOCKER_OK=1"
    ) else (
      rem Se nao tiver a imagem nvidia/cuda, ainda pode dar false-negative; tenta sem o teste
      set "WHISPERX_DOCKER_OK=1"
    )
  )

  if /I "%KARAOKE_MODE%"=="WHISPERX" (
    set "KARAOKE_ENGINE=whisperx"
  ) else (
    if "%WHISPERX_DOCKER_OK%"=="1" (
      set "KARAOKE_ENGINE=whisperx"
    ) else (
      set "KARAOKE_ENGINE=approx"
    )
  )
)

rem Diarize: auto => só liga se token existir
set "DIARIZE_FLAG="
if /I "%DIARIZE%"=="1" set "DIARIZE_FLAG=--diarize"
if /I "%DIARIZE%"=="0" set "DIARIZE_FLAG="
if /I "%DIARIZE%"=="auto" (
  if defined HUGGINGFACE_HUB_TOKEN (
    set "DIARIZE_FLAG=--diarize"
  ) else (
    set "DIARIZE_FLAG="
  )
)

rem ============================================================
rem 6) Rodar
rem Arquivo principal (python) - mantenha ele na mesma pasta do .bat
set "APP_PY=%cd%\transcribe_pro_karaoke_docker.py"
if not exist "%APP_PY%" (
  rem fallback: tenta o nome sem _docker
  set "APP_PY=%cd%\transcribe_pro_karaoke.py"
)

if not exist "%APP_PY%" (
  echo [ERRO] Nao achei o script Python:
  echo        - transcribe_pro_karaoke_docker.py (recomendado)
  echo        - transcribe_pro_karaoke.py
  echo        Coloque o .py na mesma pasta deste .bat.
  pause
  exit /b 2
)

echo [3/6] Rodando transcricao + outputs...
echo.
echo (Dica) Coloque seus videos/áudios em: "%INPUT_DIR%"
echo.

set "KARAOKE_FLAGS="
if /I "%KARAOKE_ENGINE%"=="whisperx" (
  set "KARAOKE_FLAGS=--karaoke --karaoke-engine whisperx --whisperx-docker-image "%WHISPERX_IMAGE%" --whisperx-model "%WHISPERX_MODEL%" %DIARIZE_FLAG%"
) else (
  set "KARAOKE_FLAGS=--karaoke --karaoke-engine approx"
)

"%VENV_PY%" "%APP_PY%" ^
  --input "%INPUT_DIR%" ^
  --output "%OUTPUT_DIR%" ^
  --recursive ^
  --ffmpeg "%FFMPEG%" ^
  --whisper-cli "%WHISPER_CLI%" ^
  --model "%MODEL_PATH%" ^
  --language "%LANG%" ^
  --threads %THREADS% ^
  --vtt ^
  --polish ^
  %KARAOKE_FLAGS%

echo.
echo [6/6] Finalizado. Veja os arquivos em: "%OUTPUT_DIR%"
echo.
pause
exit /b 0
