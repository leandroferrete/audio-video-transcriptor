## Visão geral rápida
- Projeto Windows para transcrição de áudio/vídeo com whisper.cpp (CLI binário) e opcionalmente WhisperX (Python) para palavras/diarização/karaoke preciso.  
- Entradas em `input/`; saídas em `output/` (SRT/VTT/TXT/JSON/ASS/MP4).  
- GUI em `transcribe_gui.py` (atalho `ABRIR_GUI.bat`). Pipeline principal em `transcribe_pro_karaoke_docker.py`.

## Componentes e fluxos
- **whisper.cpp (CUDA)**: binário `whisper-cublas-12.4.0-bin-x64/whisper-cli.exe` + modelo `ggml-large-v3.bin` em `whisper-cublas-12.4.0-bin-x64/models/`.
- **Pipeline principal** (`transcribe_pro_karaoke_docker.py`): usa whisper.cpp para texto base; gera SRT/VTT/TXT/JSON; karaoke approx (sem palavra a palavra) ou karaoke preciso via WhisperX. Detecta trilha de áudio (ffprobe) ou respeita `--audio-stream`.
- **WhisperX opcional**: roda em `venv_whisperx` (torch CUDA + whisperx + pyannote). Produz `*.whisperx.json` (palavras/diarize) e `*.whisperx.srt/.vtt`; também fornece timing preciso para karaoke.
- **GUI** (`transcribe_gui.py`): presets (texto rápido, karaoke rápido approx, karaoke qualidade WhisperX), polish desmarcado por padrão, seleção de trilha de áudio manual/automática, controle de qualidade/velocidade do vídeo.
- **BATs**:
  - `1clique_instalar_e_rodar.bat`: cria `.venv`, instala deps mínimas, roda pipeline padrão (whisper.cpp, karaoke approx).
  - `RODAR.bat`: roda pipeline principal com defaults.
  - `ABRIR_GUI.bat`: abre GUI.
  - `setup_whisperx.bat`: cria `venv_whisperx` com torch/cu121 + deps pinadas em `requirements_whisperx_local.txt`.

## Presets e modos
- **Texto rápido**: sem karaoke, whisper.cpp apenas.
- **Karaoke rápido (approx)**: timing de frases pelo whisper.cpp; não word-level.
- **Karaoke qualidade (WhisperX)**: usa WhisperX (word-level) e WAV extraído da trilha escolhida; requer `venv_whisperx` + token HF aceito.
- **Diarize**: só com WhisperX + `HUGGINGFACE_HUB_TOKEN` (termos pyannote aceitos).
- **Polish**: pós-processamento de pontuação; desligado por padrão (ativar só se quiser reformatar frases).

## Requisitos e tokens
- Python: `.venv` para pipeline principal; `venv_whisperx` para WhisperX (recom. Python 3.12 + CUDA 12.1).
- FFmpeg acessível no PATH (ou `ffmpeg.exe` local).
- GPU NVIDIA para WhisperX local.
- Token HF em `HUGGINGFACE_HUB_TOKEN` para diarize/pyannote; aceite `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0`.

## Downloads manuais (não versionados)
- Binários whisper.cpp CUDA: baixe `whisper-cublas-12.4.0-bin-x64` da release do whisper.cpp (ex.: https://github.com/ggerganov/whisper.cpp/releases) e extraia na raiz.
- Modelo: baixe `ggml-large-v3.bin` (ou outro) de https://huggingface.co/ggerganov/whisper.cpp/tree/main para `whisper-cublas-12.4.0-bin-x64/models/`.
- PowerShell exemplo:
  ```
  Invoke-WebRequest -Uri "https://github.com/ggerganov/whisper.cpp/releases/download/v1.7.0/whisper-cublas-12.4.0-bin-x64.zip" -OutFile whisper-cublas.zip
  Expand-Archive whisper-cublas.zip -DestinationPath .
  Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin" -OutFile "whisper-cublas-12.4.0-bin-x64/models/ggml-large-v3.bin"
  ```

## Execução básica (CLI)
```
cd /d "%~dp0"
python transcribe_pro_karaoke_docker.py ^
  --input input ^
  --output output ^
  --whisper-cli "whisper-cublas-12.4.0-bin-x64/whisper-cli.exe" ^
  --model "whisper-cublas-12.4.0-bin-x64/models/ggml-large-v3.bin" ^
  --language pt --threads 8 ^
  --vtt --force
```
- Karaoke approx: adicionar `--karaoke --karaoke-engine approx`.
- Karaoke WhisperX: adicionar `--karaoke --karaoke-engine whisperx --whisperx-cli "venv_whisperx/Scripts/whisperx.exe" --whisperx-model medium`.
- Diarize: adicionar `--diarize` (com token HF e termos aceitos).

## Sincronismo e qualidade
- Se legenda travar: fixe `--audio-stream` correto ou desative polish. Karaoke WhisperX usa WAV da trilha escolhida (menos dessincronização).
- Qualidade x velocidade do vídeo: ajuste CRF/preset no GUI; menor CRF = mais qualidade, mais tempo.

## Git / versão
- `.gitignore` exclui `input/`, `output/`, mídias/gerados, venvs e `whisper-cublas-12.4.0-bin-x64/`. Suba só scripts, BATs, requirements e docs.
