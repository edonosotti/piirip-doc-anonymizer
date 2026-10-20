"""Playbooks: lists of Presidio entities to redact."""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

ALL = "all"
DEFAULT = "default"


@dataclass
class Playbook:
    name: str
    entities: list[str]
    description: str = ""
    score_threshold: float | None = None
    extra: dict = field(default_factory=dict)


def _parse(name: str, text: str) -> Playbook:
    data = yaml.safe_load(text)
    if isinstance(data, list):
        data = {"entities": data}
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise ValueError(f"Playbook '{name}' must contain an 'entities' list")
    entities = [str(e).strip().upper() for e in data["entities"]]
    return Playbook(
        name=name,
        entities=entities,
        description=str(data.get("description", "")),
        score_threshold=data.get("score_threshold"),
    )


def load_playbook(spec: str | None) -> Playbook:
    """Load a playbook by built-in name ('default', 'all') or YAML file path.

    'all' is resolved by the engine to every entity supported by Presidio.
    """
    spec = spec or DEFAULT
    if spec == ALL:
        return Playbook(ALL, [], "Every entity supported by Presidio")
    path = Path(spec)
    if path.is_file():
        return _parse(path.stem, path.read_text(encoding="utf-8"))
    if spec == DEFAULT:
        text = resources.files("piirip.data").joinpath("default.yaml").read_text(encoding="utf-8")
        return _parse(DEFAULT, text)
    raise FileNotFoundError(f"Unknown playbook '{spec}' (use 'default', 'all' or a YAML file path)")
