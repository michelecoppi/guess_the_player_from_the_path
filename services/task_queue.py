"""Durable HTTP work. Deterministic task names deduplicate producer retries."""
import hashlib
import json
import re
from functools import lru_cache

from google.api_core.exceptions import AlreadyExists

import config


@lru_cache(maxsize=1)
def client():
    from google.cloud import tasks_v2
    return tasks_v2.CloudTasksClient()


def validate_configuration():
    if not all((config.TASKS_QUEUE, config.BROADCAST_QUEUE, config.PUBLIC_BASE_URL, config.TASK_SECRET)):
        raise RuntimeError("Configure TASKS_QUEUE, BROADCAST_QUEUE, PUBLIC_BASE_URL and TASK_SECRET")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", config.TASK_SECRET):
        raise RuntimeError("TASK_SECRET must contain 32-256 URL-safe characters")
    if not config.PUBLIC_BASE_URL.startswith("https://"):
        raise RuntimeError("PUBLIC_BASE_URL must use HTTPS for task delivery")


def enqueue(path, payload, key, *, broadcast=False):
    validate_configuration()
    parent = config.BROADCAST_QUEUE if broadcast else config.TASKS_QUEUE
    name = hashlib.sha256(key.encode()).hexdigest()
    task = {
        "name": f"{parent}/tasks/{name}",
        "http_request": {
            "http_method": "POST",
            "url": config.PUBLIC_BASE_URL + path,
            "headers": {"Content-Type": "application/json", "X-Task-Secret": config.TASK_SECRET},
            "body": json.dumps(payload).encode(),
        },
        "dispatch_deadline": {"seconds": 180},
    }
    try:
        client().create_task(request={"parent": parent, "task": task}, timeout=5)
    except AlreadyExists:
        pass
