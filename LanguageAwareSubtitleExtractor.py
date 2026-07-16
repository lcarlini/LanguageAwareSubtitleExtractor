#!/usr/bin/env python3
"""Language-aware, resilient media transcription with automatic setup.

Implemented by Computer Engineer Leandro Carlini Mingorance.
Reach out: https://lcarlini.github.io/lcarlini/
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


APP_NAME = "LanguageAwareSubtitleExtractor"
MIN_PYTHON = (3, 9)
DEFAULT_MODEL_NAME = "small"
CHUNK_SECONDS = 20 * 60
POLL_SECONDS = 3
STABLE_CHECKS_REQUIRED = 2
FFMPEG_INACTIVITY_TIMEOUT = 180
DENOISE_FILTER = "afftdn=nr=15:nf=-30,highpass=f=200,lowpass=f=3000"

DEPENDENCIES = {
    "av": "av",
    "colorama": "colorama",
    "faster_whisper": "faster-whisper",
    "imageio_ffmpeg": "imageio-ffmpeg",
    "tqdm": "tqdm",
    "nvidia.cublas": "nvidia-cublas-cu12",
    "nvidia.cudnn": "nvidia-cudnn-cu12",
    "nvidia.cuda_nvrtc": "nvidia-cuda-nvrtc-cu12",
}

LANGUAGE_METADATA_ALIASES = {
    "zh": {"chi"},
    "fr": {"fre"},
    "de": {"ger"},
}

LANGUAGES = [
    ("en", "eng", "English", "Inglês", "Inglés"),
    ("zh", "zho", "Mandarin Chinese", "Chinês mandarim", "Chino mandarín"),
    ("hi", "hin", "Hindi", "Hindi", "Hindi"),
    ("es", "spa", "Spanish", "Espanhol", "Español"),
    ("fr", "fra", "French", "Francês", "Francés"),
    ("ar", "ara", "Arabic", "Árabe", "Árabe"),
    ("bn", "ben", "Bengali", "Bengali", "Bengalí"),
    ("pt", "por", "Portuguese", "Português", "Portugués"),
    ("ru", "rus", "Russian", "Russo", "Ruso"),
    ("ur", "urd", "Urdu", "Urdu", "Urdu"),
    ("id", "ind", "Indonesian", "Indonésio", "Indonesio"),
    ("de", "deu", "German", "Alemão", "Alemán"),
    ("ja", "jpn", "Japanese", "Japonês", "Japonés"),
    ("pa", "pan", "Punjabi", "Punjabi", "Punyabí"),
    ("mr", "mar", "Marathi", "Marathi", "Maratí"),
    ("te", "tel", "Telugu", "Telugu", "Telugu"),
    ("tr", "tur", "Turkish", "Turco", "Turco"),
    ("ta", "tam", "Tamil", "Tâmil", "Tamil"),
    ("vi", "vie", "Vietnamese", "Vietnamita", "Vietnamita"),
    ("ko", "kor", "Korean", "Coreano", "Coreano"),
]

UI_NAMES = {"en": "English", "pt": "Português", "es": "Español"}
LANGUAGE_NAME_COLUMN = {"en": 2, "pt": 3, "es": 4}

MESSAGES = {
    "en": {
        "checking": "🔎 Checking required components...",
        "installing": "⬇️  Installing missing packages: {items}",
        "install_failed": "❌ Install failed. Run:\n{command}",
        "ready": "✅ Ready",
        "folders": "📂 Workspace: {path}",
        "menu_title": "MAIN MENU",
        "menu_start": "▶️  Start monitoring",
        "menu_ui": "🌐 Change menu language",
        "menu_audio": "🗣️  Change audio language",
        "menu_noise": "🎧 Toggle noise reduction",
        "menu_exit": "🚪 Exit",
        "current": "📌 Menu: {ui}  ·  Audio: {audio}  ·  Noise: {noise}",
        "noise_on": "ON",
        "noise_off": "OFF",
        "noise_enabled": "🎧 Noise reduction: ON",
        "noise_disabled": "🎧 Noise reduction: OFF",
        "choose": "➜  ",
        "invalid": "⚠️  Invalid option.",
        "choose_ui": "🌐 Select menu language",
        "choose_audio": "🗣️  Select original spoken language",
        "saved": "💾 Saved",
        "monitoring": "👀 Watching: {path}",
        "drop_files": "📥 Drop media here · Ctrl+C returns to menu",
        "waiting_stable": "⏳ Waiting for copy to finish: {name}",
        "waiting_next": "💤 Waiting for the next file...",
        "detected": "🎬 Processing: {name}",
        "loading_model": "🧠 Loading AI model '{model}'...",
        "model_preparing": "🧠 Preparing '{model}' · first use may download it · still working",
        "device": "⚙️  Device: {device}",
        "gpu_detected": "🚀 GPU ready: {name} ({vram})",
        "gpu_compute": "🧮 GPU compute: {compute}",
        "gpu_trying": "🧪 Trying GPU mode: {compute}...",
        "gpu_failed_mode": "⚠️  GPU mode {compute} failed — trying next...",
        "gpu_fallback": "⚠️  All GPU modes failed — CPU only (reason: {reason})",
        "no_gpu": "⚠️  No CUDA GPU detected — using CPU",
        "extracting": "🎧 Extract",
        "transcribing": "🧠 Transcribe",
        "processing": "📊 Progress",
        "no_audio": "❌ No audio stream found.",
        "audio_fallback": "ℹ️  No '{language}' track tag — using first audio track.",
        "audio_selected": "🎯 Audio track: {language}",
        "denoise_active": "🎧 Noise reduction active for this file",
        "complete": "✅ Done → Output/{name}",
        "failed": "❌ Failed: {error}",
        "moved_error": "📁 Moved to Errors/ (see .error.log)",
        "stopped": "↩️  Back to menu",
        "goodbye": "👋 Bye!",
        "python_old": "❌ Need Python {required}+ (now {current})",
        "disk_space": "❌ Low disk space (need ~{needed})",
        "ffmpeg_stalled": "❌ FFmpeg stalled for {seconds}s",
        "unknown_duration": "❌ Could not read media duration.",
        "press_enter": "Press Enter to continue...",
    },
    "pt": {
        "checking": "🔎 Verificando componentes...",
        "installing": "⬇️  Instalando pacotes: {items}",
        "install_failed": "❌ Falha na instalação. Execute:\n{command}",
        "ready": "✅ Pronto",
        "folders": "📂 Pasta: {path}",
        "menu_title": "MENU PRINCIPAL",
        "menu_start": "▶️  Iniciar monitoramento",
        "menu_ui": "🌐 Alterar idioma do menu",
        "menu_audio": "🗣️  Alterar idioma do áudio",
        "menu_noise": "🎧 Alternar redução de ruído",
        "menu_exit": "🚪 Sair",
        "current": "📌 Menu: {ui}  ·  Áudio: {audio}  ·  Ruído: {noise}",
        "noise_on": "LIGADO",
        "noise_off": "DESLIGADO",
        "noise_enabled": "🎧 Redução de ruído: LIGADA",
        "noise_disabled": "🎧 Redução de ruído: DESLIGADA",
        "choose": "➜  ",
        "invalid": "⚠️  Opção inválida.",
        "choose_ui": "🌐 Selecione o idioma do menu",
        "choose_audio": "🗣️  Selecione o idioma falado",
        "saved": "💾 Salvo",
        "monitoring": "👀 Monitorando: {path}",
        "drop_files": "📥 Coloque mídias aqui · Ctrl+C volta ao menu",
        "waiting_stable": "⏳ Aguardando cópia: {name}",
        "waiting_next": "💤 Aguardando o próximo arquivo...",
        "detected": "🎬 Processando: {name}",
        "loading_model": "🧠 Carregando modelo IA '{model}'...",
        "model_preparing": "🧠 Preparando '{model}' · o primeiro uso pode baixá-lo · ainda trabalhando",
        "device": "⚙️  Dispositivo: {device}",
        "gpu_detected": "🚀 GPU pronta: {name} ({vram})",
        "gpu_compute": "🧮 Computação GPU: {compute}",
        "gpu_trying": "🧪 Tentando modo GPU: {compute}...",
        "gpu_failed_mode": "⚠️  Modo GPU {compute} falhou — tentando o próximo...",
        "gpu_fallback": "⚠️  Todos os modos GPU falharam — só CPU (motivo: {reason})",
        "no_gpu": "⚠️  Nenhuma GPU CUDA detectada — usando CPU",
        "extracting": "🎧 Extrair",
        "transcribing": "🧠 Transcrever",
        "processing": "📊 Progresso",
        "no_audio": "❌ Nenhuma faixa de áudio.",
        "audio_fallback": "ℹ️  Sem tag '{language}' — usando a primeira faixa.",
        "audio_selected": "🎯 Faixa de áudio: {language}",
        "denoise_active": "🎧 Redução de ruído ativa neste arquivo",
        "complete": "✅ Concluído → Output/{name}",
        "failed": "❌ Falha: {error}",
        "moved_error": "📁 Movido para Errors/ (veja .error.log)",
        "stopped": "↩️  De volta ao menu",
        "goodbye": "👋 Até logo!",
        "python_old": "❌ Precisa de Python {required}+ (atual {current})",
        "disk_space": "❌ Pouco disco (precisa ~{needed})",
        "ffmpeg_stalled": "❌ FFmpeg parado por {seconds}s",
        "unknown_duration": "❌ Não foi possível ler a duração.",
        "press_enter": "Pressione Enter para continuar...",
    },
    "es": {
        "checking": "🔎 Comprobando componentes...",
        "installing": "⬇️  Instalando paquetes: {items}",
        "install_failed": "❌ Falló la instalación. Ejecuta:\n{command}",
        "ready": "✅ Listo",
        "folders": "📂 Carpeta: {path}",
        "menu_title": "MENÚ PRINCIPAL",
        "menu_start": "▶️  Iniciar monitoreo",
        "menu_ui": "🌐 Cambiar idioma del menú",
        "menu_audio": "🗣️  Cambiar idioma del audio",
        "menu_noise": "🎧 Alternar reducción de ruido",
        "menu_exit": "🚪 Salir",
        "current": "📌 Menú: {ui}  ·  Audio: {audio}  ·  Ruido: {noise}",
        "noise_on": "ON",
        "noise_off": "OFF",
        "noise_enabled": "🎧 Reducción de ruido: ON",
        "noise_disabled": "🎧 Reducción de ruido: OFF",
        "choose": "➜  ",
        "invalid": "⚠️  Opción no válida.",
        "choose_ui": "🌐 Selecciona el idioma del menú",
        "choose_audio": "🗣️  Selecciona el idioma hablado",
        "saved": "💾 Guardado",
        "monitoring": "👀 Monitoreando: {path}",
        "drop_files": "📥 Deja archivos aquí · Ctrl+C vuelve al menú",
        "waiting_stable": "⏳ Esperando copia: {name}",
        "waiting_next": "💤 Esperando el siguiente archivo...",
        "detected": "🎬 Procesando: {name}",
        "loading_model": "🧠 Cargando modelo IA '{model}'...",
        "model_preparing": "🧠 Preparando '{model}' · el primer uso puede descargarlo · sigue trabajando",
        "device": "⚙️  Dispositivo: {device}",
        "gpu_detected": "🚀 GPU lista: {name} ({vram})",
        "gpu_compute": "🧮 Cómputo GPU: {compute}",
        "gpu_trying": "🧪 Probando modo GPU: {compute}...",
        "gpu_failed_mode": "⚠️  Modo GPU {compute} falló — probando el siguiente...",
        "gpu_fallback": "⚠️  Todos los modos GPU fallaron — solo CPU (motivo: {reason})",
        "no_gpu": "⚠️  No se detectó GPU CUDA — usando CPU",
        "extracting": "🎧 Extraer",
        "transcribing": "🧠 Transcribir",
        "processing": "📊 Progreso",
        "no_audio": "❌ Sin pista de audio.",
        "audio_fallback": "ℹ️  Sin etiqueta '{language}' — usando la primera pista.",
        "audio_selected": "🎯 Pista de audio: {language}",
        "denoise_active": "🎧 Reducción de ruido activa en este archivo",
        "complete": "✅ Listo → Output/{name}",
        "failed": "❌ Error: {error}",
        "moved_error": "📁 Movido a Errors/ (ver .error.log)",
        "stopped": "↩️  De vuelta al menú",
        "goodbye": "👋 ¡Hasta luego!",
        "python_old": "❌ Se necesita Python {required}+ (ahora {current})",
        "disk_space": "❌ Poco disco (se necesita ~{needed})",
        "ffmpeg_stalled": "❌ FFmpeg sin progreso {seconds}s",
        "unknown_duration": "❌ No se pudo leer la duración.",
        "press_enter": "Pulsa Enter para continuar...",
    },
}


class Theme:
    def __init__(self) -> None:
        colorama = importlib.import_module("colorama")
        colorama.init(autoreset=True)
        self.Fore = colorama.Fore
        self.Style = colorama.Style

    def banner(self, title: str) -> None:
        line = "═" * max(48, len(title) + 8)
        print()
        print(f"{self.Fore.CYAN}{self.Style.BRIGHT}╔{line}╗{self.Style.RESET_ALL}")
        print(
            f"{self.Fore.CYAN}{self.Style.BRIGHT}║  🎬 {title}{self.Style.RESET_ALL}"
            f"{' ' * max(0, len(line) - len(title) - 5)}║"
        )
        print(f"{self.Fore.CYAN}{self.Style.BRIGHT}╚{line}╝{self.Style.RESET_ALL}")

    def info(self, text: str) -> None:
        print(f"{self.Fore.CYAN}{text}{self.Style.RESET_ALL}")

    def ok(self, text: str) -> None:
        print(f"{self.Fore.GREEN}{text}{self.Style.RESET_ALL}")

    def warn(self, text: str) -> None:
        print(f"{self.Fore.YELLOW}{text}{self.Style.RESET_ALL}")

    def error(self, text: str) -> None:
        print(f"{self.Fore.RED}{text}{self.Style.RESET_ALL}")

    def muted(self, text: str) -> None:
        print(f"{self.Fore.WHITE}{self.Style.DIM}{text}{self.Style.RESET_ALL}")


class ActivityIndicator:
    """Display an animated status while a blocking setup operation runs."""

    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, text: str, theme: Theme) -> None:
        self.text = text
        self.theme = theme
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "ActivityIndicator":
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def _animate(self) -> None:
        index = 0
        while not self._stopped.is_set():
            frame = self.FRAMES[index % len(self.FRAMES)]
            print(
                f"\r{self.theme.Fore.MAGENTA}{frame} {self.text}"
                f"{self.theme.Style.RESET_ALL}",
                end="",
                flush=True,
            )
            index += 1
            self._stopped.wait(0.12)

    def __exit__(self, *_: Any) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        print("\r" + (" " * 120) + "\r", end="", flush=True)


def base_directory() -> Path:
    """Use the directory that contains this script as the application root."""
    override = os.environ.get("LASX_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class AppPaths:
    base: Path
    incoming: Path
    output: Path
    processed: Path
    errors: Path
    temporary: Path
    settings: Path

    @classmethod
    def create(cls) -> "AppPaths":
        base = base_directory()
        return cls(
            base=base,
            incoming=base / "To Process",
            output=base / "Output",
            processed=base / "Processed",
            errors=base / "Errors",
            temporary=base / "Temporary",
            settings=base / "settings.json",
        )

    def ensure_directories(self) -> None:
        for directory in (
            self.base,
            self.incoming,
            self.output,
            self.processed,
            self.errors,
            self.temporary,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    ui_language: str = "en"
    audio_language: str = "en"
    noise_reduction: bool = False

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ui = data.get("ui_language", "en")
            audio = data.get("audio_language", "en")
            noise = bool(data.get("noise_reduction", False))
            valid_audio = {language[0] for language in LANGUAGES}
            return cls(
                ui if ui in MESSAGES else "en",
                audio if audio in valid_audio else "en",
                noise,
            )
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "ui_language": self.ui_language,
                    "audio_language": self.audio_language,
                    "noise_reduction": self.noise_reduction,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)


def message(settings: Settings, key: str, **values: Any) -> str:
    return MESSAGES[settings.ui_language][key].format(**values)


def language_record(code: str) -> tuple[str, str, str, str, str]:
    return next(language for language in LANGUAGES if language[0] == code)


def language_name(code: str, ui_language: str) -> str:
    return language_record(code)[LANGUAGE_NAME_COLUMN[ui_language]]


def noise_label(settings: Settings) -> str:
    key = "noise_on" if settings.noise_reduction else "noise_off"
    return message(settings, key)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    warnings.filterwarnings("ignore", message=".*huggingface_hub.*")
    warnings.filterwarnings("ignore", message=".*symlinks.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
    for logger_name in (
        "huggingface_hub",
        "huggingface_hub.utils._http",
        "huggingface_hub.file_download",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


def configure_cuda_dll_paths() -> list[str]:
    """Make pip-installed NVIDIA CUDA DLLs visible to CTranslate2 on Windows."""
    added: list[str] = []
    seen: set[str] = set()
    for entry in map(Path, sys.path):
        nvidia_root = entry / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for package_dir in nvidia_root.iterdir():
            for candidate in (
                package_dir / "bin",
                package_dir / "lib",
                package_dir / "lib" / "x64",
            ):
                key = str(candidate.resolve()) if candidate.exists() else ""
                if not key or key in seen:
                    continue
                if not any(candidate.glob("*.dll")) and not any(candidate.glob("*.so*")):
                    continue
                seen.add(key)
                added.append(key)
                os.environ["PATH"] = key + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(key)
                    except OSError:
                        pass
    return added


def detect_gpus() -> list[dict[str, Any]]:
    """Return NVIDIA GPUs sorted by VRAM (strongest first)."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    gpus: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "vram_mb": float(parts[2]),
                }
            )
        except ValueError:
            continue
    gpus.sort(key=lambda item: (item["vram_mb"], -item["index"]), reverse=True)
    return gpus


