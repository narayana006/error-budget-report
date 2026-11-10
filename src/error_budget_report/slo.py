"""Load SLO definitions from YAML or JSON.

Two shapes are accepted, and can be mixed in one file or directory:

* OpenSLO v1 documents with ``kind: SLO`` (a subset of fields, see README).
  Documents of any other kind (Service, SLI, AlertPolicy, ...) are skipped.
* A short form: a mapping with a top-level ``slos`` list of
  ``{name, target, window, service?, description?}``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

import yaml

SLO_FILE_SUFFIXES = (".yaml", ".yml", ".json")
_DURATION = re.compile(r"^(\d+)([mhdw])$")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


class SLOError(ValueError):
    """An SLO definition is invalid or uses a feature that is not supported."""


@dataclass(frozen=True)
class SLO:
    name: str
    target: float  # fraction of events that must be good, e.g. 0.999
    window: timedelta  # rolling compliance window
    window_text: str  # as written, e.g. "28d"
    service: str = ""
    display_name: str = ""
    description: str = ""

    @property
    def title(self) -> str:
        return self.display_name or self.name

    @property
    def allowed_failure_ratio(self) -> float:
        return 1.0 - self.target


def parse_duration(text: Any) -> timedelta:
    """Parse '30m', '6h', '7d' or '4w'. Calendar units (M, Q, Y) are not supported."""
    match = _DURATION.match(str(text).strip())
    if not match:
        raise ValueError(
            f"duration {text!r} is not supported; use a whole number followed by m, h, d or w"
        )
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError(f"duration {text!r} must be greater than zero")
    return timedelta(seconds=amount * _UNIT_SECONDS[match.group(2)])


def _target(raw: dict[str, Any], where: str) -> float:
    if raw.get("target") is not None:
        value, label = raw["target"], "target"
    elif raw.get("targetPercent") is not None:
        value, label = raw["targetPercent"], "targetPercent"
    else:
        raise SLOError(f"{where}: no target or targetPercent")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SLOError(f"{where}: {label} must be a number")
    target = float(value) / 100.0 if label == "targetPercent" else float(value)
    if not 0.0 < target < 1.0:
        raise SLOError(
            f"{where}: {label} must be between 0 and {'100' if label == 'targetPercent' else '1'} (exclusive)"
        )
    return target


def _window(text: Any, where: str) -> tuple[timedelta, str]:
    try:
        return parse_duration(text), str(text).strip()
    except ValueError as exc:
        raise SLOError(f"{where}: {exc}") from None


def _from_openslo(doc: dict[str, Any], source: str) -> SLO:
    metadata = doc.get("metadata") or {}
    name = str(metadata.get("name") or "").strip()
    if not name:
        raise SLOError(f"{source}: SLO document has no metadata.name")
    where = f"{source}: SLO {name!r}"
    spec = doc.get("spec") or {}

    method = str(spec.get("budgetingMethod") or "Occurrences")
    if method != "Occurrences":
        raise SLOError(f"{where}: budgetingMethod {method!r} is not supported (only Occurrences)")

    objectives = spec.get("objectives") or []
    if len(objectives) != 1 or not isinstance(objectives[0], dict):
        raise SLOError(f"{where}: exactly one objective is supported, found {len(objectives)}")

    windows = spec.get("timeWindow") or []
    if len(windows) != 1 or not isinstance(windows[0], dict):
        raise SLOError(f"{where}: exactly one timeWindow is required")
    if windows[0].get("isRolling") is False or windows[0].get("calendar"):
        raise SLOError(f"{where}: calendar-aligned time windows are not supported (only rolling)")
    window, window_text = _window(windows[0].get("duration"), where)

    return SLO(
        name=name,
        target=_target(objectives[0], where),
        window=window,
        window_text=window_text,
        service=str(spec.get("service") or ""),
        display_name=str(metadata.get("displayName") or ""),
        description=" ".join(str(spec.get("description") or "").split()),
    )


def _from_short_form(item: Any, source: str) -> SLO:
    if not isinstance(item, dict) or not str(item.get("name") or "").strip():
        raise SLOError(f"{source}: every entry under 'slos' needs a name")
    name = str(item["name"]).strip()
    where = f"{source}: SLO {name!r}"
    if item.get("window") is None:
        raise SLOError(f"{where}: no window")
    window, window_text = _window(item["window"], where)
    return SLO(
        name=name,
        target=_target(item, where),
        window=window,
        window_text=window_text,
        service=str(item.get("service") or ""),
        display_name=str(item.get("displayName") or ""),
        description=" ".join(str(item.get("description") or "").split()),
    )


def _documents(path: Path) -> Iterator[Any]:
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix == ".json":
            loaded = json.loads(text)
            yield from loaded if isinstance(loaded, list) else [loaded]
        else:
            yield from yaml.safe_load_all(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SLOError(f"{path}: cannot parse: {exc}") from None


def load_slo_file(path: Path) -> list[SLO]:
    slos: list[SLO] = []
    for doc in _documents(path):
        if not isinstance(doc, dict):
            continue
        if isinstance(doc.get("slos"), list):
            slos.extend(_from_short_form(item, str(path)) for item in doc["slos"])
        elif doc.get("kind") == "SLO":
            slos.append(_from_openslo(doc, str(path)))
    return slos


def load_slos(path: str) -> list[SLO]:
    """Load every SLO from a file, or from all YAML/JSON files directly inside a directory."""
    root = Path(path)
    if root.is_dir():
        files = sorted(p for p in root.iterdir() if p.is_file() and p.suffix in SLO_FILE_SUFFIXES)
        if not files:
            raise SLOError(f"{root}: no .yaml, .yml or .json files found")
    elif root.is_file():
        files = [root]
    else:
        raise SLOError(f"{root}: no such file or directory")

    slos: list[SLO] = []
    seen: dict[str, Path] = {}
    for file in files:
        for slo in load_slo_file(file):
            if slo.name in seen:
                raise SLOError(f"SLO {slo.name!r} is defined in both {seen[slo.name]} and {file}")
            seen[slo.name] = file
            slos.append(slo)
    if not slos:
        raise SLOError(f"{root}: no SLO definitions found")
    return slos
