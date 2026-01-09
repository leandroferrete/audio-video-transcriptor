import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from tqdm import tqdm

MEDIA_EXTS = {
    # vídeo
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".wmv", ".m4v", ".mts", ".m2ts",
    # áudio
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"
}


@dataclass
class SrtSegment:
    idx: int
    start: str  # "HH:MM:SS,mmm"
    end: str    # "HH:MM:SS,mmm"
    text: str


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def iter_media_files(input_dir: Path, recursive: bool) -> List[Path]:
    if recursive:
        candidates = [p for p in input_dir.rglob("*") if p.is_file()]
    else:
        candidates = [p for p in input_dir.iterdir() if p.is_file()]
    return [p for p in candidates if p.suffix.lower() in MEDIA_EXTS]


def ffmpeg_extract_wav(ffmpeg_bin: str, input_media: Path, output_wav: Path) -> None:
    """
    Extrai WAV mono 16kHz PCM 16-bit (formato bem aceito pelo whisper.cpp),
    tanto de VÍDEO quanto de ÁUDIO.
    """
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(input_media),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(output_wav),
    ]
    cp = run_cmd(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{cp.stdout}")


def parse_srt(srt_path: Path) -> List[SrtSegment]:
    content = srt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return []

    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
    segments: List[SrtSegment] = []

    for b in blocks:
        lines = [ln.rstrip("\r") for ln in b.splitlines()]
        if len(lines) < 3:
            continue

        try:
            idx = int(lines[0].strip())
        except ValueError:
            idx = len(segments) + 1

        times = lines[1].strip()
        if "-->" not in times:
            continue
        start, end = [t.strip() for t in times.split("-->", 1)]

        text = "\n".join(lines[2:]).strip()
        segments.append(SrtSegment(idx=idx, start=start, end=end, text=text))

    return segments


def srt_to_timestamped_txt(segments: List[SrtSegment]) -> str:
    out_lines = []
    for s in segments:
        one_line_text = " ".join(s.text.splitlines()).strip()
        out_lines.append(f"{s.start} --> {s.end} | {one_line_text}")
    return "\n".join(out_lines) + ("\n" if out_lines else "")


def pick_latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = list(folder.glob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def try_run_whisper_cli(
    whisper_bin: Path,
    model_path: Path,
    wav_path: Path,
    workdir: Path,
    language: Optional[str],
    max_line_len: int,
    threads: Optional[int],
) -> None:
    """
    Tenta variações de flags do whisper.cpp para gerar SRT + TXT.
    """
    attempts: List[Tuple[List[str], str]] = []

    a = [str(whisper_bin), "-m", str(model_path), "-f", str(wav_path), "-osrt", "-otxt", "-ml", str(max_line_len)]
    if language:
        a += ["-l", language]
    if threads:
        a += ["-t", str(threads)]
    attempts.append((a, "flags curtas (-osrt/-otxt)"))

    b = [str(whisper_bin), "--model", str(model_path), "--file", str(wav_path), "--output-srt", "--output-txt", "-ml", str(max_line_len)]
    if language:
        b += ["--language", language]
    if threads:
        b += ["-t", str(threads)]
    attempts.append((b, "flags longas (--output-srt/--output-txt)"))

    c = [str(whisper_bin), "-m", str(model_path), "-osrt", "-otxt", "-ml", str(max_line_len), str(wav_path)]
    if language:
        c += ["-l", language]
    if threads:
        c += ["-t", str(threads)]
    attempts.append((c, "arquivo posicional"))

    last_out = ""
    for cmd, _label in attempts:
        cp = run_cmd(cmd, cwd=workdir)
        last_out = cp.stdout
        if cp.returncode == 0:
            return

    raise RuntimeError(
        "whisper.cpp (whisper-cli) falhou em todas as variações de comando.\n"
        "Saída/erro (última tentativa):\n"
        f"{last_out}"
    )


def transcribe_one(
    input_media: Path,
    output_dir: Path,
    ffmpeg_bin: str,
    whisper_bin: Path,
    model_path: Path,
    language: Optional[str],
    max_line_len: int,
    threads: Optional[int],
    keep_wav: bool,
) -> None:
    stem = input_media.stem
    ensure_dir(output_dir)

    with tempfile.TemporaryDirectory(prefix=f"whisper_{stem}_") as td:
        workdir = Path(td)

        wav_path = workdir / f"{stem}.wav"
        ffmpeg_extract_wav(ffmpeg_bin, input_media, wav_path)

        try_run_whisper_cli(
            whisper_bin=whisper_bin,
            model_path=model_path,
            wav_path=wav_path,
            workdir=workdir,
            language=language,
            max_line_len=max_line_len,
            threads=threads,
        )

        srt = pick_latest_file(workdir, "*.srt")
        txt = pick_latest_file(workdir, "*.txt")

        if not srt:
            raise RuntimeError("Não encontrei nenhum .srt gerado no diretório temporário.")

        segments = parse_srt(srt)
        transcript_txt = srt_to_timestamped_txt(segments)

        out_srt = output_dir / f"{stem}.srt"
        out_txt = output_dir / f"{stem}.transcript.timestamps.txt"
        out_plain = output_dir / f"{stem}.plain.txt"
        out_json = output_dir / f"{stem}.segments.json"

        shutil.copy2(srt, out_srt)
        out_txt.write_text(transcript_txt, encoding="utf-8")

        plain = "\n".join([" ".join(s.text.splitlines()).strip() for s in segments]).strip()
        out_plain.write_text((plain + "\n") if plain else "", encoding="utf-8")

        out_json.write_text(
            json.dumps(
                [{"idx": s.idx, "start": s.start, "end": s.end, "text": s.text} for s in segments],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if txt:
            shutil.copy2(txt, output_dir / f"{stem}.whispercpp.txt")

        if keep_wav:
            shutil.copy2(wav_path, output_dir / f"{stem}.wav")


def main() -> int:
    """
    Melhorias:
    - input pode ser uma PASTA (default ./input) OU um ARQUIVO (áudio/vídeo).
    - Se for pasta: processa todos os arquivos compatíveis (e pode ser recursivo).
    - Se for arquivo: transcreve só ele (mesma saída: SRT/TXT/JSON).
    """
    base_dir = Path(__file__).resolve().parent
    default_input_dir = base_dir / "input"
    default_output_dir = base_dir / "output"

    ap = argparse.ArgumentParser(
        description="Transcreve áudio/vídeo e gera SRT + TXT (com barra de progresso)."
    )
    ap.add_argument(
        "--input", "--input-dir",
        dest="input_path",
        default=str(default_input_dir),
        help="Arquivo ou pasta de entrada (default: ./input ao lado do script).",
    )
    ap.add_argument(
        "--output", "--output-dir",
        dest="output_dir",
        default=str(default_output_dir),
        help="Pasta de saída (default: ./output ao lado do script).",
    )

    ap.add_argument("--whisper-cli", required=True, help="Caminho do whisper-cli.exe (whisper.cpp).")
    ap.add_argument("--model", required=True, help="Caminho do modelo ggml/gguf (ex.: ggml-medium.bin).")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="Comando/caminho do ffmpeg (default: ffmpeg no PATH).")
    ap.add_argument("--language", default=None, help="Idioma (ex.: pt, en). Se omitir, autodetect.")
    ap.add_argument("--max-line-len", type=int, default=60, help="Quebra de linha aproximada no SRT (default: 60).")
    ap.add_argument("--threads", type=int, default=None, help="Número de threads CPU (opcional).")
    ap.add_argument("--keep-wav", action="store_true", help="Mantém WAV final em output (pode ficar grande).")
    ap.add_argument("--recursive", action="store_true", help="Se input for pasta: busca também em subpastas.")
    args = ap.parse_args()

    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir)
    whisper_bin = Path(args.whisper_cli)
    model_path = Path(args.model)

    ensure_dir(output_dir)

    if not whisper_bin.exists():
        print(f"ERRO: whisper-cli não existe: {whisper_bin}")
        return 2
    if not model_path.exists():
        print(f"ERRO: model não existe: {model_path}")
        return 2

    # Se o usuário não passou nada (default), cria a pasta ./input
    if str(input_path) == str(default_input_dir):
        ensure_dir(input_path)

    if not input_path.exists():
        print(f"ERRO: input não existe: {input_path}")
        return 2

    # Modo 1: arquivo único (áudio ou vídeo)
    if input_path.is_file():
        if input_path.suffix.lower() not in MEDIA_EXTS:
            print(f"ERRO: extensão não suportada: {input_path.suffix}")
            return 2
        files = [input_path]
    else:
        # Modo 2: pasta
        files = iter_media_files(input_path, recursive=args.recursive)

    if not files:
        print(f"Nenhum arquivo de mídia encontrado em: {input_path}")
        return 0

    print(f"Pasta base: {base_dir}")
    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")
    print(f"Encontrados {len(files)} arquivo(s). Iniciando...")

    ok = 0
    fail = 0

    for f in tqdm(files, desc="Transcrevendo", unit="arquivo"):
        tqdm.write(f"\nProcessando: {f.name}")
        try:
            transcribe_one(
                input_media=f,
                output_dir=output_dir,
                ffmpeg_bin=args.ffmpeg,
                whisper_bin=whisper_bin,
                model_path=model_path,
                language=args.language,
                max_line_len=args.max_line_len,
                threads=args.threads,
                keep_wav=args.keep_wav,
            )
            ok += 1
            tqdm.write("✅ OK")
        except Exception as e:
            fail += 1
            tqdm.write(f"❌ FALHOU: {e}")

    print(f"\nFinalizado. Sucesso: {ok} | Falhas: {fail} | Output: {output_dir}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
