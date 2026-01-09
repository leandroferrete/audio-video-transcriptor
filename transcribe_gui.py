"""
GUI amigavel para Transcritor PRO + Karaoke.
- Presets de 1 clique (texto rapido, karaoke rapido, karaoke qualidade)
- Explicacoes claras e controle de velocidade x qualidade do video
- Barra de progresso (indeterminada) e status vivo
"""

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

BASE_DIR = Path(__file__).resolve().parent


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def search_first(patterns) -> Path | None:
    for pat in patterns:
        for hit in BASE_DIR.rglob(pat):
            return hit
    return None


def detect_default_paths() -> dict:
    inp = BASE_DIR / "input"
    outp = BASE_DIR / "output"
    ensure_dir(inp)
    ensure_dir(outp)

    whisper_cli = search_first(["whisper-cli.exe"])
    model = search_first(["ggml-large-v3.bin", "ggml-medium.bin", "*.gguf", "ggml-base.bin"])

    ffmpeg = None
    for cand in [
        BASE_DIR / "ffmpeg.exe",
        BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe",
        BASE_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]:
        if cand.exists():
            ffmpeg = cand
            break

    # Auto-detectar WhisperX CLI local
    whisperx_cli = None
    for cand in [
        BASE_DIR / "venv_whisperx" / "Scripts" / "whisperx.exe",
        BASE_DIR / ".venv_whisperx" / "Scripts" / "whisperx.exe",
    ]:
        if cand.exists():
            whisperx_cli = cand
            break

    return {
        "input": inp,
        "output": outp,
        "whisper_cli": whisper_cli,
        "model": model,
        "ffmpeg": ffmpeg,
        "whisperx_cli": whisperx_cli,
    }


def default_python_exe() -> str:
    venv = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


