#!/usr/bin/env python3
"""Language-aware, resilient media transcription with automatic setup."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


APP_NAME = "LanguageAwareSubtitleExtractor"
MIN_PYTHON = (3, 9)
MODEL_NAME = "small"
CHUNK_SECONDS = 20 * 60
POLL_SECONDS = 3
STABLE_CHECKS_REQUIRED = 2
FFMPEG_INACTIVITY_TIMEOUT = 180

DEPENDENCIES = {
    "av": "av",
    "faster_whisper": "faster-whisper",
    "imageio_ffmpeg": "imageio-ffmpeg",
    "tqdm": "tqdm",
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
        "checking": "Checking required components...",
        "installing": "Missing components: {items}\nInstalling them automatically...",
        "install_failed": "Automatic installation failed. Run this command and try again:\n{command}",
        "ready": "All required components are ready.",
        "folders": "Working folders: {path}",
        "menu_title": "MAIN MENU",
        "menu_start": "Start monitoring and processing",
        "menu_ui": "Change menu language",
        "menu_audio": "Change original audio language",
        "menu_exit": "Exit",
        "current": "Current: menu={ui}, audio={audio}",
        "choose": "Choose an option: ",
        "invalid": "Invalid option. Please try again.",
        "choose_ui": "Select the menu language:",
        "choose_audio": "Select the original spoken language:",
        "saved": "Preference saved.",
        "monitoring": "Monitoring: {path}",
        "drop_files": "Copy media files into this folder. Press Ctrl+C to return to the menu.",
        "waiting_stable": "Waiting for {name} to finish copying...",
        "detected": "Processing: {name}",
        "loading_model": "Loading speech model '{model}' (it downloads automatically on first use)...",
        "device": "Transcription device: {device}",
        "gpu_fallback": "GPU transcription is unavailable; retrying this chunk on CPU.",
        "extracting": "Extracting audio",
        "transcribing": "Transcribing",
        "processing": "Overall progress",
        "no_audio": "No audio stream was found in this media file.",
        "audio_fallback": "No {language} audio track metadata was found; using the first audio track.",
        "audio_selected": "Using the audio track tagged as {language}.",
        "complete": "Completed. Subtitle: {name}",
        "failed": "Failed: {error}",
        "moved_error": "The media and diagnostic log were moved to the Errors folder.",
        "stopped": "Monitoring stopped.",
        "goodbye": "Goodbye.",
        "python_old": "Python {required}+ is required. Current version: {current}.",
        "disk_space": "Not enough free disk space. At least {needed} is required.",
        "ffmpeg_stalled": "FFmpeg produced no progress for {seconds} seconds and was stopped.",
        "unknown_duration": "The media duration could not be determined.",
    },
    "pt": {
        "checking": "Verificando os componentes necessários...",
        "installing": "Componentes ausentes: {items}\nInstalando automaticamente...",
        "install_failed": "A instalação automática falhou. Execute este comando e tente novamente:\n{command}",
        "ready": "Todos os componentes necessários estão prontos.",
        "folders": "Pastas de trabalho: {path}",
        "menu_title": "MENU PRINCIPAL",
        "menu_start": "Iniciar monitoramento e processamento",
        "menu_ui": "Alterar idioma do menu",
        "menu_audio": "Alterar idioma original do áudio",
        "menu_exit": "Sair",
        "current": "Atual: menu={ui}, áudio={audio}",
        "choose": "Escolha uma opção: ",
        "invalid": "Opção inválida. Tente novamente.",
        "choose_ui": "Selecione o idioma do menu:",
        "choose_audio": "Selecione o idioma original falado:",
        "saved": "Preferência salva.",
        "monitoring": "Monitorando: {path}",
        "drop_files": "Copie arquivos de mídia para esta pasta. Pressione Ctrl+C para voltar ao menu.",
        "waiting_stable": "Aguardando a cópia de {name} terminar...",
        "detected": "Processando: {name}",
        "loading_model": "Carregando o modelo de fala '{model}' (o primeiro uso faz o download automático)...",
        "device": "Dispositivo de transcrição: {device}",
        "gpu_fallback": "A transcrição por GPU não está disponível; tentando este trecho na CPU.",
        "extracting": "Extraindo áudio",
        "transcribing": "Transcrevendo",
        "processing": "Progresso geral",
        "no_audio": "Nenhuma faixa de áudio foi encontrada neste arquivo.",
        "audio_fallback": "Nenhuma faixa marcada como {language} foi encontrada; usando a primeira faixa de áudio.",
        "audio_selected": "Usando a faixa de áudio marcada como {language}.",
        "complete": "Concluído. Legenda: {name}",
        "failed": "Falha: {error}",
        "moved_error": "A mídia e o diagnóstico foram movidos para a pasta Errors.",
        "stopped": "Monitoramento interrompido.",
        "goodbye": "Até logo.",
        "python_old": "Python {required}+ é necessário. Versão atual: {current}.",
        "disk_space": "Espaço em disco insuficiente. São necessários pelo menos {needed}.",
        "ffmpeg_stalled": "O FFmpeg ficou {seconds} segundos sem progresso e foi interrompido.",
        "unknown_duration": "Não foi possível determinar a duração da mídia.",
    },
    "es": {
        "checking": "Comprobando los componentes necesarios...",
        "installing": "Componentes faltantes: {items}\nInstalándolos automáticamente...",
        "install_failed": "La instalación automática falló. Ejecuta este comando e inténtalo de nuevo:\n{command}",
        "ready": "Todos los componentes necesarios están listos.",
        "folders": "Carpetas de trabajo: {path}",
        "menu_title": "MENÚ PRINCIPAL",
        "menu_start": "Iniciar monitoreo y procesamiento",
        "menu_ui": "Cambiar idioma del menú",
        "menu_audio": "Cambiar idioma original del audio",
        "menu_exit": "Salir",
        "current": "Actual: menú={ui}, audio={audio}",
        "choose": "Elige una opción: ",
        "invalid": "Opción no válida. Inténtalo de nuevo.",
        "choose_ui": "Selecciona el idioma del menú:",
        "choose_audio": "Selecciona el idioma original hablado:",
        "saved": "Preferencia guardada.",
        "monitoring": "Monitoreando: {path}",
        "drop_files": "Copia archivos multimedia en esta carpeta. Pulsa Ctrl+C para volver al menú.",
        "waiting_stable": "Esperando a que termine la copia de {name}...",
        "detected": "Procesando: {name}",
        "loading_model": "Cargando el modelo de voz '{model}' (se descarga automáticamente la primera vez)...",
        "device": "Dispositivo de transcripción: {device}",
        "gpu_fallback": "La transcripción por GPU no está disponible; reintentando este fragmento en CPU.",
        "extracting": "Extrayendo audio",
        "transcribing": "Transcribiendo",
        "processing": "Progreso general",
        "no_audio": "No se encontró ninguna pista de audio en este archivo.",
        "audio_fallback": "No se encontró una pista marcada como {language}; se usará la primera pista de audio.",
        "audio_selected": "Usando la pista de audio marcada como {language}.",
        "complete": "Completado. Subtítulo: {name}",
        "failed": "Error: {error}",
        "moved_error": "El archivo y el diagnóstico se movieron a la carpeta Errors.",
        "stopped": "Monitoreo detenido.",
        "goodbye": "Hasta luego.",
        "python_old": "Se requiere Python {required}+. Versión actual: {current}.",
        "disk_space": "No hay suficiente espacio libre. Se requiere al menos {needed}.",
        "ffmpeg_stalled": "FFmpeg no produjo progreso durante {seconds} segundos y fue detenido.",
        "unknown_duration": "No se pudo determinar la duración del archivo.",
    },
}


def base_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LASX_HOME", r"C:\SubtitlesGenerator"))
    return Path(os.environ.get("LASX_HOME", str(Path.home() / "SubtitlesGenerator")))


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

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ui = data.get("ui_language", "en")
            audio = data.get("audio_language", "en")
            valid_audio = {language[0] for language in LANGUAGES}
            return cls(ui if ui in MESSAGES else "en", audio if audio in valid_audio else "en")
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {"ui_language": self.ui_language, "audio_language": self.audio_language},
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


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def check_python(settings: Settings) -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(map(str, MIN_PYTHON))
        current = ".".join(map(str, sys.version_info[:3]))
        raise RuntimeError(message(settings, "python_old", required=required, current=current))


def ensure_dependencies(settings: Settings) -> None:
    print(message(settings, "checking"))
    missing = [
        package
        for module, package in DEPENDENCIES.items()
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        print(message(settings, "ready"))
        return

    print(message(settings, "installing", items=", ".join(missing)))
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
    print(message(settings, "ready"))


def load_runtime_dependencies() -> tuple[Any, Any, Any, Any]:
    av = importlib.import_module("av")
    ctranslate2 = importlib.import_module("ctranslate2")
    imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
    tqdm_module = importlib.import_module("tqdm")
    faster_whisper = importlib.import_module("faster_whisper")
    return av, ctranslate2, imageio_ffmpeg, tqdm_module.tqdm, faster_whisper


def choose_from_list(settings: Settings, title_key: str, options: list[tuple[str, str]]) -> str:
    print(f"\n{message(settings, title_key)}")
    for index, (_, label) in enumerate(options, start=1):
        print(f"  {index:2}. {label}")
    while True:
        choice = input(message(settings, "choose")).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print(message(settings, "invalid"))


def choose_ui_language(settings: Settings, paths: AppPaths) -> None:
    options = [(code, label) for code, label in UI_NAMES.items()]
    settings.ui_language = choose_from_list(settings, "choose_ui", options)
    settings.save(paths.settings)
    print(message(settings, "saved"))


def choose_audio_language(settings: Settings, paths: AppPaths) -> None:
    column = LANGUAGE_NAME_COLUMN[settings.ui_language]
    options = [(language[0], language[column]) for language in LANGUAGES]
    settings.audio_language = choose_from_list(settings, "choose_audio", options)
    settings.save(paths.settings)
    print(message(settings, "saved"))


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
    # Mono, 16 kHz, 16-bit PCM plus a conservative safety margin.
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
    ) -> None:
        self._faster_whisper = faster_whisper
        self._settings = settings
        self.device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        self.model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        compute_type = "float16" if self.device == "cuda" else "int8"
        print(message(self._settings, "loading_model", model=MODEL_NAME))
        try:
            self.model = self._faster_whisper.WhisperModel(
                MODEL_NAME,
                device=self.device,
                compute_type=compute_type,
            )
        except Exception:
            if self.device != "cuda":
                raise
            self.device = "cpu"
            print(message(self._settings, "gpu_fallback"))
            self.model = self._faster_whisper.WhisperModel(
                MODEL_NAME,
                device="cpu",
                compute_type="int8",
            )
        print(message(self._settings, "device", device=self.device.upper()))

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
        except Exception:
            if self.device != "cuda":
                raise
            progress.n = progress_start
            progress.refresh()
            self.device = "cpu"
            print(f"\n{message(self._settings, 'gpu_fallback')}")
            self.model = self._faster_whisper.WhisperModel(
                MODEL_NAME,
                device="cpu",
                compute_type="int8",
            )
            return self._transcribe_once(audio_path, language, progress, chunk_duration)

    def _transcribe_once(
        self,
        audio_path: Path,
        language: str,
        progress: Any,
        chunk_duration: float,
    ) -> list[Any]:
        segments, _ = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )
        completed = 0.0
        result = []
        for segment in segments:
            result.append(segment)
            current = min(chunk_duration, float(segment.end))
            progress.update(max(0.0, current - completed))
            completed = current
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
    print(
        message(
            settings,
            "audio_selected" if matched else "audio_fallback",
            language=selected_name,
        )
    )
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
                total=duration * 2,
                unit="media-sec",
                desc=message(settings, "processing"),
                dynamic_ncols=True,
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
        print(message(settings, "complete", name=output_srt.name))
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
) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    transcriber: Transcriber | None = None
    observations: dict[Path, tuple[int, int, int]] = {}
    announced: set[Path] = set()

    print(f"\n{message(settings, 'monitoring', path=paths.incoming)}")
    print(message(settings, "drop_files"))

    while True:
        present = set(candidate_files(paths))
        for stale in set(observations) - present:
            observations.pop(stale, None)
            announced.discard(stale)

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
                    print(message(settings, "waiting_stable", name=media_path.name))
                    announced.add(media_path)
                continue

            observations.pop(media_path, None)
            announced.discard(media_path)
            print(f"\n{message(settings, 'detected', name=media_path.name)}")
            try:
                if transcriber is None:
                    transcriber = Transcriber(ctranslate2, faster_whisper, settings)
                process_media(
                    media_path,
                    paths,
                    settings,
                    av,
                    ffmpeg_path,
                    tqdm,
                    transcriber,
                )
            except Exception as error:
                print(message(settings, "failed", error=error))
                write_error_log(paths, media_path, error)
                try:
                    move_safely(media_path, paths.errors)
                except OSError:
                    pass
                print(message(settings, "moved_error"))

        time.sleep(POLL_SECONDS)


def main_menu(
    paths: AppPaths,
    settings: Settings,
    runtime: tuple[Any, Any, Any, Any, Any],
) -> None:
    av, ctranslate2, imageio_ffmpeg, tqdm, faster_whisper = runtime
    while True:
        print(f"\n=== {APP_NAME}: {message(settings, 'menu_title')} ===")
        print(
            message(
                settings,
                "current",
                ui=UI_NAMES[settings.ui_language],
                audio=language_name(settings.audio_language, settings.ui_language),
            )
        )
        print(f"  1. {message(settings, 'menu_start')}")
        print(f"  2. {message(settings, 'menu_ui')}")
        print(f"  3. {message(settings, 'menu_audio')}")
        print(f"  0. {message(settings, 'menu_exit')}")
        choice = input(message(settings, "choose")).strip()

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
                )
            except KeyboardInterrupt:
                print(f"\n{message(settings, 'stopped')}")
        elif choice == "2":
            choose_ui_language(settings, paths)
        elif choice == "3":
            choose_audio_language(settings, paths)
        elif choice == "0":
            print(message(settings, "goodbye"))
            return
        else:
            print(message(settings, "invalid"))


def main() -> int:
    configure_console()
    paths = AppPaths.create()
    paths.ensure_directories()
    settings = Settings.load(paths.settings)
    try:
        check_python(settings)
        ensure_dependencies(settings)
        runtime = load_runtime_dependencies()
        print(message(settings, "folders", path=paths.base))
        main_menu(paths, settings, runtime)
        return 0
    except KeyboardInterrupt:
        print(f"\n{message(settings, 'goodbye')}")
        return 130
    except Exception as error:
        print(f"\n{message(settings, 'failed', error=error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