def select_model_for_vram(vram_mb: float) -> str:
    if vram_mb >= 12_000:
        return "large-v3"
    if vram_mb >= 6_000:
        return "medium"
    return DEFAULT_MODEL_NAME


def format_vram(vram_mb: float) -> str:
    return f"{vram_mb / 1024:.0f} GB"

def check_python(settings: Settings) -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(map(str, MIN_PYTHON))
        current = ".".join(map(str, sys.version_info[:3]))
        raise RuntimeError(message(settings, "python_old", required=required, current=current))


def ensure_dependencies(settings: Settings, theme: Theme | None = None) -> None:
    printer = theme.info if theme else print
    printer(message(settings, "checking"))
    missing = []
    for module, package in DEPENDENCIES.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)
            continue
        # NVIDIA CUDA wheels can be importable yet still miss the DLL folders.
        if module.startswith("nvidia."):
            found_dll = False
            for entry in map(Path, sys.path):
                package_dir = entry / Path(*module.split("."))
                if any((package_dir / "bin").glob("*.dll")) or any(
                    (package_dir / "lib").glob("*.so*")
                ):
                    found_dll = True
                    break
            if not found_dll and os.name == "nt":
                missing.append(package)
    missing = list(dict.fromkeys(missing))
    if not missing:
        (theme.ok if theme else print)(message(settings, "ready"))
        return

    printer(message(settings, "installing", items=", ".join(missing)))
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=True)

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        *missing,
    ]
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        if sys.prefix == sys.base_prefix:
            user_command = [*command[:4], "--user", *command[4:]]
            try:
                subprocess.run(user_command, check=True)
                command = user_command
            except (OSError, subprocess.CalledProcessError):
                printable = subprocess.list2cmdline(user_command)
                raise RuntimeError(
                    message(settings, "install_failed", command=printable)
                ) from error
        else:
            printable = subprocess.list2cmdline(command)
            raise RuntimeError(
                message(settings, "install_failed", command=printable)
            ) from error

    importlib.invalidate_caches()
    still_missing = [
        module for module in DEPENDENCIES if importlib.util.find_spec(module) is None
    ]
    if still_missing:
        raise RuntimeError(
            message(
                settings,
                "install_failed",
                command=subprocess.list2cmdline(command),
            )
        )
    (theme.ok if theme else print)(message(settings, "ready"))


