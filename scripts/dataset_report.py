"""Stampa lo stato di salute del dataset calciatori.

    python scripts/dataset_report.py
    python scripts/dataset_report.py --strict    # esce con codice 1 se il dataset ha errori (usato in CI)
    python scripts/dataset_report.py --pending   # le schede in attesa di revisione, carriera compresa
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.dataset_health import build_report, format_report_text  # noqa: E402
from services.difficulty import compute_difficulty, compute_difficulty_score  # noqa: E402
from services.player_pool import _load_raw_players, validate_player  # noqa: E402


def format_pending_text(players):
    """Le schede da approvare, stampate per intero.

    /admin_review e la dashboard dicono *chi* e' escluso e perche', ma non mostrano la
    carriera: per decidere se una scheda e' giusta bisogna vedere le tappe, ed e' l'unica
    cosa che serve davvero prima di marcarla verificata.
    """
    if not players:
        return "Nessuna scheda in attesa di revisione."

    lines = [f"Schede da rivedere: {len(players)}", ""]
    for player in players:
        problems = validate_player(player)
        difficulty = compute_difficulty(player)
        lines.append(
            f"{player.get('full_name')} ({player.get('id')}) - "
            f"popolarita' {player.get('popularity')}, "
            f"{difficulty} ({round(compute_difficulty_score(player), 2)})"
        )
        for entry in player.get("career", []):
            end = entry.get("end_year") or "oggi"
            lines.append(
                f"    {entry.get('start_year')}-{end}  {entry.get('team')} "
                f"({entry.get('country')}, {entry.get('league')})"
            )
        if problems:
            lines.append("    !! " + "; ".join(problems))
        lines.append("")

    lines.append("Per approvarle tutte, reimporta il batch con --update --verified.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Report sullo stato del dataset calciatori")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="esce con codice 1 se ci sono problemi di integrita' nel dataset",
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="elenca le schede non ancora verificate con la carriera completa, per rivederle",
    )
    args = parser.parse_args()

    if args.pending:
        pending = [p for p in _load_raw_players() if not p.get("verified", False)]
        print(format_pending_text(pending))
        return 0

    report = build_report()
    print(format_report_text(report))

    if args.strict and report["dataset_problems"]:
        print("\nDataset non valido: correggi i problemi elencati sopra.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
