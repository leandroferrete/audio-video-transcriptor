import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum

from tqdm import tqdm

# Força stdout/stderr a usar utf-8 com replace para evitar falhas de codec em consoles cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ===========================
# ESTILOS CAPCUT / VIRAL
# ===========================

class AnimationType(Enum):
    """Tipos de animação para karaoke estilo CapCut"""
    NONE = "none"                    # Sem animação
    POP = "pop"                      # Bounce/pop micro na palavra ativa
    BOUNCE = "bounce"                # Bounce mais pronunciado
    SCALE_IN = "scale_in"            # Cresce de pequeno para tamanho normal
    SHAKE = "shake"                  # Tremor horizontal (palavras-chave)
    GLOW = "glow"                    # Brilho/glow que aumenta
    COLOR_SWITCH = "color_switch"    # Troca de cor palavra por palavra
    TYPEWRITER = "typewriter"        # Efeito de digitação (não word-by-word)


class BackgroundStyle(Enum):
    """Estilo de fundo/caixa atrás do texto"""
    NONE = "none"                    # Sem caixa
    BOX = "box"                      # Retângulo sólido
    ROUNDED = "rounded"              # Retângulo arredondado (pill)
    GLASS = "glass"                  # Caixa translúcida (efeito vidro)
    HIGHLIGHT = "highlight"          # Marca-texto atrás da palavra