def load_runtime_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    configure_cuda_dll_paths()
    av = importlib.import_module("av")
    ctranslate2 = importlib.import_module("ctranslate2")
    imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
    tqdm_module = importlib.import_module("tqdm")
    faster_whisper = importlib.import_module("faster_whisper")
    return av, ctranslate2, imageio_ffmpeg, tqdm_module.tqdm, faster_whisper


def choose_from_list(
    settings: Settings,
    title_key: str,
    options: list[tuple[str, str]],
    theme: Theme,
) -> str:
    print()
    theme.info(message(settings, title_key))
    for index, (_, label) in enumerate(options, start=1):
        print(f"  {theme.Fore.CYAN}{index:2}.{theme.Style.RESET_ALL} {label}")
    while True:
        choice = input(f"{theme.Fore.GREEN}{message(settings, 'choose')}{theme.Style.RESET_ALL}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        theme.warn(message(settings, "invalid"))


def choose_ui_language(settings: Settings, paths: AppPaths, theme: Theme) -> None:
    options = [(code, label) for code, label in UI_NAMES.items()]
    settings.ui_language = choose_from_list(settings, "choose_ui", options, theme)
    settings.save(paths.settings)
    theme.ok(message(settings, "saved"))


def choose_audio_language(settings: Settings, paths: AppPaths, theme: Theme) -> None:
    column = LANGUAGE_NAME_COLUMN[settings.ui_language]
    options = [(language[0], language[column]) for language in LANGUAGES]
    settings.audio_language = choose_from_list(settings, "choose_audio", options, theme)
    settings.save(paths.settings)
    theme.ok(message(settings, "saved"))


def toggle_noise_reduction(settings: Settings, paths: AppPaths, theme: Theme) -> None:
    settings.noise_reduction = not settings.noise_reduction
    settings.save(paths.settings)
    key = "noise_enabled" if settings.noise_reduction else "noise_disabled"
    theme.ok(message(settings, key))


def unique_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    stamp = time.strftime("%Y%m%d-%H%M%S")
    counter = 1
    while True:
        candidate = directory / f"{stem}_{stamp}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_safely(source: Path, destination_directory: Path) -> Path:
    destination = unique_path(destination_directory, source.name)
    return Path(shutil.move(str(source), str(destination)))


def media_details(
    av: Any,
    media_path: Path,
    language_codes: tuple[str, str],
) -> tuple[float, int, bool]:
    with av.open(str(media_path), mode="r") as container:
        audio_streams = list(container.streams.audio)
        if not audio_streams:
            raise ValueError("NO_AUDIO")

        normalized_languages = {code.lower() for code in language_codes}
        normalized_languages.update(
            LANGUAGE_METADATA_ALIASES.get(language_codes[0].lower(), set())
        )
        matching = [
            stream
            for stream in audio_streams
            if str(stream.metadata.get("language", "")).lower() in normalized_languages
        ]
        selected = matching[0] if matching else audio_streams[0]

        duration = 0.0
        if container.duration is not None:
            duration = float(container.duration / av.time_base)
        elif selected.duration is not None and selected.time_base is not None:
            duration = float(selected.duration * selected.time_base)

        if duration <= 0:
            raise ValueError("UNKNOWN_DURATION")
        return duration, int(selected.index), bool(matching)


def check_disk_space(paths: AppPaths, chunk_seconds: float, settings: Settings) -> None:
    needed = int(chunk_seconds * 32_000 * 2.5 + 100 * 1024 * 1024)
    if shutil.disk_usage(paths.temporary).free < needed:
        needed_text = f"{needed / (1024 ** 2):.0f} MB"
        raise OSError(message(settings, "disk_space", needed=needed_text))


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def extract_chunk(
    ffmpeg_path: str,
    source: Path,
    output: Path,
    stream_index: int,
    start: float,
    length: float,
    progress: Any,
    settings: Settings,
    denoise: bool,
) -> None:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{length:.3f}",
        "-map",
        f"0:{stream_index}",
        "-vn",
    ]
    if denoise:
        command.extend(["-af", DENOISE_FILTER])
    command.extend(
        [
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-progress",
            "pipe:1",
            "-y",
            str(output),
        ]
    )

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=flags,
    )
    assert process.stdout is not None
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    last_activity = time.monotonic()
    reported = 0.0
    diagnostics: list[str] = []

    try:
        while True:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None:
                    break
                if time.monotonic() - last_activity > FFMPEG_INACTIVITY_TIMEOUT:
                    terminate_process(process)
                    raise TimeoutError(
                        message(
                            settings,
                            "ffmpeg_stalled",
                            seconds=FFMPEG_INACTIVITY_TIMEOUT,
                        )
                    )
                continue

            if line is None:
                break
            last_activity = time.monotonic()
            stripped = line.strip()
            if stripped.startswith("out_time_us="):
                try:
                    current = min(length, int(stripped.split("=", 1)[1]) / 1_000_000)
                    progress.update(max(0.0, current - reported))
                    reported = current
                except ValueError:
                    pass
            elif stripped and "=" not in stripped:
                diagnostics.append(stripped)

        return_code = process.wait()
        if return_code != 0:
            detail = "\n".join(diagnostics[-10:]) or f"FFmpeg exit code {return_code}"
            raise RuntimeError(detail)
        progress.update(max(0.0, length - reported))
    except BaseException:
        terminate_process(process)
        raise
    finally:
        process.stdout.close()


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def unique_output_paths(directory: Path, media_stem: str) -> tuple[Path, Path]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    counter = 0
    while True:
        suffix = "" if counter == 0 else f"_{stamp}_{counter}"
        srt_path = directory / f"{media_stem}{suffix}.srt"
        txt_path = directory / f"{media_stem}{suffix}.txt"
        if not srt_path.exists() and not txt_path.exists():
            return srt_path, txt_path
        counter += 1


