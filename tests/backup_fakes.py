"""In-memory stand-in for the parts of the Firestore client the backup package uses.

Only for unit tests of planning/guard logic; the real behaviour is proven against the emulator
in tests/test_backup_restore_emulator.py.
"""
from __future__ import annotations

from types import SimpleNamespace

from google.api_core.exceptions import AlreadyExists


class FakeClient:
    def __init__(self, project="demo-fake", docs=None):
        self.project = project
        self.docs = {tuple(path.split("/")): dict(fields) for path, fields in (docs or {}).items()}
        self.commits = 0

    def collections(self):
        return [FakeCollection(self, (name,)) for name in sorted({path[0] for path in self.docs})]

    def collection(self, name):
        return FakeCollection(self, (name,))

    def document(self, *path):
        return FakeDocument(self, tuple(path))

    def get_all(self, references):
        for reference in references:
            fields = self.docs.get(reference.segments)
            yield SimpleNamespace(reference=reference, exists=fields is not None,
                                  to_dict=lambda fields=fields: dict(fields) if fields is not None else None)

    def batch(self):
        return FakeBatch(self)


class FakeCollection:
    def __init__(self, client, segments):
        self.client, self.segments, self.id = client, segments, segments[-1]

    def list_documents(self, page_size=None):
        depth = len(self.segments)
        ids = sorted({path[depth] for path in self.client.docs
                      if len(path) > depth and path[:depth] == self.segments})
        return iter([FakeDocument(self.client, self.segments + (doc_id,)) for doc_id in ids])


class FakeDocument:
    def __init__(self, client, segments):
        self.client, self.segments, self.id = client, segments, segments[-1]
        self.path = "/".join(segments)

    def collections(self):
        depth = len(self.segments)
        names = sorted({path[depth] for path in self.client.docs
                        if len(path) > depth + 1 and path[:depth] == self.segments})
        return [FakeCollection(self.client, self.segments + (name,)) for name in names]


class FakeBatch:
    def __init__(self, client):
        self.client, self.ops = client, []

    def create(self, reference, fields):
        self.ops.append(("create", reference.segments, fields))

    def set(self, reference, fields):
        self.ops.append(("set", reference.segments, fields))

    def commit(self):
        if any(op == "create" and path in self.client.docs for op, path, _ in self.ops):
            raise AlreadyExists("document exists")
        for _, path, fields in self.ops:
            self.client.docs[path] = dict(fields)
        self.client.commits += 1
