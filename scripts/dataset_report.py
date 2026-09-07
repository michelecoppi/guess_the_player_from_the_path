"""Stampa lo stato di salute del dataset calciatori.

    python scripts/dataset_report.py
    python scripts/dataset_report.py --strict   # esce con codice 1 se il dataset ha errori (usato in CI)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.dataset_health import build_report, format_report_text  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Report sullo stato del dataset calciatori")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="esce con codice 1 se ci sono problemi di integrita' nel dataset",
    )
    args = parser.parse_args()

    report = build_report()
    print(format_report_text(report))

    if args.strict and report["dataset_problems"]:
        print("\nDataset non valido: correggi i problemi elencati sopra.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
