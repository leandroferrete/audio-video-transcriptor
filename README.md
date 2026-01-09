# Transcritor PRO + Karaoke

### Visão geral
- `transcribe_pro_karaoke_docker.py`: pipeline principal (whisper.cpp) + opção de karaoke + sidecar WhisperX.
- GUI: `transcribe_gui.py` (atalho: `ABRIR_GUI.bat`).
- `1clique_instalar_e_rodar.bat`: cria `.venv`, instala deps do projeto (tqdm) e roda pipeline (whisper.cpp) com karaoke approx por padrão.
- Opcional: `setup_whisperx.bat` cria `venv_whisperx` (Python 3.12 + CUDA 12.1) e instala WhisperX (com diarize). 

### Pastas/arquivos importantes
- `input/`: coloque os arquivos de mídia.
- `output/`: saídas (SRT/VTT/TXT/JSON/ASS/MP4); ignoradas no git.
- `whisper-cublas-12.4.0-bin-x64/`: binários do whisper.cpp + modelos (models/ é ignorado no git). Baixe o modelo `ggml-large-v3.bin` na pasta `models/`.
- `.venv/`: venv principal (tqdm). `setup_whisperx.bat` cria `venv_whisperx/` para WhisperX.
- `requirements_transcribe_pro_karaoke.txt`: deps mínimas do pipeline principal.
- `requirements_whisperx_local.txt`: snapshot pinado das deps do `venv_whisperx` (WhisperX local + diarize).

### Pré-requisitos
- Windows, ffmpeg disponível (ou em `ffmpeg.exe`/`ffmpeg\bin\ffmpeg.exe`). 
- Python 3.12 (para `setup_whisperx.bat`). O pipeline principal roda com 3.10+.
- GPU NVIDIA com CUDA 12.1 para WhisperX local (opcional).
- Token HF em variável de ambiente `HUGGINGFACE_HUB_TOKEN` para diarize (modelos pyannote são gated; aceite os termos em `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0`).

### Setup rápido (pipeline principal, whisper.cpp)
1) Rode `1clique_instalar_e_rodar.bat` (cria `.venv`, instala tqdm). 
2) Coloque mídia em `input/`. 
3) Rode `RODAR.bat` ou o comando (exemplo):
```
python transcribe_pro_karaoke_docker.py ^
  --input input ^
  --output output ^
  --whisper-cli "whisper-cublas-12.4.0-bin-x64\whisper-cli.exe" ^
  --model "whisper-cublas-12.4.0-bin-x64\models\ggml-large-v3.bin" ^
  --language pt --threads 8 ^
  --audio-stream 0 --no-auto-audio-stream ^
  --vtt --force
```
(Tire `--karaoke` para só textos. Polish fica off na GUI por padrão; mantenha off se quiser resultado cru.)

### Setup WhisperX local (diarize/words + karaoke mais preciso)
1) Rode `setup_whisperx.bat` (cria `venv_whisperx`, instala torch 2.5.1 cu121 e deps pinadas do `requirements_whisperx_local.txt`).
2) Certifique `HUGGINGFACE_HUB_TOKEN` setado e termos aceitos em `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0`.
3) Comando exemplo (texto + sidecar WhisperX + diarize; sem vídeo):
```
venv_whisperx\Scripts\python.exe transcribe_pro_karaoke_docker.py ^
  --input "input\teste.mkv" ^
  --output "output" ^
  --whisper-cli "whisper-cublas-12.4.0-bin-x64\whisper-cli.exe" ^
  --model "whisper-cublas-12.4.0-bin-x64\models\ggml-large-v3.bin" ^
  --language pt --threads 8 ^
  --audio-stream 0 --no-auto-audio-stream ^
  --vtt --force ^
  --karaoke-engine whisperx ^
  --whisperx-cli "venv_whisperx\Scripts\whisperx.exe" ^
  --whisperx-model medium ^
  --diarize
```
Saídas: 
- `*.srt` (whisper.cpp) + `*.whisperx.srt/.vtt` (WhisperX), `*.whisperx.json` (words/diarize). 
- Karaoke usa WhisperX quando engine=whisperx; approx quando não.

### GUI (ABRIR_GUI.bat)
- Presets: texto rápido, karaoke rápido (approx), karaoke qualidade (WhisperX). 
- Polish vem desmarcado por padrão. 
- Campo “Trilha de áudio (0/1/2…)” para escolher a trilha correta.
- “Auto escolher trilha” usa ffprobe; desmarque se quiser fixar.
- Qualidade do vídeo: crf/preset (menor crf = mais qualidade). 
- Diarize só com WhisperX + token HF.

### Dicas de sincronismo
- Se legendas travarem, defina `--audio-stream` correto (0/1/2...) e desative polish.
- Karaoke WhisperX agora usa o mesmo WAV da trilha selecionada, reduzindo dessincronização.

### Scripts úteis
- `1clique_instalar_e_rodar.bat`: cria `.venv`, instala deps mínimas e roda whisper.cpp com karaoke approx.
- `ABRIR_GUI.bat`: abre GUI.
- `setup_whisperx.bat`: cria `venv_whisperx` e instala WhisperX local com deps pinadas.

### Itens ignorados no git
- `output/`, venvs (`.venv`, `venv*/`, `venv_whisperx/`), binários/modelos em `whisper-cublas-12.4.0-bin-x64/`, logs e temporários. Suba apenas scripts, .bat e requirements.

### Downloads não versionados (traga manualmente)
- whisper.cpp CUDA (binários): baixe o pacote `whisper-cublas-12.4.0-bin-x64` da release do whisper.cpp (ex.: https://github.com/ggerganov/whisper.cpp/releases). Descompacte na raiz do projeto.
- Modelo base: baixe `ggml-large-v3.bin` (ou outro) de https://huggingface.co/ggerganov/whisper.cpp/tree/main e coloque em `whisper-cublas-12.4.0-bin-x64/models/`.
- Dica de download via PowerShell (exemplo, ajuste versão se quiser):
```
Invoke-WebRequest -Uri "https://github.com/ggerganov/whisper.cpp/releases/download/v1.7.0/whisper-cublas-12.4.0-bin-x64.zip" -OutFile whisper-cublas.zip
Expand-Archive whisper-cublas.zip -DestinationPath .
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin" -OutFile "whisper-cublas-12.4.0-bin-x64/models/ggml-large-v3.bin"
```
Se usar aria2c: `aria2c -x8 -s8 <url>`.