@dataclass
class CapcutStyleConfig:
    """Configuração completa de estilo CapCut para karaoke"""
    
    # Fonte
    font_name: str = "Montserrat"
    font_size: int = 52
    font_bold: bool = True
    all_caps: bool = True
    letter_spacing: int = 0  # em pixels (\fsp)
    
    # Cores (RGB hex: "FFFFFF")
    primary_color: str = "FFFFFF"      # Cor da palavra ativa
    secondary_color: str = "FFFFFF"    # Cor antes de ativar
    outline_color: str = "000000"      # Cor da borda
    shadow_color: str = "000000"       # Cor da sombra
    
    # Efeitos visuais
    outline_size: int = 3              # Tamanho da borda (\bord)
    shadow_depth: int = 2              # Profundidade da sombra (\shad)
    blur_strength: float = 0.0         # Blur gaussiano (\blur)
    
    # Background/caixa
    background_style: BackgroundStyle = BackgroundStyle.NONE
    background_color: str = "000000"   # Cor da caixa
    background_alpha: int = 180        # Transparência da caixa (0=opaco, 255=invisível)
    background_padding: int = 20       # Padding da caixa
    
    # Animação
    animation_type: AnimationType = AnimationType.COLOR_SWITCH
    animation_intensity: float = 1.0   # Multiplicador de intensidade (0.5 = sutil, 2.0 = exagerado)
    
    # Highlight palavra-por-palavra
    highlight_color: str = "FFFF00"    # Amarelo para destaque
    use_gradient: bool = False          # Usar gradiente (simulado com alpha)
    gradient_color: str = "FF00FF"     # Segunda cor do gradiente
    
    # Posicionamento
    margin_v: int = 50                 # Margem vertical (pixels da borda inferior)
    alignment: int = 2                 # 1-9 (numpad), 2 = bottom center
    max_chars_per_line: int = 28       # Limite de caracteres por linha (para não estourar a tela)
    max_lines: int = 2                 # Limite de linhas (quebra com \\N)
    
    def to_dict(self) -> dict:
        """Serializa para JSON/dict"""
        return {
            "font_name": self.font_name,
            "font_size": self.font_size,
            "font_bold": self.font_bold,
            "all_caps": self.all_caps,
            "letter_spacing": self.letter_spacing,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "outline_color": self.outline_color,
            "shadow_color": self.shadow_color,
            "outline_size": self.outline_size,
            "shadow_depth": self.shadow_depth,
            "blur_strength": self.blur_strength,
            "background_style": self.background_style.value,
            "background_color": self.background_color,
            "background_alpha": self.background_alpha,
            "background_padding": self.background_padding,
            "animation_type": self.animation_type.value,
            "animation_intensity": self.animation_intensity,
            "highlight_color": self.highlight_color,
            "use_gradient": self.use_gradient,
            "gradient_color": self.gradient_color,
            "margin_v": self.margin_v,
            "alignment": self.alignment,
            "max_chars_per_line": self.max_chars_per_line,
            "max_lines": self.max_lines,
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'CapcutStyleConfig':
        """Deserializa de JSON/dict"""
        return CapcutStyleConfig(
            font_name=data.get("font_name", "Montserrat"),
            font_size=data.get("font_size", 52),
            font_bold=data.get("font_bold", True),
            all_caps=data.get("all_caps", True),
            letter_spacing=data.get("letter_spacing", 0),
            primary_color=data.get("primary_color", "FFFFFF"),
            secondary_color=data.get("secondary_color", "FFFFFF"),
            outline_color=data.get("outline_color", "000000"),
            shadow_color=data.get("shadow_color", "000000"),
            outline_size=data.get("outline_size", 3),
            shadow_depth=data.get("shadow_depth", 2),
            blur_strength=data.get("blur_strength", 0.0),
            background_style=BackgroundStyle(data.get("background_style", "none")),
            background_color=data.get("background_color", "000000"),
            background_alpha=data.get("background_alpha", 180),
            background_padding=data.get("background_padding", 20),
            animation_type=AnimationType(data.get("animation_type", "color_switch")),
            animation_intensity=data.get("animation_intensity", 1.0),
            highlight_color=data.get("highlight_color", "FFFF00"),
            use_gradient=data.get("use_gradient", False),
            gradient_color=data.get("gradient_color", "FF00FF"),
            margin_v=data.get("margin_v", 50),
            alignment=data.get("alignment", 2),
            max_chars_per_line=data.get("max_chars_per_line", 28),
            max_lines=data.get("max_lines", 2),
        )


# PRESETS VIRAIS (baseado no estudo fonts.txt)

class CapcutPresets:
    """Presets de estilo prontos para usar - baseados nos estilos virais"""
    
    @staticmethod
    def viral_karaoke() -> CapcutStyleConfig:
        """1) Padrão viral (karaokê) - O mais usado em Reels/TikTok/Shorts"""
        return CapcutStyleConfig(
            font_name="Montserrat",
            font_size=46,
            font_bold=True,
            all_caps=True,
            letter_spacing=1,
            primary_color="FFE600",      # Dourado claro (ativo)
            secondary_color="F5F5F5",    # Off-white (inativo)
            outline_color="0B0B0B",
            outline_size=3,
            shadow_depth=1,
            blur_strength=0.6,
            background_style=BackgroundStyle.ROUNDED,
            background_color="000000",
            background_alpha=160,
            background_padding=18,
            animation_type=AnimationType.POP,
            animation_intensity=0.9,
            highlight_color="00FFC2",    # Verde-menta sutil
            margin_v=80,
            max_chars_per_line=34,  # ~1 linha 5-9 palavras, 2 linhas 10-14
            max_lines=2,
        )
    
    @staticmethod
    def viral_flat() -> CapcutStyleConfig:
        """1b) Viral flat - mesma base do viral, sem animação, highlight amarelo suave"""
        return CapcutStyleConfig(
            font_name="Montserrat",
            font_size=46,               # mantém proporção do viral; seguro em 1080p
            font_bold=True,
            all_caps=True,
            letter_spacing=1,
            primary_color="FFE600",     # Amarelo ativo
            secondary_color="F5F5F5",   # Off-white inativo
            outline_color="0B0B0B",
            outline_size=3,
            shadow_depth=1,
            blur_strength=0.4,
            background_style=BackgroundStyle.ROUNDED,
            background_color="000000",
            background_alpha=160,
            background_padding=18,
            animation_type=AnimationType.NONE,  # sem animação
            animation_intensity=0.0,
            highlight_color="FFE600",
            margin_v=80,
            max_chars_per_line=34,
            max_lines=2,
        )
    
    @staticmethod
    def clean_premium() -> CapcutStyleConfig:
        """2) Clean premium (podcast/entrevista) - Minimalista profissional"""
        return CapcutStyleConfig(
            font_name="Inter",
            font_size=40,
            font_bold=False,
            all_caps=False,
            primary_color="FFFFFF",
            secondary_color="B5C0CB",
            outline_color="000000",
            outline_size=0,
            shadow_depth=0,
            background_style=BackgroundStyle.ROUNDED,
            background_color="000000",
            background_alpha=190,
            background_padding=22,
            animation_type=AnimationType.COLOR_SWITCH,
            animation_intensity=0.6,
            margin_v=90,
            max_chars_per_line=36,
            max_lines=2,
        )
    
    @staticmethod
    def tutorial_tech() -> CapcutStyleConfig:
        """3) Tutorial tech - Fonte condensada com destaque ciano"""
        return CapcutStyleConfig(
            font_name="Oswald",
            font_size=44,
            font_bold=True,
            all_caps=True,
            letter_spacing=1,
            primary_color="00E0FF",      # Ciano premium
            secondary_color="EFF7FF",
            outline_color="000000",
            outline_size=2,
            shadow_depth=1,
            animation_type=AnimationType.SCALE_IN,
            animation_intensity=1.2,
            margin_v=78,
            max_chars_per_line=36,
            max_lines=2,
        )
    
    @staticmethod
    def storytime_fofoca() -> CapcutStyleConfig:
        """4) Storytime/fofoca - Bold arredondado com shake"""
        return CapcutStyleConfig(
            font_name="Poppins",
            font_size=44,
            font_bold=True,
            all_caps=False,
            primary_color="111111",
            secondary_color="2E2E2E",
            outline_color="FFFFFF",
            outline_size=3,
            background_style=BackgroundStyle.BOX,
            background_color="FFFFFF",
            background_alpha=230,
            background_padding=18,
            animation_type=AnimationType.SHAKE,
            animation_intensity=0.6,
            margin_v=76,
            max_chars_per_line=32,
            max_lines=2,
        )
    
    @staticmethod
    def motivacional() -> CapcutStyleConfig:
        """5) Motivacional - Glow dourado com scale"""
        return CapcutStyleConfig(
            font_name="Montserrat",
            font_size=48,
            font_bold=True,
            all_caps=True,
            letter_spacing=2,
            primary_color="FFD166",      # Dourado quente
            secondary_color="FFFFFF",
            outline_color="000000",
            outline_size=2,
            shadow_depth=2,
            blur_strength=0.6,           # Glow leve
            animation_type=AnimationType.GLOW,
            animation_intensity=1.1,
            use_gradient=True,
            gradient_color="FFA500",     # Laranja
            margin_v=82,
            max_chars_per_line=36,
            max_lines=2,
        )
    
    @staticmethod
    def terror_true_crime() -> CapcutStyleConfig:
        """6) Terror/true crime - Condensado com glitch vermelho"""
        return CapcutStyleConfig(
            font_name="Oswald",
            font_size=44,
            font_bold=True,
            all_caps=True,
            letter_spacing=3,
            primary_color="E60000",      # Vermelho sangue mais escuro
            secondary_color="FFFFFF",
            outline_color="000000",
            outline_size=2,
            background_style=BackgroundStyle.BOX,
            background_color="000000",
            background_alpha=200,
            animation_type=AnimationType.SHAKE,  # Simula glitch
            animation_intensity=1.3,
            margin_v=72,
            max_chars_per_line=32,
            max_lines=2,
        )
    
    @staticmethod
    def get_all_presets() -> Dict[str, CapcutStyleConfig]:
        """Retorna todos os presets disponíveis"""
        return {
            "viral_karaoke": CapcutPresets.viral_karaoke(),
            "viral_flat": CapcutPresets.viral_flat(),
            "clean_premium": CapcutPresets.clean_premium(),
            "tutorial_tech": CapcutPresets.tutorial_tech(),
            "storytime_fofoca": CapcutPresets.storytime_fofoca(),
            "motivacional": CapcutPresets.motivacional(),
            "terror_true_crime": CapcutPresets.terror_true_crime(),
        }
    
    @staticmethod
    def get_preset_names() -> List[str]:
        """Lista nomes dos presets"""
        return list(CapcutPresets.get_all_presets().keys())


# Suporta VÍDEO e ÁUDIO
MEDIA_EXTS = {
    # vídeo
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".wmv", ".m4v", ".mts", ".m2ts",
    # áudio
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}
AUDIO_ONLY_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


# ----------------------------
# SRT
# ----------------------------
@dataclass
class SrtSegment:
    idx: int
    start: str  # "HH:MM:SS,mmm"
    end: str    # "HH:MM:SS,mmm"
    text: str


def srt_time_to_ms(ts: str) -> int:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(",")
    return (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(ms)


def ms_to_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    total_s = ms // 1000
    msec = ms % 1000
    hh = total_s // 3600
    mm = (total_s % 3600) // 60
    ss = total_s % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},{msec:03d}"


def parse_srt(srt_path: Path) -> List[SrtSegment]:
    content = srt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        return []
    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
    out: List[SrtSegment] = []
    for b in blocks:
        lines = [ln.rstrip("\r") for ln in b.splitlines()]
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            idx = len(out) + 1
        if "-->" not in lines[1]:
            continue
        start, end = [t.strip() for t in lines[1].split("-->", 1)]
        text = "\n".join(lines[2:]).strip()
        out.append(SrtSegment(idx=idx, start=start, end=end, text=text))
    return out


def write_srt(segments: List[SrtSegment], path: Path) -> None:
    parts: List[str] = []
    for i, s in enumerate(segments, 1):
        parts.append(str(i))
        parts.append(f"{s.start} --> {s.end}")
        parts.append(s.text.strip())
        parts.append("")
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def write_vtt(segments: List[SrtSegment], path: Path) -> None:
    def t(ts: str) -> str:
        return ts.replace(",", ".")
    parts = ["WEBVTT", ""]
    for s in segments:
        parts.append(f"{t(s.start)} --> {t(s.end)}")
        parts.append(s.text.strip())
        parts.append("")
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def timestamped_txt(segments: List[SrtSegment]) -> str:
    lines = []
    for s in segments:
        one = " ".join(s.text.splitlines()).strip()
        lines.append(f"{s.start} --> {s.end} | {one}")
    return "\n".join(lines) + ("\n" if lines else "")


# ----------------------------
# Subtitle polish
# ----------------------------
def wrap_text(text: str, max_chars: int, max_lines: int) -> str:
    words = text.split()
    if not words:
        return ""
    lines: List[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    if len(lines) > max_lines:
        total = len(words)
        chunk = max(1, total // max_lines)
        lines = []
        i = 0
        for _ in range(max_lines - 1):
            part = words[i:i + chunk]
            if not part:
                break
            lines.append(" ".join(part))
            i += chunk
        lines.append(" ".join(words[i:]))

    final: List[str] = []
    for ln in lines:
        if len(ln) <= max_chars:
            final.append(ln)
        else:
            tmp = ""
            for w in ln.split():
                if not tmp:
                    tmp = w
                elif len(tmp) + 1 + len(w) <= max_chars:
                    tmp += " " + w
                else:
                    final.append(tmp)
                    tmp = w
            if tmp:
                final.append(tmp)
    return "\n".join(final[:max_lines])


def polish_segments(
    segments: List[SrtSegment],
    max_chars_per_line: int,
    max_lines: int,
    max_cps: float,
    min_dur_ms: int,
    max_dur_ms: int,
    merge_gap_ms: int,
) -> List[SrtSegment]:
    if not segments:
        return []

    items: List[Tuple[int, int, str]] = []
    for s in segments:
        st = srt_time_to_ms(s.start)
        en = max(st, srt_time_to_ms(s.end))
        txt = re.sub(r"\s+", " ", s.text).strip()
        if txt:
            items.append((st, en, txt))

    merged: List[Tuple[int, int, str]] = []
    for st, en, txt in items:
        if not merged:
            merged.append((st, en, txt))
            continue
        pst, pen, ptxt = merged[-1]
        gap = st - pen
        if 0 <= gap <= merge_gap_ms:
            merged[-1] = (pst, en, (ptxt + " " + txt).strip())
        else:
            merged.append((st, en, txt))

    adjusted: List[Tuple[int, int, str]] = []
    for i, (st, en, txt) in enumerate(merged):
        dur = max(1, en - st)
        words = txt.split()

        if dur < min_dur_ms:
            en = st + min_dur_ms
            dur = en - st

        # Quebra agressiva de segmentos longos em blocos menores (baseado em palavras)
        if dur > max_dur_ms and len(words) >= 4:
            parts = max(2, math.ceil(dur / max_dur_ms))
            chunk_size = max(1, len(words) // parts)
            total_words = len(words)
            cur_time = st
            for idx in range(0, total_words, chunk_size):
                wchunk = words[idx:idx + chunk_size]
                if not wchunk:
                    continue
                # estimativa de duração proporcional ao número de palavras
                remaining = total_words - idx
                remaining_time = en - cur_time
                # distribuição proporcional
                est = max(min_dur_ms, min(int(round(remaining_time * (len(wchunk) / remaining))), max_dur_ms))
                chunk_end = cur_time + est
                # garante que o último bloco termine exatamente no fim
                if idx + chunk_size >= total_words:
                    chunk_end = en
                adjusted.append((cur_time, chunk_end, " ".join(wchunk).strip()))
                cur_time = chunk_end
            continue

        chars = len(txt)
        cps = chars / (dur / 1000.0)
        if cps > max_cps:
            target = int((chars / max_cps) * 1000)
            target = max(min_dur_ms, min(target, max_dur_ms))
            if i + 1 < len(merged):
                next_st = merged[i + 1][0]
                en = min(st + target, max(st + 1, next_st - 1))
            else:
                en = st + target

        adjusted.append((st, en, txt))

    out: List[SrtSegment] = []
    for j, (st, en, txt) in enumerate(adjusted, 1):
        out.append(SrtSegment(idx=j, start=ms_to_srt_time(st), end=ms_to_srt_time(en),
                              text=wrap_text(txt, max_chars_per_line, max_lines)))
    return out


# ----------------------------
# PII + Glossary
# ----------------------------
PII_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PII_PHONE = re.compile(r"(?:(?:\+?55)\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}\b")
PII_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
PII_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def redact_pii(text: str) -> str:
    text = PII_EMAIL.sub("[EMAIL]", text)
    text = PII_PHONE.sub("[TEL]", text)
    text = PII_CPF.sub("[CPF]", text)
    text = PII_CNPJ.sub("[CNPJ]", text)
    return text


def load_glossary(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    mapping: Dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if "=" in ln:
            a, b = ln.split("=", 1)
            a = a.strip()
            b = b.strip()
            if a:
                mapping[a] = b
    return mapping


def apply_glossary(text: str, mapping: Dict[str, str]) -> str:
    if not mapping:
        return text
    for src, dst in mapping.items():
        text = text.replace(src, dst)
    return text


# ----------------------------
# Exec helpers
# ----------------------------
def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def ffmpeg_escape_path_for_filter(path: Path) -> str:
    """
    Escapa caminhos Windows para uso no filtro ass= do ffmpeg.
    - Converte para POSIX (/)
    - Escapa ":" (drive) e "'" (preserva nomes com aspas simples)
    - Envolve em aspas simples para manter espacos intactos
    """
    p = path.resolve().as_posix()
    p = p.replace(":", r"\:")
    p = p.replace("'", r"\'")
    return f"'{p}'"


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sig(path: Path) -> Dict[str, object]:
    st = path.stat()
    return {"size": st.st_size, "mtime": st.st_mtime}


def detect_best_audio_stream(ffmpeg_bin: str, media: Path) -> Optional[int]:
    """
    Usa ffprobe (do mesmo pacote do ffmpeg) para descobrir a trilha de áudio mais longa.
    Retorna índice zero-based no conjunto de ÁUDIO (para usar em -map 0:a:<idx>).
    """
    ffprobe = Path(ffmpeg_bin).with_name("ffprobe").as_posix()
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,duration",
        "-of", "csv=p=0",
        str(media),
    ]
    cp = run_cmd(cmd)
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    best_ord = None
    best_dur = -1.0
    for ord_idx, line in enumerate(cp.stdout.strip().splitlines()):
        parts = line.split(",")
        if not parts:
            continue
        dur = None
        if len(parts) > 1:
            try:
                dur = float(parts[1])
            except Exception:
                dur = None
        if dur is None:
            dur = -1.0
        if dur > best_dur:
            best_dur = dur
            best_ord = ord_idx
    return best_ord


def pick_latest(folder: Path, pattern: str) -> Optional[Path]:
    files = list(folder.glob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


# ----------------------------
# FFmpeg audio extraction / chunking
# ----------------------------
def ffmpeg_extract_wav(ffmpeg_bin: str, input_media: Path, output_wav: Path, audio_filter: Optional[str], audio_stream: Optional[int]) -> None:
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(input_media),
        "-map", f"0:a:{audio_stream}" if audio_stream is not None else "0:a:0",
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += [str(output_wav)]
    cp = run_cmd(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{cp.stdout}")


def ffmpeg_split_wav(ffmpeg_bin: str, wav_path: Path, chunk_seconds: int, out_dir: Path) -> List[Path]:
    ensure_dir(out_dir)
    out_pattern = out_dir / "chunk_%05d.wav"
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(wav_path),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "16000",
        str(out_pattern),
    ]
    cp = run_cmd(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"FFmpeg split falhou:\n{cp.stdout}")
    return sorted(out_dir.glob("chunk_*.wav"))


# ----------------------------
# whisper.cpp CLI
# ----------------------------
def whisper_cli_attempts(
    whisper_bin: Path,
    model_path: Path,
    wav_path: Path,
    workdir: Path,
    language: Optional[str],
    max_line_len: int,
    threads: Optional[int],
    prompt: Optional[str],
    extra_args: List[str],
) -> str:
    """
    Tenta variações de flags do whisper.cpp. Retorna stdout do último comando.
    """
    attempts: List[List[str]] = []

    a = [str(whisper_bin), "-m", str(model_path), "-f", str(wav_path), "-osrt", "-otxt", "-ml", str(max_line_len)]
    if language:
        a += ["-l", language]
    if threads:
        a += ["-t", str(threads)]
    if prompt:
        a += ["--prompt", prompt]
    a += extra_args
    attempts.append(a)

    b = [str(whisper_bin), "--model", str(model_path), "--file", str(wav_path), "--output-srt", "--output-txt", "-ml", str(max_line_len)]
    if language:
        b += ["--language", language]
    if threads:
        b += ["-t", str(threads)]
    if prompt:
        b += ["--prompt", prompt]
    b += extra_args
    attempts.append(b)

    c = [str(whisper_bin), "-m", str(model_path), "-osrt", "-otxt", "-ml", str(max_line_len), str(wav_path)]
    if language:
        c += ["-l", language]
    if threads:
        c += ["-t", str(threads)]
    if prompt:
        c += ["--prompt", prompt]
    c += extra_args
    attempts.append(c)

    last = ""
    for cmd in attempts:
        cp = run_cmd(cmd, cwd=workdir)
        last = cp.stdout
        if cp.returncode == 0:
            return last

    if prompt:
        return whisper_cli_attempts(
            whisper_bin=whisper_bin,
            model_path=model_path,
            wav_path=wav_path,
            workdir=workdir,
            language=language,
            max_line_len=max_line_len,
            threads=threads,
            prompt=None,
            extra_args=extra_args,
        )

    raise RuntimeError("whisper-cli falhou.\nÚltima saída:\n" + last)


# ----------------------------
# Karaoke ASS (CapCut-like highlight)
# ----------------------------
@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class KaraokeSegment:
    start: float
    end: float
    words: List[Word]
    speaker: Optional[str] = None


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def load_whisperx_json_words(path: Path) -> List[KaraokeSegment]:
    """
    Espera JSON gerado pelo WhisperX com timestamps por palavra (segments[].words[]).
    """
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    segs_raw = data.get("segments") or data.get("result", {}).get("segments") or []
    segments: List[KaraokeSegment] = []

    for s in segs_raw:
        st = _safe_float(s.get("start"), 0.0)
        en = _safe_float(s.get("end"), st)
        spk = s.get("speaker")
        words_raw = s.get("words") or []
        words: List[Word] = []
        for w in words_raw:
            wst = _safe_float(w.get("start"), st)
            wen = _safe_float(w.get("end"), wst)
            txt = (w.get("word") or w.get("text") or "").strip()
            if not txt:
                continue
            if wen <= wst:
                wen = wst + 0.01
            words.append(Word(start=wst, end=wen, text=txt))
        if words:
            st2 = min(st, min(w.start for w in words))
            en2 = max(en, max(w.end for w in words))
            segments.append(KaraokeSegment(start=st2, end=en2, words=words, speaker=spk))
    return segments


def whisperx_segments_to_srt_segments(ksegs: List[KaraokeSegment], speaker_prefix: bool) -> List[SrtSegment]:
    out: List[SrtSegment] = []
    for i, ks in enumerate(ksegs, 1):
        st_ms = int(round(ks.start * 1000))
        en_ms = int(round(ks.end * 1000))
        if en_ms <= st_ms:
            en_ms = st_ms + 1
        words = [w.text.strip() for w in ks.words if w.text.strip()]
        if not words:
            continue
        text = " ".join(words).strip()
        if speaker_prefix and ks.speaker:
            text = f"[{ks.speaker}] " + text
        out.append(SrtSegment(
            idx=i,
            start=ms_to_srt_time(st_ms),
            end=ms_to_srt_time(en_ms),
            text=text,
        ))
    return out


def build_karaoke_from_srt_approx(segments: List[SrtSegment], min_word_ms: int = 60) -> List[KaraokeSegment]:
    """
    Fallback SEM WhisperX:
    - distribui o tempo do segmento PROPORCIONALMENTE ao número de caracteres de cada palavra.
    - Isso é mais realista que divisão igual, pois palavras maiores levam mais tempo para falar.
    """
    out: List[KaraokeSegment] = []
    for s in segments:
        st_ms = srt_time_to_ms(s.start)
        en_ms = srt_time_to_ms(s.end)
        dur = max(1, en_ms - st_ms)
        text = " ".join(s.text.splitlines()).strip()
        words = [w for w in re.split(r"\s+", text) if w]
        if not words:
            continue
        
        # Calcular peso proporcional baseado no número de caracteres
        # Cada palavra tem peso mínimo de 1 caractere para evitar divisão por zero
        char_counts = [max(1, len(w)) for w in words]
        total_chars = sum(char_counts)
        
        cur = st_ms
        ww: List[Word] = []
        for i, w in enumerate(words):
            # Tempo proporcional ao número de caracteres
            word_dur = max(min_word_ms, int(round(dur * char_counts[i] / total_chars)))
            
            w_st = cur
            # Para a última palavra, garantir que termine exatamente no final do segmento
            if i == len(words) - 1:
                w_en = en_ms
            else:
                w_en = min(en_ms, cur + word_dur)
            
            ww.append(Word(start=w_st / 1000.0, end=w_en / 1000.0, text=w))
            cur = w_en
        
        out.append(KaraokeSegment(start=st_ms / 1000.0, end=en_ms / 1000.0, words=ww, speaker=None))
    return out


def ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    total = int(t)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    cc = int(round((t - total) * 100))
    if cc >= 100:
        cc = 99
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def ass_color_bgr_hex(rgb_hex: str) -> str:
    rgb_hex = rgb_hex.strip().lstrip("#")
    if len(rgb_hex) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", rgb_hex):
        rgb_hex = "FFFFFF"
    r = rgb_hex[0:2]
    g = rgb_hex[2:4]
    b = rgb_hex[4:6]
    return f"&H00{b}{g}{r}"


def build_karaoke_text(words: List[Word], min_cs: int = 1, segment_start: float = 0.0) -> str:
    """
    Constrói texto karaoke ASS com timing correto estilo CapCut.
    
    No formato ASS, a tag \\k especifica QUANDO destacar cada sílaba/palavra.
    Os valores são CUMULATIVOS - a soma dos \\k até a palavra N indica o 
    momento (relativo ao início do Dialogue) em que a palavra N é destacada.
    
    Exemplo: {\\k50}Olá {\\k30}Mundo
    - "Olá" destaca em t=0.5s (50cs após início do Dialogue)
    - "Mundo" destaca em t=0.8s (50cs + 30cs = 80cs após início)
    
    Para sincronizar corretamente, cada \\k deve representar o intervalo
    de tempo DESDE O MOMENTO QUE A PALAVRA ANTERIOR FOI DESTACADA até
    o momento que ESTA palavra deve ser destacada.
    
    Args:
        words: Lista de palavras com timestamps absolutos (start/end em segundos)
        min_cs: Duração mínima em centissegundos (default: 1)
        segment_start: Timestamp de início do segmento/Dialogue (em segundos)
    """
    if not words:
        return ""
    
    parts: List[str] = []
    
    for i, w in enumerate(words):
        if i == 0:
            # Primeira palavra: tempo desde o início do segmento até esta palavra começar
            # Se a palavra começa exatamente no início do segmento, \k0 (destaca imediatamente)
            delay_seconds = max(0.0, w.start - segment_start)
        else:
            # Palavras subsequentes: tempo desde quando a palavra ANTERIOR começou
            # até quando ESTA palavra começa
            prev_word = words[i - 1]
            delay_seconds = max(0.0, w.start - prev_word.start)
        
        cs = max(min_cs if i > 0 else 0, int(round(delay_seconds * 100)))
        safe = w.text.replace("{", "").replace("}", "")
        parts.append(r"{\k" + str(cs) + r"}" + safe + " ")
    
    return "".join(parts).rstrip()


def build_karaoke_text_capcut(
    words: List[Word], 
    segment_start: float, 
    style_config: CapcutStyleConfig,
    min_cs: int = 1
) -> str:
    """
    Constrói texto karaoke ASS com animações estilo CapCut/TikTok/Viral.
    
    Suporta:
    - Animações \\t (pop, bounce, scale, shake, glow)
    - Mudança de cor palavra-por-palavra
    - Letter spacing customizado (\\fsp)
    - ALL CAPS automático
    
    Args:
        words: Lista de palavras com timestamps
        segment_start: Início do segmento em segundos
        style_config: Configuração de estilo CapCut
        min_cs: Duração mínima em centissegundos
    
    Returns:
        String ASS formatada com efeitos
    """
    if not words:
        return ""
    
    parts: List[str] = []
    
    # Cor de destaque para palavra ativa (primary)
    primary_rgb = style_config.primary_color
    primary_ass = ass_color_bgr_hex(primary_rgb)
    
    # Cor secundária (antes de ativar)
    secondary_ass = ass_color_bgr_hex(style_config.secondary_color)
    
    # Intensidade das animações
    intensity = style_config.animation_intensity
    
    for i, w in enumerate(words):
        # Calcular delay (tempo até destacar esta palavra)
        if i == 0:
            delay_seconds = max(0.0, w.start - segment_start)
        else:
            prev_word = words[i - 1]
            delay_seconds = max(0.0, w.start - prev_word.start)
        
        cs = max(min_cs if i > 0 else 0, int(round(delay_seconds * 100)))
        
        # Duração da palavra (para animações)
        word_duration = max(0.1, w.end - w.start)
        word_duration_ms = int(word_duration * 1000)
        
        # Processar texto
        text = w.text.replace("{", "").replace("}", "")
        if style_config.all_caps:
            text = text.upper()
        
        # Montar override block com animação
        override_tags = []
        
        # Letter spacing (se configurado)
        if style_config.letter_spacing != 0:
            override_tags.append(f"\\fsp{style_config.letter_spacing}")
        
        # Tag de karaoke básica
        override_tags.append(f"\\k{cs}")
        
        # ANIMAÇÕES ESTILO CAPCUT
        if style_config.animation_type == AnimationType.POP:
            # Bounce/Pop: Escala 100% → 110% → 100% rapidamente
            scale_max = int(100 + 10 * intensity)
            anim_dur = min(150, word_duration_ms // 2)  # Animação rápida
            override_tags.append(f"\\t(0,{anim_dur},\\fscx{scale_max}\\fscy{scale_max})")
            override_tags.append(f"\\t({anim_dur},{anim_dur*2},\\fscx100\\fscy100)")
        
        elif style_config.animation_type == AnimationType.BOUNCE:
            # Bounce mais pronunciado
            scale_max = int(100 + 20 * intensity)
            anim_dur = min(200, word_duration_ms // 2)
            override_tags.append(f"\\t(0,{anim_dur},\\fscx{scale_max}\\fscy{scale_max})")
            override_tags.append(f"\\t({anim_dur},{anim_dur*2},\\fscx100\\fscy100)")
        
        elif style_config.animation_type == AnimationType.SCALE_IN:
            # Cresce de 0% → 100%
            scale_start = max(0, int(100 - 80 * intensity))
            anim_dur = min(300, word_duration_ms)
            override_tags.insert(0, f"\\fscx{scale_start}\\fscy{scale_start}")  # Estado inicial
            override_tags.append(f"\\t(0,{anim_dur},\\fscx100\\fscy100)")
        
        elif style_config.animation_type == AnimationType.SHAKE:
            # Tremor horizontal (simula glitch)
            # ASS não tem shake nativo, simulamos com múltiplas transformações de posição
            # Alternativa: usar \\fax (shearing) para efeito de "vibração"
            shear = 0.1 * intensity
            anim_dur = min(100, word_duration_ms // 3)
            override_tags.append(f"\\t(0,{anim_dur},\\fax{shear})")
            override_tags.append(f"\\t({anim_dur},{anim_dur*2},\\fax{-shear})")
            override_tags.append(f"\\t({anim_dur*2},{anim_dur*3},\\fax0)")
        
        elif style_config.animation_type == AnimationType.GLOW:
            # Aumenta blur gradualmente (simula glow)
            blur_max = 2.0 * intensity
            anim_dur = min(250, word_duration_ms)
            override_tags.append(f"\\t(0,{anim_dur},\\blur{blur_max})")
            override_tags.append(f"\\t({anim_dur},{word_duration_ms},\\blur0)")
        
        # Montar string final
        override_block = "{" + "".join(override_tags) + "}"
        parts.append(override_block + text + " ")
    
    return "".join(parts).rstrip()


def wrap_ass_line(text: str, max_chars: int, max_lines: int = 0) -> str:
    r"""
    Insere quebras de linha (\\N) em texto ASS respeitando limite de caracteres visíveis.
    Ignora tags {\\...} na contagem para evitar estouro na tela. Se max_lines > 0,
    limita o número de linhas (linhas excedentes são agregadas na última).
    """
    if max_chars <= 0:
        return text
    tokens = text.split(" ")
    lines: List[str] = [""]
    visible_len: List[int] = [0]

    def append_token(idx: int, tok: str):
        if lines[idx]:
            lines[idx] += " " + tok
        else:
            lines[idx] = tok
        visible = re.sub(r"\{[^}]*\}", "", tok)
        visible_len[idx] += len(visible) + (1 if visible_len[idx] > 0 else 0)

    for tok in tokens:
        if tok == "":
            continue
        visible_tok = re.sub(r"\{[^}]*\}", "", tok)
        wlen = len(visible_tok)
        current = len(lines) - 1
        projected = visible_len[current] + (1 if visible_len[current] > 0 else 0) + wlen
        if visible_len[current] > 0 and projected > max_chars:
            if max_lines and len(lines) >= max_lines:
                append_token(current, tok)  # força na última linha
            else:
                lines.append(tok)
                visible_len.append(wlen)
        else:
            append_token(current, tok)

    return "\\N".join(lines)


def add_background_box(text: str, style_config: CapcutStyleConfig) -> str:
    """Adiciona background box atrás do texto (simplificado)."""
    return text


def write_ass_karaoke(
    segments: List[KaraokeSegment],
    out_ass: Path,
    *,
    font: str = None,
    font_size: int = None,
    res: Tuple[int, int] = None,
    margin_v: int = None,
    outline: int = None,
    shadow: int = None,
    highlight_rgb: str = None,
    base_rgb: str = None,
    use_speaker_prefix: bool = False,
    style_config: Optional[CapcutStyleConfig] = None,
) -> None:
    """Escreve arquivo ASS com karaoke estilo CapCut."""
    if style_config is None:
        style_config = CapcutStyleConfig(
            font_name=font or "Arial",
            font_size=font_size or 48,
            primary_color=highlight_rgb or "FFFF00",
            secondary_color=base_rgb or "FFFFFF",
            outline_size=outline or 3,
            shadow_depth=shadow or 2,
            margin_v=margin_v or 50,
            animation_type=AnimationType.COLOR_SWITCH,
        )
    
    w, h = res if res else (1920, 1080)
    
    primary = ass_color_bgr_hex(style_config.primary_color)
    secondary = ass_color_bgr_hex(style_config.secondary_color)
    outline_color = ass_color_bgr_hex(style_config.outline_color)
    shadow_color = ass_color_bgr_hex(style_config.shadow_color)
    
    bold_flag = "-1" if style_config.font_bold else "0"
    border_style = 1
    back_color = "&H00000000"
    
    if style_config.background_style != BackgroundStyle.NONE:
        bg_color_rgb = style_config.background_color
        back_color = ass_color_bgr_hex(bg_color_rgb)
        alpha_hex = f"{style_config.background_alpha:02X}"
        back_color = back_color.replace("&H00", f"&H{alpha_hex}")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config.font_name},{style_config.font_size},{primary},{secondary},{outline_color},{back_color},{bold_flag},0,0,0,100,100,{style_config.letter_spacing},0,{border_style},{style_config.outline_size},{style_config.shadow_depth},{style_config.alignment},60,60,{style_config.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    for seg in segments:
        start = ass_time(seg.start)
        end = ass_time(seg.end)
        prefix = ""
        if use_speaker_prefix and seg.speaker:
            prefix = f"[{seg.speaker}] "
        
        # Sempre usa builder CapCut para respeitar CAPS/letter spacing/cor,
        # mesmo quando a animação é NONE.
        text = prefix + build_karaoke_text_capcut(seg.words, seg.start, style_config)

        # Quebra linha para evitar estouro (conta só caracteres visíveis)
        if style_config.max_chars_per_line:
            text = wrap_ass_line(text, style_config.max_chars_per_line, style_config.max_lines)

        if style_config.background_style in [BackgroundStyle.BOX, BackgroundStyle.ROUNDED]:
            text = add_background_box(text, style_config)
        
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    out_ass.write_text("\n".join(lines), encoding="utf-8")


def burn_ass_to_video(
    ffmpeg_bin: str,
    input_media: Path,
    ass_path: Path,
    output_video: Path,
    *,
    audio_only_bg: str,
    audio_only_res: Tuple[int, int],
    audio_only_fps: int,
    ffmpeg_crf: int,
    ffmpeg_preset: str,
) -> None:
    ensure_dir(output_video.parent)
    ass_filter = f"ass={ffmpeg_escape_path_for_filter(ass_path)}"

    if input_media.suffix.lower() in AUDIO_ONLY_EXTS:
        w, h = audio_only_res
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", f"color=c={audio_only_bg}:s={w}x{h}:r={audio_only_fps}",
            "-i", str(input_media),
            "-shortest",
            "-vf", ass_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", ffmpeg_preset,
            "-crf", str(ffmpeg_crf),
            "-c:a", "aac",
            str(output_video),
        ]
        cp = run_cmd(cmd)
        if cp.returncode != 0:
            raise RuntimeError("FFmpeg (audio->video) falhou.\nSaída:\n" + cp.stdout)
        return

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(input_media),
        "-vf", ass_filter,
        "-c:v", "libx264", "-crf", str(ffmpeg_crf), "-preset", ffmpeg_preset,
        "-c:a", "copy",
        str(output_video),
    ]
    cp = run_cmd(cmd)
    if cp.returncode == 0:
        return

    cmd2 = [
        ffmpeg_bin, "-y",
        "-i", str(input_media),
        "-vf", ass_filter,
        "-c:v", "libx264", "-crf", str(ffmpeg_crf), "-preset", ffmpeg_preset,
        "-c:a", "aac",
        str(output_video),
    ]
    cp2 = run_cmd(cmd2)
    if cp2.returncode != 0:
        raise RuntimeError("FFmpeg falhou (copy e fallback aac).\nCopy saída:\n" + cp.stdout + "\n\nAAC fallback:\n" + cp2.stdout)


# ----------------------------
# WhisperX runner (opcional)
# ----------------------------
def run_whisperx_to_json_local(
    whisperx_exe: str,
    media_path: Path,
    out_dir: Path,
    model: str,
    language: Optional[str],
    diarize: bool,
    hf_token_env: str,
) -> Path:
    """
    Executa WhisperX por CLI (instalado localmente) e pede JSON.
    Tenta primeiro o executável diretamente; se falhar, usa python -m whisperx.
    """
    ensure_dir(out_dir)

    hf_token = os.environ.get(hf_token_env)
    whisperx_path = Path(whisperx_exe)
    
    # Detectar o Python do mesmo venv do whisperx.exe
    python_exe = None
    if whisperx_path.exists():
        venv_scripts = whisperx_path.parent
        python_candidate = venv_scripts / "python.exe"
        if python_candidate.exists():
            python_exe = str(python_candidate)
    
    # Construir comandos - tentar múltiplas abordagens
    attempts: List[List[str]] = []
    
    # Base args do WhisperX
    base_args = [str(media_path), "--model", model, "--output_dir", str(out_dir), "--output_format", "json"]
    if language:
        base_args += ["--language", language]
    if diarize:
        base_args += ["--diarize"]
    if hf_token:
        base_args += ["--hf_token", hf_token]
    
    # Tentativa 1: Usar python -m whisperx (mais confiável)
    if python_exe:
        attempts.append([python_exe, "-m", "whisperx"] + base_args)
        attempts.append([python_exe, "-m", "whisperx"] + base_args + ["--compute_type", "float16"])
    
    # Tentativa 2: Usar o executável diretamente
    attempts.append([whisperx_exe] + base_args)
    attempts.append([whisperx_exe] + base_args + ["--compute_type", "float16"])

    last = ""
    for cmd in attempts:
        cp = run_cmd(cmd)
        last = cp.stdout
        if cp.returncode == 0:
            jss = list(out_dir.glob("*.json"))
            if not jss:
                raise RuntimeError("WhisperX rodou mas não gerou .json no output.\nSaída:\n" + last)
            jss.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return jss[0]

    raise RuntimeError("WhisperX falhou.\nSaída:\n" + last)


def run_whisperx_to_json_docker(
    docker_bin: str,
    image: str,
    media_path: Path,
    out_dir: Path,
    model: str,
    language: Optional[str],
    diarize: bool,
    hf_token_env: str,
    cache_dir: Optional[Path],
) -> Path:
    """
    Executa WhisperX via Docker (não depende do seu Python 3.14 no host).
    - Monta a pasta do arquivo de mídia em /in
    - Monta out_dir em /out
    - Gera JSON em /out
    """
    ensure_dir(out_dir)

    media_dir = media_path.parent.resolve()
    out_dir = out_dir.resolve()

    cmd: List[str] = [docker_bin, "run", "--rm", "--gpus", "all"]

    # cache HF/pytorch (opcional)
    if cache_dir:
        cache_dir = cache_dir.resolve()
        ensure_dir(cache_dir)
        cmd += ["-v", f"{str(cache_dir)}:/root/.cache"]

    # HF token (opcional)
    token = os.environ.get(hf_token_env)
    if token:
        cmd += ["-e", f"{hf_token_env}={token}"]

    # mounts
    cmd += ["-v", f"{str(media_dir)}:/in", "-v", f"{str(out_dir)}:/out"]

    # imagem + args do whisperx
    # Em algumas imagens (ex.: ghcr.io/jim60105/whisperx:*), é comum usar "--" antes dos args do whisperx.
    # Se a imagem não precisar, normalmente não quebra; se quebrar, remova o "--" na sua imagem escolhida.
    cmd += [image, "--",
            "--output_dir", "/out",
            "--output_format", "json",
            "--model", model]

    if language:
        cmd += ["--language", language]
    if diarize:
        cmd += ["--diarize"]

    cmd += [f"/in/{media_path.name}"]

    cp = run_cmd(cmd)
    if cp.returncode != 0:
        raise RuntimeError("WhisperX (Docker) falhou.\nSaída:\n" + cp.stdout)

    jss = list(out_dir.glob("*.json"))
    if not jss:
        raise RuntimeError("WhisperX (Docker) rodou mas não gerou .json no output.\nSaída:\n" + cp.stdout)
    jss.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jss[0]


def run_whisperx_sidecar(
    media: Path,
    out_json: Path,
    *,
    whisperx_cli: Optional[str],
    whisperx_docker_image: Optional[str],
    docker_bin: str,
    model: str,
    language: Optional[str],
    diarize: bool,
    hf_token_env: str,
    cache_dir: Optional[Path],
) -> Optional[Path]:
    """
    Executa WhisperX (local ou Docker) para gerar JSON com words/diarize,
    mas não quebra o fluxo principal se falhar (retorna None).
    """
    try:
        with tempfile.TemporaryDirectory(prefix="whisperx_sidecar_") as td:
            td_path = Path(td)
            if whisperx_cli:
                wx_json = run_whisperx_to_json_local(
                    whisperx_exe=whisperx_cli,
                    media_path=media,
                    out_dir=td_path,
                    model=model,
                    language=language,
                    diarize=diarize,
                    hf_token_env=hf_token_env,
                )
            elif whisperx_docker_image:
                wx_json = run_whisperx_to_json_docker(
                    docker_bin=docker_bin,
                    image=whisperx_docker_image,
                    media_path=media,
                    out_dir=td_path,
                    model=model,
                    language=language,
                    diarize=diarize,
                    hf_token_env=hf_token_env,
                    cache_dir=cache_dir,
                )
            else:
                return None
            out_json.write_text(wx_json.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return out_json
    except Exception as exc:
        print(f"Aviso: WhisperX sidecar falhou: {exc}")
        return None


# ----------------------------
# State / cache
# ----------------------------
def load_state(path: Path) -> Dict:
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": {}}


def save_state(path: Path, state: Dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def options_fingerprint(opts: Dict) -> str:
    blob = json.dumps(opts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def is_supported_media(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MEDIA_EXTS


def collect_files(input_path: Path, recursive: bool) -> List[Path]:
    if input_path.is_file():
        return [input_path] if is_supported_media(input_path) else []
    cand = input_path.rglob("*") if recursive else input_path.iterdir()
    files = [p for p in cand if p.is_file() and p.suffix.lower() in MEDIA_EXTS]
    return sorted(files, key=lambda p: p.name.lower())


# ----------------------------
# Main processing
# ----------------------------
def transcribe_one_whispercpp(
    input_media: Path,
    output_dir: Path,
    ffmpeg_bin: str,
    whisper_bin: Path,
    model_path: Path,
    language: Optional[str],
    max_line_len: int,
    threads: Optional[int],
    prompt: Optional[str],
    extra_args: List[str],
    keep_wav: bool,
    audio_filter: Optional[str],
    audio_stream: Optional[int],
    auto_audio_stream: bool,
    chunk_seconds: int,
    polish: bool,
    polish_params: Dict,
    redact: bool,
    glossary_map: Dict[str, str],
    make_vtt: bool,
    run_log: Path,
) -> Tuple[List[SrtSegment], str]:
    """
    Retorna (segments, whisper_stdout_full).
    """
    stem = input_media.stem
    ensure_dir(output_dir)

    def log(msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {stem} | {msg}\n"
        prev = run_log.read_text(encoding="utf-8", errors="replace") if run_log.exists() else ""
        run_log.write_text(prev + line, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix=f"whisper_{stem}_") as td:
        workdir = Path(td)
        wav = workdir / f"{stem}.wav"

        # escolher trilha de audio
        chosen_stream = audio_stream
        if chosen_stream is None and auto_audio_stream:
            chosen_stream = detect_best_audio_stream(ffmpeg_bin, input_media)

        log("ffmpeg: extraindo WAV...")
        ffmpeg_extract_wav(ffmpeg_bin, input_media, wav, audio_filter, chosen_stream)

        all_segments: List[SrtSegment] = []
        whisper_stdout_all = ""

        if chunk_seconds > 0:
            log(f"ffmpeg: split WAV em chunks de {chunk_seconds}s...")
            chunks = ffmpeg_split_wav(ffmpeg_bin, wav, chunk_seconds, workdir / "chunks")
            if not chunks:
                raise RuntimeError("Split gerou 0 chunks.")

            for i, ch in enumerate(chunks):
                ch_dir = workdir / f"chunk_{i:05d}"
                ensure_dir(ch_dir)
                log(f"whisper: chunk {i+1}/{len(chunks)}")
                out = whisper_cli_attempts(whisper_bin, model_path, ch, ch_dir, language, max_line_len, threads, prompt, extra_args)
                whisper_stdout_all += "\n" + out

                srt = pick_latest(ch_dir, "*.srt")
                if not srt:
                    raise RuntimeError(f"Não achei .srt do chunk {ch.name}")
                segs = parse_srt(srt)
                offset = i * chunk_seconds * 1000
                for s in segs:
                    all_segments.append(SrtSegment(
                        idx=0,
                        start=ms_to_srt_time(srt_time_to_ms(s.start) + offset),
                        end=ms_to_srt_time(srt_time_to_ms(s.end) + offset),
                        text=s.text,
                    ))
        else:
            log("whisper: arquivo único...")
            out = whisper_cli_attempts(whisper_bin, model_path, wav, workdir, language, max_line_len, threads, prompt, extra_args)
            whisper_stdout_all += out
            srt = pick_latest(workdir, "*.srt")
            if not srt:
                raise RuntimeError("Não encontrei nenhum .srt gerado.")
            all_segments = parse_srt(srt)

        # pós-processos texto
        if glossary_map or redact:
            for s in all_segments:
                t = s.text
                if glossary_map:
                    t = apply_glossary(t, glossary_map)
                if redact:
                    t = redact_pii(t)
                s.text = t

        # polish legenda
        if polish:
            all_segments = polish_segments(
                all_segments,
                max_chars_per_line=polish_params["max_chars_per_line"],
                max_lines=polish_params["max_lines"],
                max_cps=polish_params["max_cps"],
                min_dur_ms=polish_params["min_dur_ms"],
                max_dur_ms=polish_params["max_dur_ms"],
                merge_gap_ms=polish_params["merge_gap_ms"],
            )

        # renumera
        for i, s in enumerate(all_segments, 1):
            s.idx = i

        # outputs "antigos"
        out_srt = output_dir / f"{stem}.srt"
        out_vtt = output_dir / f"{stem}.vtt"
        out_ts = output_dir / f"{stem}.transcript.timestamps.txt"
        out_plain = output_dir / f"{stem}.plain.txt"
        out_json = output_dir / f"{stem}.segments.json"
        out_meta = output_dir / f"{stem}.meta.json"
        out_whisper_log = output_dir / f"{stem}.whispercpp.txt"

        write_srt(all_segments, out_srt)
        if make_vtt:
            write_vtt(all_segments, out_vtt)

        out_ts.write_text(timestamped_txt(all_segments), encoding="utf-8")

        plain = "\n".join(" ".join(s.text.splitlines()).strip() for s in all_segments).strip()
        out_plain.write_text((plain + "\n") if plain else "", encoding="utf-8")

        out_json.write_text(
            json.dumps([{"idx": s.idx, "start": s.start, "end": s.end, "text": s.text} for s in all_segments],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        out_meta.write_text(
            json.dumps(
                {
                    "input": str(input_media),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "engine": "whisper.cpp",
                    "model": str(model_path),
                    "language": language,
                    "chunk_seconds": chunk_seconds,
                    "polish": polish,
                    "redact_pii": redact,
                    "glossary_items": len(glossary_map),
                    "vtt": make_vtt,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        out_whisper_log.write_text(whisper_stdout_all.strip() + "\n", encoding="utf-8", errors="replace")

        if keep_wav:
            shutil.copy2(wav, output_dir / f"{stem}.wav")

        log("OK: outputs whisper.cpp gerados.")
        return all_segments, whisper_stdout_all


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    default_input = base_dir / "input"
    default_output = base_dir / "output"

    ap = argparse.ArgumentParser(
        description="Transcritor PRO + Karaoke (CapCut-like highlight) | whisper.cpp -> SRT/TXT/JSON + ASS + Burn no vídeo.",
    )

    # I/O
    ap.add_argument("--input", default=str(default_input), help="Arquivo ou pasta (default: ./input).")
    ap.add_argument("--output", default=str(default_output), help="Pasta de saída (default: ./output).")
    ap.add_argument("--recursive", action="store_true", help="Se input for pasta, busca também em subpastas.")
    ap.add_argument("--watch", action="store_true", help="Monitorar a pasta e transcrever novos arquivos.")
    ap.add_argument("--watch-interval", type=float, default=2.0, help="Intervalo do watch em segundos.")

    # whisper.cpp
    ap.add_argument("--whisper-cli", required=True, help="Caminho do whisper-cli.exe (whisper.cpp).")
    ap.add_argument("--model", required=True, help="Caminho do modelo ggml/gguf.")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="Caminho/comando do ffmpeg (default: ffmpeg no PATH).")
    ap.add_argument("--language", default=None, help="Idioma (pt, en, etc). Se omitir, autodetect.")
    ap.add_argument("--threads", type=int, default=None, help="Threads CPU (opcional).")
    ap.add_argument("--max-line-len", type=int, default=60, help="Wrap sugerido pro whisper.cpp (default: 60).")
    ap.add_argument("--prompt", default=None, help="Prompt inicial pro Whisper (opcional).")
    ap.add_argument("--whisper-extra-args", default="", help="Args extras pro whisper-cli (string).")

    # áudio
    ap.add_argument("--audio-filter", default=None, help="Filtro ffmpeg opcional (ex.: loudnorm).")
    ap.add_argument("--chunk-seconds", type=int, default=0, help="Divide em chunks (segundos). 0 = desliga.")
    ap.add_argument("--keep-wav", action="store_true", help="Salva WAV final em output (pode ficar grande).")
    ap.add_argument("--audio-stream", type=int, default=None, help="Índice da trilha de áudio (0=a primeira). Se omitir, usa auto se habilitado.")
    ap.add_argument("--auto-audio-stream", action=argparse.BooleanOptionalAction, default=True,
                    help="Detectar e usar a trilha de áudio mais longa via ffprobe (default: on).")

    # outputs extras
    ap.add_argument("--vtt", action="store_true", help="Gera também .vtt.")
    ap.add_argument("--polish", action="store_true", help="Polir SRT (wrap + CPS + merge).")
    ap.add_argument("--max-cps", type=float, default=17.0)
    ap.add_argument("--max-chars-per-line", type=int, default=42)
    ap.add_argument("--max-lines", type=int, default=2)
    ap.add_argument("--min-dur-ms", type=int, default=700)
    ap.add_argument("--max-dur-ms", type=int, default=7000)
    ap.add_argument("--merge-gap-ms", type=int, default=200)

    ap.add_argument("--redact-pii", action="store_true", help="Redigir email/tel/cpf/cnpj.")
    ap.add_argument("--glossary", default=None, help="Glossário (.json ou .txt 'errado=certo').")

    # karaoke/burn
    ap.add_argument("--karaoke", action="store_true", help="Gera .karaoke.ass e .karaoke.mp4 (hardsub).")
    ap.add_argument("--karaoke-engine", choices=["auto", "whisperx", "approx"], default="auto",
                    help="auto=usa WhisperX se disponível, senão approx.")
    ap.add_argument("--whisperx-cli", default=None, help="Caminho/comando do WhisperX local (ex.: ...\\venv\\Scripts\\whisperx.exe).")
    ap.add_argument("--whisperx-docker-image", default=None, help="Imagem Docker do WhisperX (ex.: ghcr.io/jim60105/whisperx:no_model).")
    ap.add_argument("--docker", default="docker", help="Comando do Docker (default: docker).")
    ap.add_argument("--whisperx-cache-dir", default=None, help="Pasta de cache para montar em /root/.cache (evita redownload).")
    ap.add_argument("--hf-token-env", default="HUGGINGFACE_HUB_TOKEN", help="Nome da env var do token HF (para diarize).")
    ap.add_argument("--whisperx-model", default="medium", help="Modelo do WhisperX (ex.: medium, large-v2).")
    ap.add_argument("--diarize", action="store_true", help="WhisperX diarization (requer token HF via env var).")
    ap.add_argument("--speaker-prefix", action="store_true", help="Prefixa [SPEAKER_00] no texto no ASS quando existir.")

    # Estilo CapCut/Viral
    ap.add_argument("--capcut-style", default=None, choices=list(CapcutPresets.get_preset_names()) + [None], 
                    help="Preset de estilo CapCut/TikTok (viral_karaoke, clean_premium, tutorial_tech, etc). Se não especificado, usa estilo legacy simples.")
    ap.add_argument("--capcut-font-size", type=int, default=None, help="Override de tamanho da fonte para preset CapCut (padrão: do preset).")
    ap.add_argument("--capcut-uppercase", choices=["auto", "on", "off"], default="auto",
                    help="Força CAPS (on), mantém caixa original (off) ou usa o preset (auto).")

    # Estilo legacy (usado se --capcut-style não for especificado)
    ap.add_argument("--font", default="Arial")
    ap.add_argument("--font-size", type=int, default=56)
    ap.add_argument("--res", default="1920x1080", help="Resolução render (PlayResX/Y). Ex.: 1920x1080")
    ap.add_argument("--margin-v", type=int, default=60)
    ap.add_argument("--outline", type=int, default=3)
    ap.add_argument("--shadow", type=int, default=0)
    ap.add_argument("--highlight", default="FFFFFF", help="Cor highlight (RGB hex).")
    ap.add_argument("--base", default="808080", help="Cor base (RGB hex).")
    ap.add_argument("--audio-bg", default="black", help="Background quando input for áudio.")
    ap.add_argument("--audio-fps", type=int, default=30, help="FPS para vídeo gerado a partir de áudio.")
    ap.add_argument("--ffmpeg-crf", type=int, default=18, help="CRF do hardsub (menor=melhor qualidade; default: 18).")
    ap.add_argument("--ffmpeg-preset", default="medium", help="Preset do encode (ultrafast..placebo; default: medium).")

    # cache/state
    ap.add_argument("--state-file", default=None, help="State (cache/resume). Default: output/_state.json")
    ap.add_argument("--force", action="store_true", help="Reprocessa mesmo se cache estiver OK.")
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    whisper_bin = Path(args.whisper_cli).resolve()
    model_path = Path(args.model).resolve()

    if not whisper_bin.exists():
        print(f"ERRO: whisper-cli não existe: {whisper_bin}")
        return 2
    if not model_path.exists():
        print(f"ERRO: model não existe: {model_path}")
        return 2

    if str(input_path) == str(default_input):
        ensure_dir(input_path)
    ensure_dir(output_dir)

    if not input_path.exists():
        print(f"ERRO: input não existe: {input_path}")
        return 2

    try:
        rx, ry = args.res.lower().split("x", 1)
        res = (int(rx), int(ry))
    except Exception:
        res = (1920, 1080)

    state_file = Path(args.state_file) if args.state_file else (output_dir / "_state.json")
    state = load_state(state_file)

    glossary_map: Dict[str, str] = load_glossary(Path(args.glossary)) if args.glossary else {}

    # Criar style_config baseado no preset CapCut
    style_config: Optional[CapcutStyleConfig] = None
    if args.capcut_style:
        all_presets = CapcutPresets.get_all_presets()
        if args.capcut_style in all_presets:
            style_config = all_presets[args.capcut_style]
            print(f"✨ Usando estilo CapCut: {args.capcut_style}")
        else:
            print(f"⚠️  Estilo '{args.capcut_style}' não encontrado, usando legacy")

    # Overrides de CapCut (tamanho/caps) e adaptação para resolução
    if style_config:
        base_font_size = style_config.font_size
        base_max_chars = style_config.max_chars_per_line
        if args.capcut_font_size:
            style_config.font_size = args.capcut_font_size
        if args.capcut_uppercase == "on":
            style_config.all_caps = True
        elif args.capcut_uppercase == "off":
            style_config.all_caps = False
        # ajustar max_chars_per_line conforme largura (PlayResX) e font override
        if base_max_chars and res:
            scale_w = max(0.5, res[0] / 1920.0)
            scale_font = base_font_size / style_config.font_size if style_config.font_size else 1.0
            style_config.max_chars_per_line = max(10, int(round(base_max_chars * scale_w * scale_font)))

    def karaoke_engine_effective() -> str:
        eng = args.karaoke_engine
        if eng == "auto":
            eng = "whisperx" if (args.whisperx_cli or args.whisperx_docker_image) else "approx"
        return eng

    polish_params = {
        "max_cps": args.max_cps,
        "max_chars_per_line": args.max_chars_per_line,
        "max_lines": args.max_lines,
        "min_dur_ms": args.min_dur_ms,
        "max_dur_ms": args.max_dur_ms,
        "merge_gap_ms": args.merge_gap_ms,
    }

    opt_fp = options_fingerprint({
        # whisper.cpp
        "model": str(model_path),
        "language": args.language,
        "threads": args.threads,
        "max_line_len": args.max_line_len,
        "prompt": args.prompt,
        "whisper_extra_args": args.whisper_extra_args.strip(),
        "audio_filter": args.audio_filter,
        "chunk_seconds": args.chunk_seconds,
        "polish": args.polish,
        "polish_params": polish_params,
        "redact_pii": args.redact_pii,
        "glossary_items": len(glossary_map),
        "vtt": args.vtt,
        # karaoke
        "karaoke": args.karaoke,
        "karaoke_engine": args.karaoke_engine,
        "whisperx_cli": args.whisperx_cli,
        "whisperx_model": args.whisperx_model,
        "diarize": args.diarize,
        "speaker_prefix": args.speaker_prefix,
        "capcut_style": args.capcut_style,
        "ass_style": {
            "font": args.font,
            "font_size": args.font_size,
            "res": args.res,
            "margin_v": args.margin_v,
            "outline": args.outline,
            "shadow": args.shadow,
            "highlight": args.highlight,
            "base": args.base,
            "audio_bg": args.audio_bg,
            "audio_fps": args.audio_fps,
        },
    })

    run_log = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    run_log.write_text("", encoding="utf-8")

    extra_args = args.whisper_extra_args.strip().split() if args.whisper_extra_args.strip() else []

    def outputs_exist(stem: str) -> bool:
        req = [
            output_dir / f"{stem}.srt",
            output_dir / f"{stem}.plain.txt",
            output_dir / f"{stem}.transcript.timestamps.txt",
            output_dir / f"{stem}.segments.json",
            output_dir / f"{stem}.whispercpp.txt",
        ]
        if args.karaoke:
            req += [output_dir / f"{stem}.karaoke.ass", output_dir / f"{stem}.karaoke.mp4"]
        return all(p.exists() for p in req)

    def should_skip(p: Path) -> bool:
        if args.force:
            return False
        key = str(p.resolve())
        item = state.get("items", {}).get(key)
        if not item:
            return False
        if item.get("opt_fp") != opt_fp:
            return False
        sig = file_sig(p)
        if item.get("size") != sig["size"] or item.get("mtime") != sig["mtime"]:
            return False
        return item.get("status") == "ok" and outputs_exist(p.stem)

    def mark_state(p: Path, status: str, err: Optional[str]) -> None:
        key = str(p.resolve())
        sig = file_sig(p)
        sha = sha256_file(p)
        state.setdefault("items", {})
        state["items"][key] = {
            "status": status,
            "size": sig["size"],
            "mtime": sig["mtime"],
            "sha256": sha,
            "opt_fp": opt_fp,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": err,
        }
        save_state(state_file, state)

    def do_karaoke(
        media: Path,
        stem: str,
        base_segments: List[SrtSegment],
        audio_stream: Optional[int],
        auto_audio_stream: bool,
        audio_filter: Optional[str],
        style_config: Optional[CapcutStyleConfig] = None,
    ) -> None:
        out_ass = output_dir / f"{stem}.karaoke.ass"
        out_vid = output_dir / f"{stem}.karaoke.mp4"
        out_wx_json = output_dir / f"{stem}.whisperx.json"

        engine = args.karaoke_engine
        if engine == "auto":
            engine = "whisperx" if (args.whisperx_cli or args.whisperx_docker_image) else "approx"

        if args.diarize and engine != "whisperx":
            raise RuntimeError("Diarize exige engine WhisperX (local ou Docker). Selecione whisperx e informe o caminho/imagem.")

        if engine == "whisperx" and not args.whisperx_cli and not args.whisperx_docker_image:
            if args.diarize:
                raise RuntimeError("Diarize: informe --whisperx-cli ou --whisperx-docker-image.")
            print("Aviso: karaoke-engine=whisperx sem whisperx-cli/docker => usando approx.")
            engine = "approx"

        if engine == "whisperx":
            if args.diarize and not os.environ.get(args.hf_token_env):
                raise RuntimeError(f"Diarize requer token HF em {args.hf_token_env} (ex.: setx {args.hf_token_env} SEU_TOKEN).")
            # usa a mesma trilha de áudio que o whisper.cpp para evitar dessync
            chosen_stream = audio_stream
            if chosen_stream is None and auto_audio_stream:
                chosen_stream = detect_best_audio_stream(args.ffmpeg, media)
            with tempfile.TemporaryDirectory(prefix="whisperx_out_") as td:
                td_path = Path(td)
                wav_wx = td_path / f"{stem}_wx.wav"
                ffmpeg_extract_wav(args.ffmpeg, media, wav_wx, audio_filter, chosen_stream)

                if args.whisperx_cli:
                    wx_json = run_whisperx_to_json_local(
                        whisperx_exe=args.whisperx_cli,
                        media_path=wav_wx,
                        out_dir=td_path,
                        model=args.whisperx_model,
                        language=args.language,
                        diarize=args.diarize,
                        hf_token_env=args.hf_token_env,
                    )
                else:
                    wx_json = run_whisperx_to_json_docker(
                        docker_bin=args.docker,
                        image=args.whisperx_docker_image,
                        media_path=wav_wx,
                        out_dir=td_path,
                        model=args.whisperx_model,
                        language=args.language,
                        diarize=args.diarize,
                        hf_token_env=args.hf_token_env,
                        cache_dir=Path(args.whisperx_cache_dir) if args.whisperx_cache_dir else None,
                    )
                out_wx_json.write_text(wx_json.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            ksegs = load_whisperx_json_words(out_wx_json)
            if not ksegs:
                raise RuntimeError("WhisperX não trouxe words suficientes no JSON.")
        else:
            # approx: usa segments do whisper.cpp
            ksegs = build_karaoke_from_srt_approx(base_segments)

        write_ass_karaoke(
            ksegs,
            out_ass,
            font=args.font,
            font_size=args.font_size,
            res=res,
            margin_v=args.margin_v,
            outline=args.outline,
            shadow=args.shadow,
            highlight_rgb=args.highlight,
            base_rgb=args.base,
            use_speaker_prefix=args.speaker_prefix,
            style_config=style_config,
        )

        burn_ass_to_video(
            ffmpeg_bin=args.ffmpeg,
            input_media=media,
            ass_path=out_ass,
            output_video=out_vid,
            audio_only_bg=args.audio_bg,
            audio_only_res=res,
            audio_only_fps=args.audio_fps,
            ffmpeg_crf=args.ffmpeg_crf,
            ffmpeg_preset=args.ffmpeg_preset,
        )

    def process_batch(files: List[Path]) -> Tuple[int, int]:
        ok = 0
        fail = 0
        def w(msg: str) -> None:
            safe = msg.encode("cp1252", errors="replace").decode("cp1252", errors="replace")
            tqdm.write(safe)
        for f in tqdm(files, desc="Processando", unit="arquivo"):
            w(f"\nProcessando: {f}")
            if should_skip(f):
                w("Pulando (cache OK)")
                continue
            try:
                segs, _ = transcribe_one_whispercpp(
                    input_media=f,
                    output_dir=output_dir,
                    ffmpeg_bin=args.ffmpeg,
                    whisper_bin=whisper_bin,
                    model_path=model_path,
                    language=args.language,
                    max_line_len=args.max_line_len,
                    threads=args.threads,
                    prompt=args.prompt,
                    extra_args=extra_args,
                    keep_wav=args.keep_wav,
                    audio_filter=args.audio_filter,
                    audio_stream=args.audio_stream,
                    auto_audio_stream=args.auto_audio_stream,
                    chunk_seconds=args.chunk_seconds,
                    polish=args.polish,
                    polish_params=polish_params,
                    redact=args.redact_pii,
                    glossary_map=glossary_map,
                    make_vtt=args.vtt,
                    run_log=run_log,
                )

                # sidecar WhisperX (para diarize/words) mesmo sem karaoke
                wx_json_path = output_dir / f"{f.stem}.whisperx.json"
                need_whisperx = args.diarize or (args.karaoke and karaoke_engine_effective() == "whisperx")
                if need_whisperx:
                    if not args.whisperx_cli and not args.whisperx_docker_image:
                        if args.diarize:
                            raise RuntimeError("Diarize requer WhisperX (informe --whisperx-cli ou --whisperx-docker-image).")
                        else:
                            w("Aviso: WhisperX não configurado; pulando sidecar.")
                    else:
                        wx_result = run_whisperx_sidecar(
                            media=f,
                            out_json=wx_json_path,
                            whisperx_cli=args.whisperx_cli,
                            whisperx_docker_image=args.whisperx_docker_image,
                            docker_bin=args.docker,
                            model=args.whisperx_model,
                            language=args.language,
                            diarize=args.diarize,
                            hf_token_env=args.hf_token_env,
                            cache_dir=Path(args.whisperx_cache_dir) if args.whisperx_cache_dir else None,
                        )
                        if wx_result and wx_result.exists():
                            try:
                                ksegs = load_whisperx_json_words(wx_result)
                                srt_wx = whisperx_segments_to_srt_segments(ksegs, speaker_prefix=args.speaker_prefix)
                                if srt_wx:
                                    out_wx_srt = output_dir / f"{f.stem}.whisperx.srt"
                                    write_srt(srt_wx, out_wx_srt)
                                    if args.vtt:
                                        out_wx_vtt = output_dir / f"{f.stem}.whisperx.vtt"
                                        write_vtt(srt_wx, out_wx_vtt)
                            except Exception as err:
                                w(f"Aviso: falha ao gerar SRT do WhisperX: {err}")

                if args.karaoke:
                    do_karaoke(
                        media=f,
                        stem=f.stem,
                        base_segments=segs,
                        audio_stream=args.audio_stream,
                        auto_audio_stream=args.auto_audio_stream,
                        audio_filter=args.audio_filter,
                        style_config=style_config,
                    )

                mark_state(f, "ok", None)
                ok += 1
                w("OK")
            except Exception as e:
                mark_state(f, "fail", str(e))
                fail += 1
                w(f"FALHOU: {e}")
        return ok, fail

    if not args.watch:
        files = collect_files(input_path, recursive=args.recursive)
        if not files:
            print(f"Nenhum arquivo suportado encontrado em: {input_path}")
            return 0
        print(f"Input:  {input_path}")
        print(f"Output: {output_dir}")
        print(f"State:  {state_file}")
        print(f"Log:    {run_log}")
        print(f"Arquivos: {len(files)}")
        ok, fail = process_batch(files)
        print(f"\nFinalizado. Sucesso: {ok} | Falhas: {fail} | Output: {output_dir}")
        return 0 if fail == 0 else 1

    # watch mode
    if input_path.is_file():
        print("ERRO: --watch só faz sentido quando --input é uma pasta.")
        return 2

    print(f"WATCH ON | Input: {input_path} | Output: {output_dir}")
    seen: Dict[str, float] = {}
    while True:
        try:
            files = collect_files(input_path, recursive=args.recursive)
            new: List[Path] = []
            for f in files:
                k = str(f.resolve())
                m = f.stat().st_mtime
                if k not in seen:
                    seen[k] = m
                    continue
                if seen[k] < m:
                    seen[k] = m
                    continue
                if not should_skip(f):
                    new.append(f)

            if new:
                process_batch(new)

            time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\nWATCH OFF (Ctrl+C).")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
