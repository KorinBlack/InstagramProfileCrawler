"""
Settings schema and resolution.

One list of fields drives the CLI, the pipeline and the web GUI. A value is resolved in this
order, first match wins:

    job override  ->  global settings (GUI)  ->  .env / environment  ->  built-in default
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from .filtering.visual_ai import DEFAULT_CAPTION_PROMPT, NEGATIVE_PROMPT, SYSTEM_PROMPT


@dataclass(frozen=True)
class Field:
    key: str
    type: str                 # bool | int | float | str | text | choice | account | secret
    default: Any
    group: str
    label: str
    help: str = ""
    env: Optional[str] = None
    choices: Tuple[str, ...] = ()
    secret: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    engine: Optional[str] = None   # host/model/key of one engine: shown only when it is selected
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key, "type": self.type, "default": self.default, "group": self.group,
            "label": self.label, "help": self.help, "env": self.env, "choices": list(self.choices),
            "secret": self.secret, "min": self.min, "max": self.max, "engine": self.engine,
        }


GROUPS = [
    ("instagram", "Instagram"),
    ("processing", "Elaborazione immagini"),
    ("ai", "Visual AI"),
    ("filter", "Filtro"),
    ("captions", "Caption"),
]

FIELDS: List[Field] = [
    # Instagram ------------------------------------------------------------------
    Field("account", "account", "", "instagram", "Account Instagram",
          "Sessione usata per lo scraping. Vuoto = INSTAGRAM_SESSION_ID dal file .env. "
          "Usa un account diverso per profili privati che solo quell'account segue."),
    Field("max_posts", "int", 0, "instagram", "Post massimi", "0 = tutti i post del profilo.", min=0),
    Field("include_posts", "bool", True, "instagram", "Post e caroselli"),
    Field("include_highlights", "bool", True, "instagram", "Storie in evidenza"),
    Field("include_stories", "bool", False, "instagram", "Storie attive (24 h)"),
    Field("include_video_covers", "bool", False, "instagram", "Copertine dei video",
          "Scarica il fotogramma di copertina di video e reel."),
    Field("incremental", "bool", True, "instagram", "Passate incrementali",
          "Se un profilo è già stato scaricato per intero, si ferma ai primi post già noti."),
    Field("rate_limit_delay", "float", 1.5, "instagram", "Pausa tra richieste (s)",
          "Media con ±30% di variazione. Valori bassi aumentano il rischio di blocchi temporanei.",
          env="RATE_LIMIT_DELAY", min=0, max=60),
    Field("headless", "bool", True, "instagram", "Browser invisibile",
          "Disattiva per vedere la finestra di Chromium durante lo scraping."),
    Field("output_dir", "str", "./dataset", "instagram", "Cartella dataset",
          "Ogni profilo finisce in una sottocartella con il suo nome.", env="OUTPUT_DIR"),

    # Processing -----------------------------------------------------------------
    Field("process_scope", "choice", "new", "processing", "Immagini da elaborare",
          "new = solo quelle scaricate in questa passata; all = tutto il dataset del profilo.",
          choices=("new", "all")),
    Field("deduplicate", "bool", True, "processing", "Rimuovi duplicati",
          "I duplicati vengono spostati in _rejected, non cancellati."),
    Field("optimize", "bool", False, "processing", "Ottimizza immagini",
          "Ridimensiona e ricomprime sul posto. Irreversibile sugli originali."),
    Field("target_size", "int", 1024, "processing", "Lato massimo (px)", min=256, max=4096),
    Field("image_quality", "int", 95, "processing", "Qualità JPEG", env="IMAGE_QUALITY", min=50, max=100),

    # Visual AI ------------------------------------------------------------------
    Field("engine", "choice", "ollama", "ai", "Engine",
          "Sotto vedi host, modello e API key dell'engine scelto; quelli degli altri restano salvati.",
          env="VISUAL_AI_TYPE",
          choices=("ollama", "llama.cpp", "strata")),
    Field("ollama_host", "str", "http://localhost:11434", "ai", "Host Ollama", env="VISUAL_AI_OLLAMA_HOST", engine="ollama"),
    Field("ollama_model", "str", "llava", "ai", "Modello Ollama", env="VISUAL_AI_OLLAMA_MODEL", engine="ollama"),
    Field("ollama_api_key", "secret", "", "ai", "API key Ollama",
          "Solo se Ollama è dietro un proxy con autenticazione. Inviata come \"Authorization: Bearer\".",
          env="VISUAL_AI_OLLAMA_API_KEY", secret=True, engine="ollama"),
    Field("llama_host", "str", "http://localhost:8080", "ai", "Host llama.cpp", env="VISUAL_AI_LLAMA_HOST", engine="llama.cpp"),
    Field("llama_model", "str", "gemma4", "ai", "Modello llama.cpp", env="VISUAL_AI_LLAMA_MODEL", engine="llama.cpp"),
    Field("llama_api_key", "secret", "", "ai", "API key llama.cpp",
          "La chiave passata a llama-server con --api-key.", env="VISUAL_AI_LLAMA_API_KEY", secret=True, engine="llama.cpp"),
    Field("strata_host", "str", "http://127.0.0.1:8080", "ai", "Host Strata", env="VISUAL_AI_STRATA_HOST", engine="strata"),
    Field("strata_model", "str", "qwen3.8-flash-next", "ai", "Modello Strata", env="VISUAL_AI_STRATA_MODEL", engine="strata"),
    Field("strata_api_key", "secret", "", "ai", "API key Strata",
          "Se il server Strata la richiede.", env="VISUAL_AI_STRATA_API_KEY", secret=True, engine="strata"),
    Field("ai_timeout", "int", 300, "ai", "Timeout per immagine (s)", min=10, max=3600),
    Field("system_prompt", "text", SYSTEM_PROMPT.strip(), "ai", "System prompt",
          "Inviato al modello prima di ogni richiesta, con tutti gli engine."),

    # Filter -----------------------------------------------------------------------
    Field("filter_enabled", "bool", False, "filter", "Filtra con Visual AI", env="FILTERING_ENABLED"),
    Field("filter_prompt", "text", "", "filter", "Criterio di filtro",
          "Cosa tenere o scartare, in parole tue.", env="FILTERING_PROMPT"),
    Field("min_confidence", "float", 0.7, "filter", "Confidenza minima per scartare",
          "Un'immagine viene scartata solo se il modello è sicuro almeno quanto questa soglia.",
          env="MIN_CONFIDENCE", min=0, max=1),

    # Captions ---------------------------------------------------------------------
    Field("captions_enabled", "bool", False, "captions", "Genera caption", env="GENERATE_CAPTIONS"),
    Field("caption_format", "choice", "text", "captions", "Formato",
          "text = .txt accanto all'immagine (kohya, ai-toolkit); json = .json; "
          "pairs = .json con prompt e negative.", choices=("text", "json", "pairs")),
    Field("caption_prefix", "str", "", "captions", "Trigger word",
          "Anteposta a ogni caption, es. \"ohwx person,\"."),
    Field("use_ig_caption", "bool", False, "captions", "Usa la didascalia Instagram",
          "Passa al modello la didascalia originale del post come contesto."),
    Field("overwrite_captions", "bool", False, "captions", "Rigenera caption esistenti"),
    Field("caption_prompt", "text", DEFAULT_CAPTION_PROMPT.strip(), "captions", "Prompt caption"),
    Field("negative_prompt", "text", NEGATIVE_PROMPT.strip(), "captions", "Prompt negative",
          "Usato solo con il formato pairs."),
]

FIELDS_BY_KEY: Dict[str, Field] = {f.key: f for f in FIELDS}

_TRUE = ("true", "1", "yes", "on")


def coerce(field_: Field, value: Any) -> Any:
    """Convert a raw value (from env, JSON or a form) to the field's type. Raises ValueError."""
    if value is None:
        return field_.default
    t = field_.type
    if t == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUE
    if t in ("int", "float"):
        number = int(float(value)) if t == "int" else float(value)
        if field_.min is not None and number < field_.min:
            raise ValueError(f"{field_.label}: minimo {field_.min}")
        if field_.max is not None and number > field_.max:
            raise ValueError(f"{field_.label}: massimo {field_.max}")
        return number
    if t == "choice":
        value = str(value)
        if value not in field_.choices:
            raise ValueError(f"{field_.label}: valore non valido '{value}'")
        return value
    return str(value)


