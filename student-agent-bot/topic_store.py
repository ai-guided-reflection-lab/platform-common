"""Load, validate, and persist plug-and-play topic JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data" / "topics"
BUILTIN_DIR = DATA_DIR / "builtin"
CUSTOM_DIR = DATA_DIR / "custom"

REQUIRED_KEYS = {
    "id",
    "name",
    "resource",
    "alt_resource",
    "practice_label",
    "practice_prompt",
    "practice_stages",
    "final_example",
}

_cache: dict[str, dict] | None = None


class TopicValidationError(ValueError):
    pass


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "topic"


def validate_topic(data: dict, *, allow_missing_id: bool = False) -> dict:
    if not isinstance(data, dict):
        raise TopicValidationError("Topic must be a JSON object")

    topic = dict(data)

    if not allow_missing_id and not topic.get("id"):
        raise TopicValidationError("Missing required field: id")

    if allow_missing_id and not topic.get("id"):
        if not topic.get("name"):
            raise TopicValidationError("Topic needs id or name")
        topic["id"] = _slugify(topic["name"])

    topic["id"] = _slugify(str(topic["id"]))

    missing = REQUIRED_KEYS - set(topic.keys())
    if missing:
        raise TopicValidationError(f"Missing required fields: {', '.join(sorted(missing))}")

    for key in ("resource", "alt_resource"):
        block = topic[key]
        if not isinstance(block, dict) or not block.get("title") or not block.get("url"):
            raise TopicValidationError(f"{key} must have title and url")

    if not isinstance(topic["practice_stages"], list) or not topic["practice_stages"]:
        raise TopicValidationError("practice_stages must be a non-empty list")

    for i, stage in enumerate(topic["practice_stages"]):
        if not isinstance(stage, dict) or not stage.get("label") or not stage.get("focus"):
            raise TopicValidationError(f"practice_stages[{i}] needs label and focus")

    raw_questions = topic.get("check_questions") or []
    if raw_questions and not isinstance(raw_questions, list):
        raise TopicValidationError("check_questions must be a list if present")
    topic["check_questions"] = [str(q).strip() for q in raw_questions if str(q).strip()]

    raw_options = topic.get("practice_options") or []
    if raw_options and not isinstance(raw_options, list):
        raise TopicValidationError("practice_options must be a list if present")
    topic["practice_options"] = [str(o).strip() for o in raw_options if str(o).strip()]

    topic["practice_stages"] = [
        {"label": str(s["label"]).strip(), "focus": str(s["focus"]).strip()}
        for s in topic["practice_stages"]
    ]

    topic["name"] = str(topic["name"]).strip()
    topic["practice_label"] = str(topic["practice_label"]).strip()
    topic["practice_prompt"] = str(topic["practice_prompt"]).strip()
    topic["final_example"] = str(topic["final_example"]).strip()

    if "number" not in topic:
        topic["number"] = 100

    return topic


def _load_dir(directory: Path, builtin: bool) -> dict[str, dict]:
    topics: dict[str, dict] = {}
    if not directory.exists():
        return topics

    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        topic = validate_topic(raw)
        topic["builtin"] = builtin
        topic["_source_path"] = str(path)
        if topic["id"] in topics:
            raise TopicValidationError(f"Duplicate topic id: {topic['id']}")
        topics[topic["id"]] = topic
    return topics


def reload_topics() -> dict[str, dict]:
    global _cache
    merged = _load_dir(BUILTIN_DIR, builtin=True)
    custom = _load_dir(CUSTOM_DIR, builtin=False)

    overlap = set(merged) & set(custom)
    if overlap:
        raise TopicValidationError(
            f"Custom topics cannot override built-in ids: {', '.join(sorted(overlap))}"
        )

    merged.update(custom)
    _cache = merged
    return merged


def all_topics() -> dict[str, dict]:
    global _cache
    if _cache is None:
        reload_topics()
    assert _cache is not None
    return _cache


def get_topic(topic_id: str) -> dict:
    topics = all_topics()
    if topic_id not in topics:
        raise KeyError(f"Unknown topic: {topic_id}")
    return topics[topic_id]


def list_topics() -> list[dict]:
    return [
        {
            "id": topic["id"],
            "number": topic.get("number", 100),
            "name": topic["name"],
            "resource": topic["resource"],
            "builtin": topic.get("builtin", False),
        }
        for topic in sorted(
            all_topics().values(),
            key=lambda t: (not t.get("builtin", False), t.get("number", 100)),
        )
    ]


def list_topics_detailed() -> list[dict]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "number": t.get("number", 100),
            "builtin": t.get("builtin", False),
            "practice_label": t["practice_label"],
            "practice_options": t.get("practice_options") or [],
            "practice_stages_count": len(t["practice_stages"]),
        }
        for t in sorted(all_topics().values(), key=lambda x: (not x.get("builtin", False), x.get("number", 100)))
    ]


def save_custom_topic(data: dict) -> dict:
    topic = validate_topic(data, allow_missing_id=True)
    if topic["id"] in {t["id"] for t in _load_dir(BUILTIN_DIR, True).values()}:
        raise TopicValidationError(f"Cannot overwrite built-in topic: {topic['id']}")

    existing_custom = _load_dir(CUSTOM_DIR, False)
    if topic["id"] not in existing_custom:
        used_numbers = [t.get("number", 100) for t in all_topics().values()]
        topic["number"] = max(used_numbers, default=99) + 1

    topic["builtin"] = False
    path = CUSTOM_DIR / f"{topic['id']}.json"
    payload = {k: v for k, v in topic.items() if not k.startswith("_")}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    reload_topics()
    return get_topic(topic["id"])


def delete_custom_topic(topic_id: str) -> None:
    topic_id = _slugify(topic_id)
    topic = get_topic(topic_id)
    if topic.get("builtin"):
        raise TopicValidationError(f"Built-in topic cannot be deleted: {topic_id}")

    path = CUSTOM_DIR / f"{topic_id}.json"
    if path.exists():
        path.unlink()
    reload_topics()


def import_topic_json(raw: dict | list) -> list[dict]:
    items = raw if isinstance(raw, list) else raw.get("topics", [raw])
    if not isinstance(items, list):
        raise TopicValidationError("JSON must be a topic object or { \"topics\": [...] }")

    saved = []
    for item in items:
        saved.append(save_custom_topic(item))
    return saved

# Load on import
reload_topics()