class Transcriber:
    def __init__(
        self,
        ctranslate2: Any,
        faster_whisper: Any,
        settings: Settings,
        theme: Theme,
        tqdm: Any,
    ) -> None:
        self._faster_whisper = faster_whisper
        self._ctranslate2 = ctranslate2
        self._settings = settings
        self._theme = theme
        self._tqdm = tqdm
        self.device = "cpu"
        self.device_index = 0
        self.compute_type = "int8"
        self.model_name = DEFAULT_MODEL_NAME
        self.gpu_name = ""
        self.model: Any = None
        self._load_model()

    def _write(self, text: str, level: str = "info") -> None:
        color = {
            "info": self._theme.Fore.CYAN,
            "ok": self._theme.Fore.GREEN,
            "warn": self._theme.Fore.YELLOW,
            "error": self._theme.Fore.RED,
        }[level]
        self._tqdm.write(f"{color}{text}{self._theme.Style.RESET_ALL}")

    def _cuda_compute_candidates(self) -> list[str]:
        try:
            supported = set(self._ctranslate2.get_supported_compute_types("cuda"))
        except Exception:
            supported = {
                "float16",
                "bfloat16",
                "float32",
                "int8_float16",
                "int8_bfloat16",
                "int8",
            }
        # Prefer full-precision GPU modes first. INT8 is unreliable on RTX 50-series.
        preferred = [
            "float16",
            "bfloat16",
            "float32",
            "int8_float16",
            "int8_bfloat16",
            "int8",
        ]
        return [item for item in preferred if item in supported]

    def _create_model(self, device: str, compute_type: str, device_index: int = 0) -> Any:
        status = message(
            self._settings,
            "model_preparing",
            model=self.model_name,
        )
        with ActivityIndicator(status, self._theme):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return self._faster_whisper.WhisperModel(
                    self.model_name,
                    device=device,
                    device_index=device_index,
                    compute_type=compute_type,
                )

    def _load_model(self) -> None:
        gpus = detect_gpus()
        cuda_count = 0
        try:
            cuda_count = int(self._ctranslate2.get_cuda_device_count())
        except Exception:
            cuda_count = 0

        if gpus and cuda_count > 0:
            best = gpus[0]
            self.device_index = int(best["index"])
            self.gpu_name = str(best["name"])
            self.model_name = select_model_for_vram(float(best["vram_mb"]))
            self._theme.ok(
                message(
                    self._settings,
                    "gpu_detected",
                    name=self.gpu_name,
                    vram=format_vram(float(best["vram_mb"])),
                )
            )
            last_error = "unknown"
            for compute_type in self._cuda_compute_candidates():
                self._theme.info(
                    message(self._settings, "gpu_trying", compute=compute_type)
                )
                try:
                    self.model = self._create_model(
                        "cuda",
                        compute_type,
                        self.device_index,
                    )
                    self.device = "cuda"
                    self.compute_type = compute_type
                    self._theme.ok(
                        message(
                            self._settings,
                            "device",
                            device=f"CUDA · {self.gpu_name} · {compute_type} · {self.model_name}",
                        )
                    )
                    self._theme.ok(
                        message(self._settings, "gpu_compute", compute=compute_type)
                    )
                    return
                except Exception as error:
                    last_error = str(error).split("\n")[0]
                    self._theme.warn(
                        message(
                            self._settings,
                            "gpu_failed_mode",
                            compute=compute_type,
                        )
                    )
            self._theme.warn(
                message(self._settings, "gpu_fallback", reason=last_error)
            )
        else:
            self._theme.warn(message(self._settings, "no_gpu"))

        self.device = "cpu"
        self.compute_type = "int8"
        self.model = self._create_model("cpu", "int8")
        self._theme.ok(message(self._settings, "device", device="CPU · int8"))

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        progress: Any,
        chunk_duration: float,
    ) -> list[Any]:
        progress_start = progress.n
        try:
            return self._transcribe_once(audio_path, language, progress, chunk_duration)
        except Exception as first_error:
            if self.device != "cuda":
                raise
            progress.n = progress_start
            progress.refresh()
            last_error = str(first_error).split("\n")[0]
            for compute_type in self._cuda_compute_candidates():
                if compute_type == self.compute_type:
                    continue
                self._write(
                    message(self._settings, "gpu_trying", compute=compute_type),
                    "info",
                )
                try:
                    self.model = self._create_model(
                        "cuda",
                        compute_type,
                        self.device_index,
                    )
                    self.compute_type = compute_type
                    self._write(
                        message(
                            self._settings,
                            "device",
                            device=f"CUDA · {self.gpu_name} · {compute_type}",
                        ),
                        "ok",
                    )
                    return self._transcribe_once(
                        audio_path,
                        language,
                        progress,
                        chunk_duration,
                    )
                except Exception as error:
                    last_error = str(error).split("\n")[0]
                    self._write(
                        message(
                            self._settings,
                            "gpu_failed_mode",
                            compute=compute_type,
                        ),
                        "warn",
                    )

            # Stay on GPU failure path only after every CUDA mode fails.
            progress.n = progress_start
            progress.refresh()
            self._write(
                message(self._settings, "gpu_fallback", reason=last_error),
                "warn",
            )
            self.device = "cpu"
            self.compute_type = "int8"
            self.model = self._create_model("cpu", "int8")
            self._write(message(self._settings, "device", device="CPU · int8"), "ok")
            return self._transcribe_once(audio_path, language, progress, chunk_duration)

    def _transcribe_once(
        self,
        audio_path: Path,
        language: str,
        progress: Any,
        chunk_duration: float,
    ) -> list[Any]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            segments, _ = self.model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=True,
            )
        completed = 0.0
        result = []
        last_tick = time.monotonic()
        for segment in segments:
            result.append(segment)
            current = min(chunk_duration, float(segment.end))
            progress.update(max(0.0, current - completed))
            completed = current
            now = time.monotonic()
            if now - last_tick >= 2:
                progress.set_postfix_str(
                    f"{message(self._settings, 'transcribing')} · {current:.0f}s",
                    refresh=True,
                )
                last_tick = now
        progress.update(max(0.0, chunk_duration - completed))
        return result


