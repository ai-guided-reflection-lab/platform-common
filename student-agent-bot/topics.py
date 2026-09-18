"""Topic access — plug-and-play JSON (builtin + custom)."""

from topic_store import (
    TopicValidationError,
    delete_custom_topic,
    get_topic,
    import_topic_json,
    list_topics,
    list_topics_detailed,
    reload_topics,
    save_custom_topic,
)

__all__ = [
    "TopicValidationError",
    "delete_custom_topic",
    "get_topic",
    "import_topic_json",
    "list_topics",
    "list_topics_detailed",
    "reload_topics",
    "save_custom_topic",
]
