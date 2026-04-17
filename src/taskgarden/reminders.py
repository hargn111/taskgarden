"""Reminder message generation helpers for Task Garden."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from .todos import TodoItem, reminder_due

DEFAULT_REMINDER_CONFIG_PATH = Path("/root/.openclaw/workspace/state/automation/reminder-config.json")
DEFAULT_STYLE_PROMPT = (
    "Brief, direct, and lightly human. Sound like a useful reminder, not a chatbot."
)
DEFAULT_TIMEOUT_SECONDS = 90


class ReminderAttempt(TypedDict, total=False):
    model: str
    ok: bool
    error: str


class ReminderMessageResult(TypedDict, total=False):
    text: str
    mode: str
    provider: Optional[str]
    model: str
    attempts: List[ReminderAttempt]


class ReminderGenerationConfig(TypedDict, total=False):
    primaryModel: str
    fallbackModels: List[str]
    timeoutSeconds: int
    stylePrompt: str


def reminder_config_path() -> Path:
    """Return the configured reminder-config path."""
    return Path(os.getenv("TASKGARDEN_REMINDER_CONFIG_PATH", DEFAULT_REMINDER_CONFIG_PATH))


def load_reminder_config(path: Optional[Path] = None) -> ReminderGenerationConfig:
    """Load reminder generation config with sane defaults."""
    config_path = path or reminder_config_path()
    config: ReminderGenerationConfig = {
        "primaryModel": "plain",
        "fallbackModels": [],
        "timeoutSeconds": DEFAULT_TIMEOUT_SECONDS,
        "stylePrompt": DEFAULT_STYLE_PROMPT,
    }
    if not config_path.exists():
        return config

    raw = json.loads(config_path.read_text())
    section = raw.get("messageGeneration", raw)
    if not isinstance(section, dict):
        return config

    if isinstance(section.get("primaryModel"), str) and section["primaryModel"].strip():
        config["primaryModel"] = section["primaryModel"].strip()
    fallback_models = section.get("fallbackModels")
    if isinstance(fallback_models, list):
        config["fallbackModels"] = [
            model.strip()
            for model in fallback_models
            if isinstance(model, str) and model.strip()
        ]
    timeout_value = section.get("timeoutSeconds")
    if isinstance(timeout_value, (int, float)) and int(timeout_value) > 0:
        config["timeoutSeconds"] = int(timeout_value)
    if isinstance(section.get("stylePrompt"), str) and section["stylePrompt"].strip():
        config["stylePrompt"] = section["stylePrompt"].strip()
    return config


def due_reminder_items(items: List[TodoItem]) -> List[TodoItem]:
    """Return items currently due for reminder."""
    return [item for item in items if reminder_due(item)]


def build_plain_reminder_text(items: List[TodoItem]) -> str:
    """Build the deterministic plain reminder text."""
    return "\n".join(f"Reminder: {item['title']}" for item in items)


def build_reminder_prompt(items: List[TodoItem], style_prompt: str) -> str:
    """Build the prompt for optional model-based reminder wording."""
    titles = "\n".join(f"- {item['title']}" for item in items)
    return (
        "Write a short reminder message for Tom about these due todo items.\n\n"
        f"Due items:\n{titles}\n\n"
        f"Style:\n{style_prompt}\n\n"
        "Rules:\n"
        "- Output only the reminder message.\n"
        "- Keep it concise and natural.\n"
        "- Mention each due item exactly once.\n"
        "- No markdown headings.\n"
        "- No extra explanation.\n"
    )


def run_model_prompt(
    prompt: str,
    model: str,
    timeout_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ReminderMessageResult:
    """Run one model prompt through OpenClaw infer."""
    result = runner(
        [
            "openclaw",
            "infer",
            "model",
            "run",
            "--prompt",
            prompt,
            "--model",
            model,
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=True,
    )
    payload = json.loads(result.stdout)
    outputs = payload.get("outputs") or []
    if not outputs or not outputs[0].get("text"):
        raise RuntimeError(f"Model returned no text output: {model}")
    text = outputs[0]["text"].strip()
    if not text:
        raise RuntimeError(f"Model returned blank text: {model}")
    return {
        "text": text,
        "mode": "model",
        "provider": payload.get("provider"),
        "model": payload.get("model") or model,
        "attempts": [],
    }


def generate_reminder_message(
    items: List[TodoItem],
    config: Optional[ReminderGenerationConfig] = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ReminderMessageResult:
    """Generate reminder text from config, with fallback support."""
    active_config = config or load_reminder_config()
    plain_text = build_plain_reminder_text(items)
    models = [
        model
        for model in [active_config.get("primaryModel"), *active_config.get("fallbackModels", [])]
        if isinstance(model, str) and model
    ]
    if not models:
        models = ["plain"]

    prompt = build_reminder_prompt(items, active_config.get("stylePrompt", DEFAULT_STYLE_PROMPT))
    timeout_seconds = int(active_config.get("timeoutSeconds", DEFAULT_TIMEOUT_SECONDS))
    attempts: List[ReminderAttempt] = []

    for model in models:
        if model == "plain":
            return {
                "text": plain_text,
                "mode": "plain",
                "model": "plain",
                "attempts": attempts,
            }
        try:
            result = run_model_prompt(prompt, model, timeout_seconds, runner=runner)
            attempts.append({"model": model, "ok": True})
            result["attempts"] = attempts
            return result
        except Exception as exc:  # pragma: no cover - exercised via tests using mocks
            attempts.append({"model": model, "ok": False, "error": str(exc)})

    return {
        "text": plain_text,
        "mode": "plain-emergency",
        "model": "plain",
        "attempts": attempts,
    }