def process_media(
    media_path: Path,
    paths: AppPaths,
    settings: Settings,
    av: Any,
    ffmpeg_path: str,
    tqdm: Any,
    transcriber: Transcriber,
    theme: Theme,
) -> None:
    language = language_record(settings.audio_language)
    try:
        duration, stream_index, matched = media_details(
            av,
            media_path,
            (language[0], language[1]),
        )
    except ValueError as error:
        if str(error) == "NO_AUDIO":
            raise RuntimeError(message(settings, "no_audio")) from error
        if str(error) == "UNKNOWN_DURATION":
            raise RuntimeError(message(settings, "unknown_duration")) from error
        raise

    selected_name = language_name(settings.audio_language, settings.ui_language)
    theme.info(
        message(
            settings,
            "audio_selected" if matched else "audio_fallback",
            language=selected_name,
        )
    )
    if settings.noise_reduction:
        theme.info(message(settings, "denoise_active"))
    check_disk_space(paths, min(CHUNK_SECONDS, duration), settings)

    output_srt, output_txt = unique_output_paths(paths.output, media_path.stem)
    partial_srt = paths.temporary / f"{output_srt.name}.part"
    partial_txt = paths.temporary / f"{output_txt.name}.part"

    subtitle_number = 1
    try:
        with (
            partial_srt.open("w", encoding="utf-8", newline="\n") as srt_file,
            partial_txt.open("w", encoding="utf-8", newline="\n") as txt_file,
            tqdm(
                total=max(duration * 2, 0.001),
                unit="s",
                desc=message(settings, "processing"),
                dynamic_ncols=True,
                bar_format="{l_bar}{bar}| {percentage:3.0f}% · {elapsed}<{remaining}",
                colour="cyan",
            ) as progress,
        ):
            start = 0.0
            while start < duration:
                chunk_duration = min(CHUNK_SECONDS, duration - start)
                check_disk_space(paths, chunk_duration, settings)
                progress.set_postfix_str(message(settings, "extracting"))
                with tempfile.NamedTemporaryFile(
                    suffix=".wav",
                    prefix="lasx_",
                    dir=paths.temporary,
                    delete=False,
                ) as temporary_file:
                    chunk_path = Path(temporary_file.name)

                try:
                    extract_chunk(
                        ffmpeg_path,
                        media_path,
                        chunk_path,
                        stream_index,
                        start,
                        chunk_duration,
                        progress,
                        settings,
                        settings.noise_reduction,
                    )
                    progress.set_postfix_str(message(settings, "transcribing"))
                    segments = transcriber.transcribe(
                        chunk_path,
                        settings.audio_language,
                        progress,
                        chunk_duration,
                    )
                    for segment in segments:
                        text = str(segment.text).strip()
                        if not text:
                            continue
                        absolute_start = start + float(segment.start)
                        absolute_end = start + float(segment.end)
                        srt_file.write(
                            f"{subtitle_number}\n"
                            f"{format_srt_time(absolute_start)} --> "
                            f"{format_srt_time(absolute_end)}\n"
                            f"{text}\n\n"
                        )
                        txt_file.write(f"{text}\n")
                        subtitle_number += 1
                    srt_file.flush()
                    txt_file.flush()
                finally:
                    chunk_path.unlink(missing_ok=True)
                start += chunk_duration

        partial_srt.replace(output_srt)
        partial_txt.replace(output_txt)
        move_safely(media_path, paths.processed)
        theme.ok(message(settings, "complete", name=output_srt.name))
    except BaseException:
        partial_srt.unlink(missing_ok=True)
        partial_txt.unlink(missing_ok=True)
        raise


