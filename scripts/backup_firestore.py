"""Export Firestore in un file JSON tipizzato e validato (formato v2, vedi docs/backup-recovery.md).

Perche' non l'export gestito di Firestore: quello richiede il piano Blaze e un bucket. Il
database e' piccolo e un JSON per volta e' un backup che si legge, si mette in un artifact di
GitHub Actions e si ripristina con `scripts/restore_firestore.py`.

Cosa si esporta lo decide `services/firestore_backup/inventory.py`, non questo script: tutte le
collezioni durevoli con le loro sotto-collezioni (anche quelle sotto un documento padre che
non esiste piu'), e nessuno stato effimero (`work_receipts`, `update_locks`). Una collezione
che nessuno ha classificato viene esportata lo stesso e segnalata.

Il file si scrive come `.partial`, si rilegge dal disco, si valida per intero (struttura,
conteggi, digest, decodifica di ogni valore) e solo allora prende il nome definitivo: un
export non valido non lascia dietro un file che sembra un backup.

    python scripts/backup_firestore.py                                   # in backup/, credenziali del bot
    python scripts/backup_firestore.py --out /tmp --quiet                # stampa solo il percorso
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8571 python scripts/backup_firestore.py --project demo-gtp
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import observability  # noqa: E402
from services.firestore_backup import archive, exporter, restore  # noqa: E402

DEFAULT_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")


def source_client(project: str | None):
    """(client, project, emulator?). The emulator needs an explicit project; otherwise the
    bot's own credentials (key file or ADC, e.g. Workload Identity Federation) are used."""
    if os.environ.get(restore.EMULATOR_ENV):
        if not project:
            raise SystemExit("--project is required with FIRESTORE_EMULATOR_HOST")
        from google.cloud import firestore

        return firestore.Client(project=project), project, True
    from services import firebase_service

    client = firebase_service.db
    if project and client.project != project:
        raise SystemExit(f"credentials resolve project {client.project!r}, not {project!r}")
    return client, client.project, False


def write_archive(backup: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = os.path.join(out_dir, f"firestore-{backup['source_project']}-{stamp}.json")
    partial = final + ".partial"
    with open(partial, "w", encoding="utf-8") as handle:
        json.dump(backup, handle, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
    try:
        archive.require_valid(partial)
    except Exception:
        os.remove(partial)
        raise
    os.replace(partial, final)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Esporta Firestore in un backup JSON v2 validato")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="cartella di destinazione")
    parser.add_argument("--project", help="progetto atteso (obbligatorio con l'emulatore)")
    parser.add_argument("--collections", nargs="*", help="solo queste collezioni (backup parziale)")
    parser.add_argument("--quiet", action="store_true", help="stampa solo il percorso del file")
    args = parser.parse_args(argv)

    observability.init("backup")
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    client, project, emulator = source_client(args.project)
    try:
        backup = exporter.export_archive(client, source_project=project, source_emulator=emulator,
                                         requested=args.collections)
        path = write_archive(backup, args.out)
    except archive.BackupValidationError as exc:
        observability.log_event("backup.export.invalid", 40, component="backup", errors=len(exc.report.errors))
        print("BACKUP NON VALIDO, nessun file scritto:", file=sys.stderr)
        for error in exc.report.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    except (exporter.ExportError, ValueError) as exc:
        print(f"BACKUP FALLITO: {exc}", file=sys.stderr)
        return 1

    observability.log_event("backup.export.written", component="backup", total_documents=backup["total_documents"],
                            complete=backup["complete"], unclassified=len(backup["inventory"]["unclassified"]))
    if not args.quiet:
        meta = archive.summary(backup)
        print(json.dumps({key: meta[key] for key in ("format_version", "created_at", "source_project", "complete",
                                                     "document_counts", "total_documents")}, indent=1))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
