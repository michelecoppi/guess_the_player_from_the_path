"""Cross-platform and thread/process-safe file lock utility (#15).

Provides process-level and thread-level mutual exclusion using OS advisory file locks
(msvcrt on Windows, fcntl on Unix) combined with threading.RLock.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional


class ProcessFileLock:
    """Lock cross-platform per processi e thread per garantire l'accesso esclusivo a risorse su file."""

    _thread_locks: dict[str, threading.RLock] = {}
    _local = threading.local()
    _meta_lock = threading.Lock()

    def __init__(
        self,
        lock_path: Path | str,
        timeout: float = 10.0,
        poll_interval: float = 0.02,
    ) -> None:
        self.lock_path = Path(lock_path).resolve()
        self.timeout = max(0.1, float(timeout))
        self.poll_interval = max(0.005, float(poll_interval))
        self._fd: Optional[int] = None

        key = str(self.lock_path)
        with self._meta_lock:
            if key not in self._thread_locks:
                self._thread_locks[key] = threading.RLock()
            self._thread_lock = self._thread_locks[key]

    def acquire(self) -> bool:
        """Acquisisce il lock sul thread e successivamente a livello di sistema operativo.

        Supporta la re-entrancy trasparente sullo stesso thread.
        Ritorna True se acquisito con successo entro il timeout specificato, False altrimenti.
        """
        key = str(self.lock_path)
        held = getattr(self._local, "held", None)
        if held is None:
            held = {}
            self._local.held = held

        count = held.get(key, 0)
        if count > 0:
            held[key] = count + 1
            return True

        start = time.time()
        if not self._thread_lock.acquire(timeout=self.timeout):
            return False

        remaining = max(0.05, self.timeout - (time.time() - start))
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT)
        except Exception:
            self._thread_lock.release()
            return False

        start_os = time.time()
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held[key] = 1
                return True
            except (OSError, IOError):
                if time.time() - start_os >= remaining:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None
                    self._thread_lock.release()
                    return False
                time.sleep(self.poll_interval)

    def release(self) -> None:
        """Rilascia il lock di sistema operativo e successivamente il lock sul thread."""
        key = str(self.lock_path)
        held = getattr(self._local, "held", None)
        if held and key in held:
            if held[key] > 1:
                held[key] -= 1
                return
            del held[key]

        if self._fd is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(self._fd, 0, os.SEEK_SET)
                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    except (OSError, IOError):
                        pass
                else:
                    import fcntl

                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_UN)
                    except (OSError, IOError):
                        pass
            finally:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
        try:
            self._thread_lock.release()
        except RuntimeError:
            pass

    def __enter__(self) -> ProcessFileLock:
        if not self.acquire():
            raise TimeoutError(f"Impossibile acquisire il lock esclusivo su {self.lock_path} entro {self.timeout}s.")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
