"""Firestore backup, validation and restore (#50).

One package shared by `scripts/backup_firestore.py`, `scripts/restore_firestore.py`, the
unit tests and the emulator round-trip test, so the file that the weekly workflow writes is
decoded by exactly the code a disaster recovery would run. Procedure and policy live in
docs/backup-recovery.md.

- `inventory`: the one classification of every top-level Firestore collection.
- `codec`: typed, reversible JSON encoding of Firestore values.
- `archive`: the backup file format (v2), its validation and the v1 upgrade.
- `exporter`: reads Firestore into an archive.
- `restore`: target safety guard, restore planning/apply and post-restore verification.
"""