def write_error_log(paths: AppPaths, media_path: Path, error: BaseException) -> Path:
    log_path = unique_path(paths.errors, f"{media_path.stem}.error.log")
    log_path.write_text(
        f"{APP_NAME} error report\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"File: {media_path}\n"
        f"Error: {error}\n\n"
        f"{traceback.format_exc()}",
        encoding="utf-8",
    )
    return log_path


def candidate_files(paths: AppPaths) -> Iterable[Path]:
    for path in sorted(paths.incoming.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and not path.name.startswith(".") and not path.name.endswith(".part"):
            yield path


def monitor(
    paths: AppPaths,
    settings: Settings,
    av: Any,
    ctranslate2: Any,
    imageio_ffmpeg: Any,
    tqdm: Any,
    faster_whisper: Any,
    theme: Theme,
) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    transcriber: Transcriber | None = None
    observations: dict[Path, tuple[int, int, int]] = {}
    announced: set[Path] = set()

    print()
    theme.info(message(settings, "monitoring", path=paths.incoming))
    theme.muted(message(settings, "drop_files"))
    theme.muted(message(settings, "waiting_next"))

    while True:
        present = set(candidate_files(paths))
        for stale in set(observations) - present:
            observations.pop(stale, None)
            announced.discard(stale)

        processed_any = False
        for media_path in present:
            try:
                stat = media_path.stat()
            except OSError:
                continue
            signature = (stat.st_size, stat.st_mtime_ns)
            previous = observations.get(media_path)
            stable_count = previous[2] + 1 if previous and previous[:2] == signature else 0
            observations[media_path] = (*signature, stable_count)
            if stable_count < STABLE_CHECKS_REQUIRED:
                if media_path not in announced:
                    theme.warn(message(settings, "waiting_stable", name=media_path.name))
                    announced.add(media_path)
                continue

            observations.pop(media_path, None)
            announced.discard(media_path)
            print()
            theme.info(message(settings, "detected", name=media_path.name))
            try:
                if transcriber is None:
                    transcriber = Transcriber(
                        ctranslate2,
                        faster_whisper,
                        settings,
                        theme,
                        tqdm,
                    )
                process_media(
                    media_path,
                    paths,
                    settings,
                    av,
                    ffmpeg_path,
                    tqdm,
                    transcriber,
                    theme,
                )
            except Exception as error:
                theme.error(message(settings, "failed", error=error))
                write_error_log(paths, media_path, error)
                try:
                    move_safely(media_path, paths.errors)
                except OSError:
                    pass
                theme.warn(message(settings, "moved_error"))
            processed_any = True

        if processed_any:
            theme.muted(message(settings, "waiting_next"))
        time.sleep(POLL_SECONDS)


def main_menu(
    paths: AppPaths,
    settings: Settings,
    runtime: tuple[Any, Any, Any, Any, Any],
    theme: Theme,
) -> None:
    av, ctranslate2, imageio_ffmpeg, tqdm, faster_whisper = runtime
    while True:
        theme.banner(f"{APP_NAME} · {message(settings, 'menu_title')}")
        print(
            message(
                settings,
                "current",
                ui=UI_NAMES[settings.ui_language],
                audio=language_name(settings.audio_language, settings.ui_language),
                noise=noise_label(settings),
            )
        )
        print()
        print(f"  {theme.Fore.CYAN}1.{theme.Style.RESET_ALL} {message(settings, 'menu_start')}")
        print(f"  {theme.Fore.CYAN}2.{theme.Style.RESET_ALL} {message(settings, 'menu_ui')}")
        print(f"  {theme.Fore.CYAN}3.{theme.Style.RESET_ALL} {message(settings, 'menu_audio')}")
        print(f"  {theme.Fore.CYAN}4.{theme.Style.RESET_ALL} {message(settings, 'menu_noise')}")
        print(f"  {theme.Fore.CYAN}0.{theme.Style.RESET_ALL} {message(settings, 'menu_exit')}")
        print()
        choice = input(
            f"{theme.Fore.GREEN}{message(settings, 'choose')}{theme.Style.RESET_ALL}"
        ).strip()

        if choice == "1":
            try:
                monitor(
                    paths,
                    settings,
                    av,
                    ctranslate2,
                    imageio_ffmpeg,
                    tqdm,
                    faster_whisper,
                    theme,
                )
            except KeyboardInterrupt:
                print()
                theme.warn(message(settings, "stopped"))
        elif choice == "2":
            choose_ui_language(settings, paths, theme)
        elif choice == "3":
            choose_audio_language(settings, paths, theme)
        elif choice == "4":
            toggle_noise_reduction(settings, paths, theme)
        elif choice == "0":
            theme.ok(message(settings, "goodbye"))
            return
        else:
            theme.warn(message(settings, "invalid"))


def main() -> int:
    configure_console()
    paths = AppPaths.create()
    paths.ensure_directories()
    settings = Settings.load(paths.settings)
    try:
        check_python(settings)
        # Install packages first so Theme/colorama/CUDA libs are available afterwards.
        ensure_dependencies(settings, None)
        configure_cuda_dll_paths()
        theme = Theme()
        runtime = load_runtime_dependencies()
        theme.info(message(settings, "folders", path=paths.base))
        main_menu(paths, settings, runtime, theme)
        return 0
    except KeyboardInterrupt:
        print(f"\n{message(settings, 'goodbye')}")
        return 130
    except Exception as error:
        print(f"\n{message(settings, 'failed', error=error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
