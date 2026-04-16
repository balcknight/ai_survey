from __future__ import annotations

import json
from typing import Any


def _normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_jsonable(v) for v in value]
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return _normalize_jsonable(value.item())
        except Exception:
            return value
    return value


def to_json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(_normalize_jsonable(value), ensure_ascii=False)


def from_json_text(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