def env_values() -> Dict[str, Any]:
    """Values coming from .env / the environment, already typed. Invalid ones are skipped."""
    load_dotenv()
    values = {}
    for f in FIELDS:
        if f.env and os.getenv(f.env) not in (None, ""):
            try:
                values[f.key] = coerce(f, os.getenv(f.env))
            except ValueError:
                pass
    return values


def resolve(global_overrides: Optional[Dict[str, Any]] = None,
            job_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Return {key: {"value": ..., "source": "job" | "global" | "env" | "default"}}.
    """
    layers = [
        ("job", job_overrides or {}),
        ("global", global_overrides or {}),
        ("env", env_values()),
    ]
    resolved = {}
    for f in FIELDS:
        for source, layer in layers:
            if f.key in layer and layer[f.key] is not None:
                try:
                    resolved[f.key] = {"value": coerce(f, layer[f.key]), "source": source}
                    break
                except ValueError:
                    continue
        else:
            resolved[f.key] = {"value": f.default, "source": "default"}
    return resolved


def values(resolved: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {k: v["value"] for k, v in resolved.items()}


def clean_overrides(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a dict of overrides coming from the GUI; unknown keys are dropped."""
    cleaned = {}
    for key, value in (raw or {}).items():
        f = FIELDS_BY_KEY.get(key)
        if f is None or value is None:
            continue
        cleaned[key] = coerce(f, value)
    return cleaned


_ENGINE_PREFIX = {"ollama": "ollama", "llama.cpp": "llama", "strata": "strata"}


def engine_endpoint(settings: Dict[str, Any]) -> Tuple[str, str, str]:
    """(engine, host, model) for the selected engine."""
    engine = settings["engine"]
    prefix = _ENGINE_PREFIX[engine]
    return engine, settings[f"{prefix}_host"], settings[f"{prefix}_model"]


def engine_api_key(settings: Dict[str, Any]) -> str:
    """API key of the selected engine ("" = none)."""
    return settings.get(f"{_ENGINE_PREFIX[settings['engine']]}_api_key", "") or ""


# ---------------------------------------------------------------------- #
# Secrets: never sent to the browser in clear
# ---------------------------------------------------------------------- #

SECRET_KEYS = {f.key for f in FIELDS if f.secret}
SECRET_PREFIX = "__secret__:"


def mask_secret_value(value: str) -> str:
    """'' stays '' (not set); anything else becomes a sentinel with only the last 4 chars."""
    if not value:
        return ""
    tail = value[-4:] if len(value) > 8 else ""
    return f"{SECRET_PREFIX}…{tail}" if tail else f"{SECRET_PREFIX}••••"


def mask_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mask secrets in a flat {key: value} dict (overrides, a run's settings)."""
    return {k: (mask_secret_value(v) if k in SECRET_KEYS else v) for k, v in (data or {}).items()}


def mask_resolved(resolved: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Mask secrets in a resolve() result."""
    return {k: ({**v, "value": mask_secret_value(v["value"])} if k in SECRET_KEYS else v)
            for k, v in resolved.items()}


def unmask_overrides(incoming: Dict[str, Any], stored: Dict[str, Any],
                     inherited: Dict[str, Any]) -> Dict[str, Any]:
    """
    Put real secrets back into overrides coming from the browser.

    A masked sentinel means "unchanged": keep the value already stored at this layer, or, when
    the user has just chosen to customize an inherited secret, the inherited value.
    """
    result = dict(incoming or {})
    for key in SECRET_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.startswith(SECRET_PREFIX):
            result[key] = stored.get(key, inherited.get(key, ""))
    return result
