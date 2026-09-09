"""Bounded, thread-safe per-process token buckets (no database reads)."""
import math
import time
from collections import OrderedDict
from threading import Lock


class TokenBucket:
    def __init__(self, capacity=30, refill=0.5, max_users=10000, clock=time.monotonic):
        self.capacity = capacity
        self.refill = refill
        self.max_users = max_users
        self.clock = clock
        self._users = OrderedDict()
        self._lock = Lock()

    def retry_after(self, user_id, cost=1):
        with self._lock:
            now = self.clock()
            tokens, previous = self._users.pop(user_id, (self.capacity, now))
            tokens = min(self.capacity, tokens + max(0, now - previous) * self.refill)
            wait = max(0, math.ceil((cost - tokens) / self.refill))
            self._users[user_id] = (tokens if wait else tokens - cost, now)
            while len(self._users) > self.max_users:
                self._users.popitem(last=False)
            return wait
