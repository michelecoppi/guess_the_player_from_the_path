"""Repository abstraction and isolated persistence for Candidate Players.

Garantisce:
- Astrazione repository (CandidatePlayerRepository) per disaccoppiare la logica di dominio;
- Implementazione in-memory (InMemoryCandidatePlayerRepository) veloce e deterministica per test;
- Implementazione file-backed (FileCandidatePlayerRepository) su filesystem locale;
- Totale e rigoroso isolamento da data/players.json (nessuna scrittura sul dataset di produzione);
- Scritture atomiche su file per prevenire corruzioni di dati in caso di interruzione.
"""
from __future__ import annotations

import abc
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from services.candidate_player import CandidatePlayer, CandidateState


class CandidateRepositoryError(Exception):
    """Eccezione base per errori del repository dei candidati."""


class CandidatePlayerRepository(abc.ABC):
    """Interfaccia astratta del repository per il ciclo di vita dei candidati calciatori."""

    @abc.abstractmethod
    def save(self, candidate: CandidatePlayer) -> None:
        """Salva o aggiorna un candidato."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_id(self, candidate_id: str) -> Optional[CandidatePlayer]:
        """Recupera un candidato per ID univoco, o None se inesistente."""
        raise NotImplementedError

    @abc.abstractmethod
    def exists(self, candidate_id: str) -> bool:
        """Verifica l'esistenza di un candidato per ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> list[CandidatePlayer]:
        """Restituisce tutti i candidati con ordinamento deterministico."""
        raise NotImplementedError

    @abc.abstractmethod
    def find_by_state(
        self,
        state: CandidateState | str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[CandidatePlayer]:
        """Filtra i candidati per stato del ciclo di vita."""
        raise NotImplementedError

    @abc.abstractmethod
    def count(self, state: Optional[CandidateState | str] = None) -> int:
        """Restituisce il numero totale di candidati, o di candidati in uno stato specifico."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, candidate_id: str) -> bool:
        """Elimina un candidato per ID. Ritorna True se rimosso, False se non trovato."""
        raise NotImplementedError


class InMemoryCandidatePlayerRepository(CandidatePlayerRepository):
    """Implementazione in-memory veloce e isolata, ideale per test unitari deterministici."""

    def __init__(self) -> None:
        self._storage: dict[str, dict] = {}

    def save(self, candidate: CandidatePlayer) -> None:
        # Serializza a dizionario per garantire isolamento da modifiche per riferimento
        self._storage[candidate.candidate_id] = candidate.to_dict()

    def get_by_id(self, candidate_id: str) -> Optional[CandidatePlayer]:
        data = self._storage.get(candidate_id)
        if data is None:
            return None
        return CandidatePlayer.from_dict(copy.deepcopy(data))

    def exists(self, candidate_id: str) -> bool:
        return candidate_id in self._storage

    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> list[CandidatePlayer]:
        # Ordinamento deterministico per candidate_id
        sorted_keys = sorted(self._storage.keys())
        sliced = sorted_keys[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return [CandidatePlayer.from_dict(copy.deepcopy(self._storage[k])) for k in sliced]

    def find_by_state(
        self,
        state: CandidateState | str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[CandidatePlayer]:
        target_state = state if isinstance(state, CandidateState) else CandidateState(state)
        matching = [
            CandidatePlayer.from_dict(copy.deepcopy(data))
            for k, data in sorted(self._storage.items())
            if data.get("status") == target_state.value
        ]
        sliced = matching[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return sliced

    def count(self, state: Optional[CandidateState | str] = None) -> int:
        if state is None:
            return len(self._storage)
        target_state = state if isinstance(state, CandidateState) else CandidateState(state)
        return sum(1 for data in self._storage.values() if data.get("status") == target_state.value)

    def delete(self, candidate_id: str) -> bool:
        if candidate_id in self._storage:
            del self._storage[candidate_id]
            return True
        return False

    def clear(self) -> None:
        """Svuota completamente il repository in memoria."""
        self._storage.clear()


class FileCandidatePlayerRepository(CandidatePlayerRepository):
    """Implementazione su filesystem con un file JSON per candidato.

    Garantisce:
    - Scrittura atomica per prevenire file troncati;
    - Isolamento rigoroso: rifiuta esplicitamente percorsi coincidenti con data/players.json;
    - Formato JSON con indentazione a 2 spazi e senza escape ASCII;
    - Determinismo e serializzazione/deserializzazione completa.
    """

    DEFAULT_DIR = Path("data") / "candidates"

    def __init__(self, storage_dir: Optional[Path | str] = None) -> None:
        raw_path = Path(storage_dir) if storage_dir is not None else self.DEFAULT_DIR
        self._dir = raw_path.resolve()

        # Guard di sicurezza fondamentale: impedisce categoricamente di puntare
        # a data/players.json o di salvare candidati dentro il file di produzione.
        self._assert_storage_isolated(self._dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _assert_storage_isolated(cls, resolved_dir: Path) -> None:
        """Verifica che la directory di storage non coincida né contenga il dataset di produzione."""
        # Percorso canonico di data/players.json
        base_repo = Path(__file__).resolve().parents[2]
        prod_file = (base_repo / "data" / "players.json").resolve()

        if resolved_dir == prod_file or resolved_dir.name.lower() == "players.json":
            raise CandidateRepositoryError(
                f"Violazione di sicurezza: il repository candidati non puo' puntare al file di produzione: {prod_file}"
            )

    def _file_path(self, candidate_id: str) -> Path:
        # Sanificazione del candidate_id per prevenire path traversal
        clean_id = Path(candidate_id).name
        if clean_id != candidate_id or ".." in candidate_id or "/" in candidate_id or "\\" in candidate_id:
            raise ValueError(f"candidate_id non valido per il filesystem: '{candidate_id}'")
        return self._dir / f"{clean_id}.json"

    def save(self, candidate: CandidatePlayer) -> None:
        """Salva il candidato su file JSON in modo atomico."""
        dest_path = self._file_path(candidate.candidate_id)

        # Scrittura atomica: crea file temporaneo nella stessa cartella e poi esegue replace
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            prefix=f".tmp_{candidate.candidate_id}_",
            suffix=".json",
            dir=str(self._dir),
        )
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(candidate.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path_str, str(dest_path))
        except Exception:
            if os.path.exists(tmp_path_str):
                try:
                    os.unlink(tmp_path_str)
                except OSError:
                    pass
            raise

    def get_by_id(self, candidate_id: str) -> Optional[CandidatePlayer]:
        path = self._file_path(candidate_id)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CandidatePlayer.from_dict(data)

    def exists(self, candidate_id: str) -> bool:
        try:
            return self._file_path(candidate_id).is_file()
        except ValueError:
            return False

    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> list[CandidatePlayer]:
        files = sorted(self._dir.glob("*.json"))
        # Esclude file temporanei o nascosti
        valid_files = [f for f in files if not f.name.startswith(".")]
        sliced = valid_files[offset:]
        if limit is not None:
            sliced = sliced[:limit]

        results = []
        for path in sliced:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(CandidatePlayer.from_dict(data))
        return results

    def find_by_state(
        self,
        state: CandidateState | str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[CandidatePlayer]:
        target_state = state if isinstance(state, CandidateState) else CandidateState(state)
        all_candidates = self.list_all()
        matching = [c for c in all_candidates if c.status == target_state]
        sliced = matching[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return sliced

    def count(self, state: Optional[CandidateState | str] = None) -> int:
        if state is None:
            files = [f for f in self._dir.glob("*.json") if not f.name.startswith(".")]
            return len(files)
        target_state = state if isinstance(state, CandidateState) else CandidateState(state)
        return len(self.find_by_state(target_state))

    def delete(self, candidate_id: str) -> bool:
        try:
            path = self._file_path(candidate_id)
        except ValueError:
            return False
        if path.is_file():
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return False
        return False