QUALITY_PRESETS = {
    "Rapido (crf 23, preset ultrafast)": {"crf": 23, "preset": "ultrafast"},
    "Equilibrado (crf 20, preset fast)": {"crf": 20, "preset": "fast"},
    "Qualidade (crf 18, preset medium)": {"crf": 18, "preset": "medium"},
    "Qualidade alta (crf 16, preset slow)": {"crf": 16, "preset": "slow"},
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None
        self.msg_queue: queue.Queue[str] = queue.Queue()
        self.defaults = detect_default_paths()
        self.last_log_ts = None

        self.root.title("Transcritor PRO + Karaoke - GUI")
        self.root.geometry("1100x780")
        self.build_ui()
        self.poll_queue()

    # ------------- UI -------------
    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=10)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Transcritor PRO + Karaoke", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Escolha entre gerar apenas transcrição (texto) ou vídeo com karaoke. "
                 "Presets de 1 clique e controle de velocidade x qualidade.",
            wraplength=1000,
        ).pack(anchor="w", pady=(2, 0))

        presets = ttk.Frame(self.root, padding=(10, 4))
        presets.grid(row=1, column=0, sticky="ew")
        ttk.Label(presets, text="Presets rápidos:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        btns = ttk.Frame(presets)
        btns.pack(anchor="w", pady=(2, 4))
        ttk.Button(btns, text="1) Texto rápido (sem vídeo)", command=self.preset_text_fast).pack(side="left", padx=4)
        ttk.Button(btns, text="2) Karaoke rápido (approx)", command=self.preset_karaoke_fast).pack(side="left", padx=4)
        ttk.Button(btns, text="3) Karaoke qualidade (WhisperX docker/local)", command=self.preset_karaoke_quality).pack(side="left", padx=4)
        ttk.Label(
            presets,
            text="Dica: WhisperX exige caminho do whisperx-cli ou imagem Docker; se não preencher, use o preset 2 (approx).",
            foreground="#444",
        ).pack(anchor="w")

        body = ttk.Frame(self.root, padding=10)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        # Coluna esquerda: modo/qualidade/explicacao
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="n", padx=(0, 10))

        # Modo
        mode_box = ttk.LabelFrame(left, text="Modo de saída", padding=8)
        mode_box.pack(fill="x", pady=(0, 8))
        self.var_mode = tk.StringVar(value="text_only")
        modes = [
            ("Só transcrição (SRT/TXT/JSON)", "text_only"),
            ("Vídeo karaoke (approx, mais rápido)", "karaoke_approx"),
            ("Vídeo karaoke (WhisperX local)", "karaoke_whisperx_local"),
            ("Vídeo karaoke (WhisperX Docker)", "karaoke_whisperx_docker"),
            ("Custom", "custom"),
        ]
        for text, val in modes:
            ttk.Radiobutton(mode_box, text=text, variable=self.var_mode, value=val, command=self.on_mode_change).pack(anchor="w")
        self.label_mode_hint = ttk.Label(
            mode_box,
            text="Selecione o modo. Approx não precisa WhisperX; WhisperX gera timing por palavra.",
            foreground="#444",
            wraplength=320,
        )
        self.label_mode_hint.pack(anchor="w", pady=(6, 0))

        # Qualidade
        quality_box = ttk.LabelFrame(left, text="Qualidade do vídeo (hardsub)", padding=8)
        quality_box.pack(fill="x", pady=(0, 8))
        self.var_quality = tk.StringVar(value="Qualidade (crf 18, preset medium)")
        ttk.Label(quality_box, text="Quanto menor o crf e mais lento o preset, maior qualidade e tempo.").pack(anchor="w")
        self.combo_quality = ttk.Combobox(quality_box, values=list(QUALITY_PRESETS.keys()), textvariable=self.var_quality, state="readonly")
        self.combo_quality.pack(fill="x", pady=(4, 0))

        # Status + progresso
        status_box = ttk.LabelFrame(left, text="Status e progresso", padding=8)
        status_box.pack(fill="x", pady=(0, 8))
        self.var_status = tk.StringVar(value="Pronto.")
        ttk.Label(status_box, textvariable=self.var_status, foreground="#333", wraplength=320).pack(anchor="w")
        self.progress = ttk.Progressbar(status_box, mode="indeterminate")
        self.progress.pack(fill="x", pady=(6, 0))

        # Botões principais
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(6, 0))
        self.run_btn = ttk.Button(actions, text="Executar (1 clique)", command=self.run_clicked)
        self.run_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.stop_btn = ttk.Button(actions, text="Parar", command=self.stop_clicked, state="disabled")
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Coluna direita: detalhes/config
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right, text="Caminhos principais", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 4))
        row += 1
        self.var_python = tk.StringVar(value=default_python_exe())
        self.var_input = tk.StringVar(value=str(self.defaults["input"]))
        self.var_output = tk.StringVar(value=str(self.defaults["output"]))
        self.var_whisper = tk.StringVar(value=str(self.defaults["whisper_cli"] or ""))
        self.var_model = tk.StringVar(value=str(self.defaults["model"] or ""))
        self.var_ffmpeg = tk.StringVar(value=str(self.defaults["ffmpeg"] or ""))

        self._row_entry(right, row, "Python", self.var_python, btn=lambda: self.pick_file(self.var_python, "python.exe")); row += 1
        self._row_entry(right, row, "Input (arquivo/pasta)", self.var_input, btn=self.pick_input); row += 1
        self._row_entry(right, row, "Output (pasta)", self.var_output, btn=self.pick_output); row += 1
        self._row_entry(right, row, "whisper-cli.exe", self.var_whisper, btn=lambda: self.pick_file(self.var_whisper)); row += 1
        self._row_entry(right, row, "Modelo (ggml/gguf)", self.var_model, btn=lambda: self.pick_file(self.var_model)); row += 1
        self._row_entry(right, row, "FFmpeg", self.var_ffmpeg, btn=lambda: self.pick_file(self.var_ffmpeg)); row += 1

        ttk.Label(right, text="Opções gerais", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 4)); row += 1
        self.var_language = tk.StringVar(value="pt")
        self.var_threads = tk.StringVar(value="8")
        self.var_max_line = tk.StringVar(value="60")
        self.var_prompt = tk.StringVar(value="")
        self.var_extra = tk.StringVar(value="")
        self.var_audio_filter = tk.StringVar(value="")
        self.var_chunk = tk.StringVar(value="0")
        self.var_audio_stream = tk.StringVar(value="")
        self.var_auto_audio_stream = tk.BooleanVar(value=True)
        self.var_watch = tk.BooleanVar(value=False)
        self.var_watch_interval = tk.StringVar(value="2.0")
        self.var_keep_wav = tk.BooleanVar(value=False)
        self.var_vtt = tk.BooleanVar(value=True)
        self.var_polish = tk.BooleanVar(value=False)
        self.var_redact = tk.BooleanVar(value=False)
        self.var_glossary = tk.StringVar(value="")

        self._row_entry(right, row, "Idioma (pt/en)", self.var_language); row += 1
        self._row_entry(right, row, "Threads", self.var_threads); row += 1
        self._row_entry(right, row, "Max line len", self.var_max_line); row += 1
        self._row_entry(right, row, "Prompt", self.var_prompt); row += 1
        self._row_entry(right, row, "Extra args whisper-cli", self.var_extra); row += 1
        self._row_entry(right, row, "Filtro de áudio (ffmpeg)", self.var_audio_filter); row += 1
        self._row_entry(right, row, "Chunk seconds (0=off)", self.var_chunk); row += 1
        self._row_entry(right, row, "Trilha de áudio (0,1,2...)", self.var_audio_stream); row += 1
        ttk.Checkbutton(right, text="Auto escolher trilha (mais longa)", variable=self.var_auto_audio_stream).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0,4)); row += 1
        self._row_entry(right, row, "Glossário (.txt/.json)", self.var_glossary, btn=lambda: self.pick_file(self.var_glossary)); row += 1

        flags = ttk.Frame(right)
        flags.grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 4))
        ttk.Checkbutton(flags, text="Watch", variable=self.var_watch).pack(side="left", padx=(0, 6))
        ttk.Label(flags, text="Intervalo").pack(side="left")
        ttk.Entry(flags, textvariable=self.var_watch_interval, width=6).pack(side="left", padx=(4, 10))
        ttk.Checkbutton(flags, text="Keep WAV", variable=self.var_keep_wav).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(flags, text="Gerar .vtt", variable=self.var_vtt).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(flags, text="Polish SRT", variable=self.var_polish).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(flags, text="Redact PII", variable=self.var_redact).pack(side="left")
        row += 1

        ttk.Label(right, text="Karaoke / WhisperX", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 4)); row += 1
        # Auto-preenche o caminho do WhisperX se detectado
        whisperx_default = str(self.defaults.get("whisperx_cli") or "")
        self.var_whisperx_cli = tk.StringVar(value=whisperx_default)
        self.var_whisperx_image = tk.StringVar(value="ghcr.io/jim60105/whisperx:no_model")
        self.var_whisperx_model = tk.StringVar(value="medium")
        self.var_cache_dir = tk.StringVar(value="")
        self.var_hf_env = tk.StringVar(value="HUGGINGFACE_HUB_TOKEN")
        self.var_diarize = tk.BooleanVar(value=False)
        self.var_speaker_prefix = tk.BooleanVar(value=False)

        self._row_entry(right, row, "WhisperX CLI (local)", self.var_whisperx_cli, btn=lambda: self.pick_file(self.var_whisperx_cli)); row += 1
        self._row_entry(right, row, "WhisperX Docker image", self.var_whisperx_image); row += 1
        self._row_entry(right, row, "WhisperX model", self.var_whisperx_model); row += 1
        self._row_entry(right, row, "Cache dir (/root/.cache)", self.var_cache_dir, btn=self.pick_cache_dir); row += 1
        self._row_entry(right, row, "HF token env (diarize)", self.var_hf_env); row += 1

        flags2 = ttk.Frame(right)
        flags2.grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 4))
        ttk.Checkbutton(flags2, text="Diarize (WhisperX)", variable=self.var_diarize).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(flags2, text="Speaker prefix no ASS", variable=self.var_speaker_prefix).pack(side="left", padx=(0, 6))
        row += 1

        # Estilo CapCut/Viral
        ttk.Label(right, text="Estilo de Legenda (CapCut/TikTok/Viral)", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 4)); row += 1
        
        self.var_capcut_style = tk.StringVar(value="viral_karaoke")
        self.var_capcut_case = tk.StringVar(value="auto")  # auto/on/off
        self.var_capcut_font_size = tk.StringVar(value="")  # vazio = padrão do preset
        capcut_styles = [
            ("Padrão Viral (karaokê) - Amarelo, Pop, ALL CAPS", "viral_karaoke"),
            ("Viral Flat (CAPS, sem animação) - Amarelo sólido", "viral_flat"),
            ("Clean Premium (podcast) - Minimalista, caixa preta", "clean_premium"),
            ("Tutorial Tech - Ciano, Oswald, Scale-in", "tutorial_tech"),
            ("Storytime/Fofoca - Poppins, caixa branca, Shake", "storytime_fofoca"),
            ("Motivacional - Dourado, Glow, gradiente", "motivacional"),
            ("Terror/True Crime - Vermelho, condensado, glitch", "terror_true_crime"),
            ("Desativado (usar estilo simples/legacy)", "none"),
        ]
        
        style_label = ttk.Label(right, text="Preset de Estilo:")
        style_label.grid(row=row, column=0, sticky="w")
        style_combo = ttk.Combobox(right, textvariable=self.var_capcut_style, values=[s[1] for s in capcut_styles], state="readonly", width=22)
        style_combo.grid(row=row, column=1, sticky="ew", columnspan=2, padx=(6, 0))
        style_help_btn = ttk.Button(right, text="?", width=3, command=self.show_style_help)
        style_help_btn.grid(row=row, column=3, sticky="w", padx=(4, 0))
        row += 1

        # Controle de caixa (CAPS) e tamanho
        ttk.Label(right, text="Caixa (auto/CAPS/original):").grid(row=row, column=0, sticky="w")
        case_combo = ttk.Combobox(right, textvariable=self.var_capcut_case, state="readonly",
                                  values=["auto", "on", "off"], width=22)
        case_combo.grid(row=row, column=1, sticky="ew", padx=(6, 0))
        case_combo.bind("<<ComboboxSelected>>", lambda e: self._normalize_case_var())
        ttk.Label(right, text="Fonte (vazio = padrão):").grid(row=row, column=2, sticky="e", padx=(6, 4))
        ttk.Entry(right, textvariable=self.var_capcut_font_size, width=10).grid(row=row, column=3, sticky="w")
        row += 1
        self._normalize_case_var()
        
        # Descrição do estilo selecionado
        self.style_desc_label = ttk.Label(right, text=self.get_style_description("viral_karaoke"), foreground="#444", wraplength=450, justify="left")
        self.style_desc_label.grid(row=row, column=0, columnspan=4, sticky="w", pady=(2, 4))
        row += 1
        
        # Atualizar descrição quando mudar seleção
        style_combo.bind("<<ComboboxSelected>>", lambda e: self.update_style_description())

        # Log
        log_box = ttk.LabelFrame(self.root, text="Log", padding=8)
        log_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_box.columnconfigure(0, weight=1)
        log_box.rowconfigure(1, weight=1)
        ttk.Label(log_box, text="Mostra a saída do processo (ffmpeg/whisper).").grid(row=0, column=0, sticky="w")
        self.log_text = tk.Text(log_box, height=12, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.cmd_label = ttk.Label(log_box, text="", foreground="#555", wraplength=1000)
        self.cmd_label.grid(row=2, column=0, sticky="w", pady=(6, 0))

        # Help / explicações
        help_box = ttk.LabelFrame(self.root, text="O que cada opção faz", padding=8)
        help_box.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        help_text = (
            "- Modo: 'Só transcrição' gera SRT/VTT/TXT/JSON. Karaoke gera vídeo hardsub.\n"
            "- Trilha de áudio: escolha 0/1/2... se houver múltiplas; deixe auto se só uma.\n"
            "- Polish: melhora legibilidade (quebra blocos longos, limita cps). Deixe off se quiser bruto.\n"
            "- Qualidade vídeo: crf/preset (menor crf = mais qualidade; preset mais lento = melhor).\n"
            "- Karaoke engine: approx (rápido, sem WhisperX) ou WhisperX (timing por palavra). Diarize só funciona com WhisperX + token.\n"
            "- WhisperX diarize: precisa token HF em HUGGINGFACE_HUB_TOKEN (ou o env que você setar) e caminho do whisperx-cli (ou imagem Docker).\n"
            "- Watch: monitora a pasta e processa novos arquivos; Keep WAV salva o WAV intermediário.\n"
            "- Glossário/Redact: substitui termos ou remove PII (email/tel/cpf/cnpj).\n"
            "- Caps/tamanho (CapCut): escolha auto/on/off para CAPSLOCK; fonte vazia usa o tamanho ideal do preset e adapta à largura."
        )
        ttk.Label(help_box, text=help_text, wraplength=1000, justify="left").pack(anchor="w")

        self.on_mode_change()

    def _row_entry(self, parent, row, label, var, btn=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        e = ttk.Entry(parent, textvariable=var, width=60)
        e.grid(row=row, column=1, sticky="ew", pady=2)
        if btn:
            ttk.Button(parent, text="...", width=4, command=btn).grid(row=row, column=2, sticky="w", padx=(4, 0))

    # ------------- pickers -------------
    def pick_file(self, var: tk.StringVar, title: str | None = None):
        p = filedialog.askopenfilename(title=title or "Escolher arquivo")
        if p:
            var.set(p)

    def pick_input(self):
        pfile = filedialog.askopenfilename()
        if pfile:
            self.var_input.set(pfile)
            return
        pdir = filedialog.askdirectory()
        if pdir:
            self.var_input.set(pdir)

    def pick_output(self):
        p = filedialog.askdirectory()
        if p:
            self.var_output.set(p)

    def pick_cache_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.var_cache_dir.set(p)

    # ------------- estilos CapCut -------------
    def get_style_description(self, style_name: str) -> str:
        """Retorna descrição do estilo selecionado."""
        descriptions = {
            "viral_karaoke": "🔥 VIRAL: Branco→Amarelo, POP bounce, ALL CAPS, stroke preto. O mais usado em Reels/TikTok/Shorts.",
            "viral_flat": "🟡 VIRAL FLAT: Amarelo sólido, sem animação, Montserrat ALL CAPS, stroke preto discreto.",
            "clean_premium": "✨ PREMIUM: Minimalista, caixa preta arredondada, Inter, ideal para podcasts/entrevistas.",
            "tutorial_tech": "💻 TECH: Oswald condensada, ciano destaque, scale-in, perfeito para tutoriais/explicações.",
            "storytime_fofoca": "🗣️ STORYTIME: Poppins bold, caixa branca, shake em palavras-chave, ideal para histórias/fofocas.",
            "motivacional": "💪 MOTIVACIONAL: Montserrat, dourado com glow, gradiente laranja, inspirador.",
            "terror_true_crime": "🔪 TERROR: Oswald, vermelho sangue, shake/glitch, caixa preta, suspense/true crime.",
            "none": "❌ Desativado: Usa estilo legacy simples (sem animações avançadas)."
        }
        return descriptions.get(style_name, "Estilo personalizado")
    
    def update_style_description(self):
        """Atualiza a descrição quando mudar estilo."""
        style = self.var_capcut_style.get()
        desc = self.get_style_description(style)
        self.style_desc_label.config(text=desc)
    
    def show_style_help(self):
        """Mostra janela com explicação detalhada dos estilos."""
        help_text = """ESTILOS DE LEGENDA CAPCUT/TIKTOK/VIRAL

🔥 Padrão Viral (karaokê):
- O mais usado em Reels/TikTok/Shorts
- Branco → Amarelo quando ativo
- Animação POP/Bounce micro
- ALL CAPS, stroke preto grosso
- Montserrat Bold

🟡 Viral Flat (sem animação):
- Mesmo visual do viral, sem animação
- Amarelo sólido no destaque
- ALL CAPS, Montserrat
- Stroke preto discreto e caixa leve

✨ Clean Premium:
- Minimalista profissional
- Caixa preta arredondada translúcida
- Fonte Inter, sem ALL CAPS
- Ideal para podcasts, entrevistas
- Fade suave

💻 Tutorial Tech:
- Oswald condensada
- Destaque ciano (palavras-chave)
- Scale-in (cresce de pequeno)
- Perfeito para tutoriais/tech

🗣️ Storytime/Fofoca:
- Poppins bold arredondada
- Caixa BRANCA com texto preto
- Shake em palavras de ênfase
- Estilo "fofoca viral"

💪 Motivacional:
- Dourado com glow/brilho
- Gradiente (dourado→laranja)
- Montserrat, ALL CAPS
- Scale + pulse
- Inspirador/energia

🔪 Terror/True Crime:
- Vermelho sangue (#FF0000)
- Shake/glitch em palavras-chave
- Oswald condensada
- Caixa preta, suspense

Cada estilo inclui:
- Fonte customizada
- Cores específicas
- Animações (pop, bounce, scale, shake, glow)
- Timing palavra-por-palavra
- ALL CAPS ou Title Case
- Letter spacing ajustado
"""
        messagebox.showinfo("Estilos CapCut/TikTok", help_text)

    def _normalize_case_var(self):
        """Normaliza valor do combo de caixa (auto/on/off)."""
        v = (self.var_capcut_case.get() or "").lower()
        if v.startswith("on"):
            self.var_capcut_case.set("on")
        elif v.startswith("off"):
            self.var_capcut_case.set("off")
        else:
            self.var_capcut_case.set("auto")

    # ------------- presets -------------
    def preset_text_fast(self):
        self.var_mode.set("text_only")
        self.var_quality.set("Rapido (crf 23, preset ultrafast)")
        self.run_clicked()

    def preset_karaoke_fast(self):
        self.var_mode.set("karaoke_approx")
        self.var_quality.set("Rapido (crf 23, preset ultrafast)")
        self.run_clicked()

    def preset_karaoke_quality(self):
        # Usa WhisperX local se disponível, senão Docker
        if self.defaults.get("whisperx_cli"):
            self.var_mode.set("karaoke_whisperx_local")
        else:
            self.var_mode.set("karaoke_whisperx_docker")
        self.var_quality.set("Qualidade (crf 18, preset medium)")
        self.run_clicked()

    # ------------- mode helpers -------------
    def is_karaoke_mode(self) -> bool:
        return self.var_mode.get() in {"karaoke_approx", "karaoke_whisperx_local", "karaoke_whisperx_docker", "custom"}

    def karaoke_engine(self) -> str:
        m = self.var_mode.get()
        if m == "karaoke_approx":
            return "approx"
        if m == "karaoke_whisperx_local":
            return "whisperx_local"
        if m == "karaoke_whisperx_docker":
            return "whisperx_docker"
        return "auto"

    def on_mode_change(self):
        m = self.var_mode.get()
        if m == "text_only":
            self.label_mode_hint.config(text="Gera apenas textos (SRT/VTT/TXT/JSON). Não gera vídeo.")
        elif m == "karaoke_approx":
            self.label_mode_hint.config(text="Vídeo karaoke aproximado (rápido, sem WhisperX).")
        elif m == "karaoke_whisperx_local":
            self.label_mode_hint.config(text="Vídeo karaoke com timing por palavra usando WhisperX instalado localmente.")
        elif m == "karaoke_whisperx_docker":
            self.label_mode_hint.config(text="Vídeo karaoke com WhisperX via Docker (precisa imagem e, idealmente, GPU).")
        else:
            self.label_mode_hint.config(text="Custom: use os campos abaixo conforme necessário.")

    # ------------- cmd build -------------
    def build_cmd(self) -> list[str]:
        input_path = Path(self.var_input.get())
        output_path = Path(self.var_output.get())
        ensure_dir(output_path)

        python_exe = self.var_python.get().strip() or "python"
        script = BASE_DIR / "transcribe_pro_karaoke_docker.py"

        cmd: list[str] = [python_exe, str(script), "--input", str(input_path), "--output", str(output_path)]

        # basicos
        if self.var_whisper.get().strip():
            cmd += ["--whisper-cli", self.var_whisper.get().strip()]
        if self.var_model.get().strip():
            cmd += ["--model", self.var_model.get().strip()]
        if self.var_ffmpeg.get().strip():
            cmd += ["--ffmpeg", self.var_ffmpeg.get().strip()]
        if self.var_language.get().strip():
            cmd += ["--language", self.var_language.get().strip()]
        if self.var_threads.get().strip():
            cmd += ["--threads", self.var_threads.get().strip()]
        if self.var_max_line.get().strip():
            cmd += ["--max-line-len", self.var_max_line.get().strip()]
        if self.var_prompt.get().strip():
            cmd += ["--prompt", self.var_prompt.get().strip()]
        if self.var_extra.get().strip():
            cmd += ["--whisper-extra-args", self.var_extra.get().strip()]
        if self.var_audio_filter.get().strip():
            cmd += ["--audio-filter", self.var_audio_filter.get().strip()]
        if self.var_chunk.get().strip():
            cmd += ["--chunk-seconds", self.var_chunk.get().strip()]
        if self.var_audio_stream.get().strip():
            cmd += ["--audio-stream", self.var_audio_stream.get().strip()]
        if not self.var_auto_audio_stream.get():
            cmd.append("--no-auto-audio-stream")
        if self.var_watch.get():
            cmd.append("--watch")
            cmd += ["--watch-interval", self.var_watch_interval.get()]
        cmd.append("--recursive")
        if self.var_keep_wav.get():
            cmd.append("--keep-wav")
        if self.var_vtt.get():
            cmd.append("--vtt")
        if self.var_polish.get():
            cmd.append("--polish")
        if self.var_redact.get():
            cmd.append("--redact-pii")
        if self.var_glossary.get().strip():
            cmd += ["--glossary", self.var_glossary.get().strip()]

        # qualidade video
        qname = self.var_quality.get()
        q = QUALITY_PRESETS.get(qname, QUALITY_PRESETS["Qualidade (crf 18, preset medium)"])
        cmd += ["--ffmpeg-crf", str(q["crf"]), "--ffmpeg-preset", q["preset"]]

        # karaoke ou só texto
        if self.is_karaoke_mode():
            cmd.append("--karaoke")
            engine = self.karaoke_engine()
            if engine == "approx":
                cmd += ["--karaoke-engine", "approx"]
            elif engine == "whisperx_local":
                cmd += ["--karaoke-engine", "whisperx"]
                if self.var_whisperx_cli.get().strip():
                    cmd += ["--whisperx-cli", self.var_whisperx_cli.get().strip()]
            elif engine == "whisperx_docker":
                cmd += ["--karaoke-engine", "whisperx"]
                if self.var_whisperx_image.get().strip():
                    cmd += ["--whisperx-docker-image", self.var_whisperx_image.get().strip()]
                if self.var_cache_dir.get().strip():
                    cmd += ["--whisperx-cache-dir", self.var_cache_dir.get().strip()]
            else:
                cmd += ["--karaoke-engine", "auto"]
                if self.var_whisperx_cli.get().strip():
                    cmd += ["--whisperx-cli", self.var_whisperx_cli.get().strip()]
                if self.var_whisperx_image.get().strip():
                    cmd += ["--whisperx-docker-image", self.var_whisperx_image.get().strip()]
                if self.var_cache_dir.get().strip():
                    cmd += ["--whisperx-cache-dir", self.var_cache_dir.get().strip()]
            if self.var_whisperx_model.get().strip():
                cmd += ["--whisperx-model", self.var_whisperx_model.get().strip()]
            if self.var_hf_env.get().strip():
                cmd += ["--hf-token-env", self.var_hf_env.get().strip()]
            if self.var_diarize.get():
                cmd.append("--diarize")
            if self.var_speaker_prefix.get():
                cmd.append("--speaker-prefix")
            
            # Estilo CapCut
            style = self.var_capcut_style.get()
            if style and style != "none":
                cmd += ["--capcut-style", style]
                case_val = (self.var_capcut_case.get() or "").lower()
                if case_val in ("on", "off"):
                    cmd += ["--capcut-uppercase", case_val]
                fs = self.var_capcut_font_size.get().strip()
                if fs.isdigit():
                    cmd += ["--capcut-font-size", fs]
        # else: não passa --karaoke (gera só textos)

        return cmd

    # ------------- run/stop -------------
    def run_clicked(self) -> None:
        if self.proc:
            messagebox.showinfo("Em execução", "Já existe uma execução em andamento.")
            return
        cmd = self.build_cmd()
        self.append_log("Executando...\n" + " ".join(cmd))
        self.cmd_label.config(text="Cmd: " + " ".join(cmd))
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError as e:
            messagebox.showerror("Erro", f"Não consegui iniciar o comando: {e}")
            self.proc = None
            return
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.start(10)
        self.reader_thread = threading.Thread(target=self.read_output, daemon=True)
        self.reader_thread.start()
        self.var_status.set("Rodando... aguarde. Veja o log abaixo.")

    def stop_clicked(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.append_log("Parada solicitada (terminate).")

    def read_output(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.msg_queue.put(line.rstrip("\n"))
        rc = self.proc.wait()
        self.msg_queue.put(f"[Processo finalizado] returncode={rc}")
        self.proc = None

    def poll_queue(self) -> None:
        try:
            while True:
                line = self.msg_queue.get_nowait()
                self.append_log(line)
        except queue.Empty:
            pass
        self.update_status()
        self.root.after(300, self.poll_queue)

    def append_log(self, text: str) -> None:
        self.last_log_ts = time.time()
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def update_status(self):
        running = self.proc is not None and self.proc.poll() is None
        if running:
            self.run_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            if not self.progress["mode"] == "indeterminate":
                self.progress.config(mode="indeterminate")
            if not self.progress["value"]:
                self.progress.start(10)
            msg = "Rodando..."
            if self.last_log_ts:
                idle = time.time() - self.last_log_ts
                msg += f" (último log há {int(idle)}s)"
            self.var_status.set(msg)
        else:
            self.progress.stop()
            self.run_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            if self.last_log_ts:
                msg = "Finalizado. Veja o log e o output."
            else:
                msg = "Pronto."
            self.var_status.set(msg)


def main() -> None:
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
