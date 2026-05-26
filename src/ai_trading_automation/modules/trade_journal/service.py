"""Service layer for writing and reading trade journals."""

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import JournalReadRequest, JournalWriteRequest
from .errors import TradeJournalInputError
from .models import TradeJournalEntry
from .repository import TradeJournalRepository


class TradeJournalService:
    """Persist pipeline decisions into JSONL journal for auditability."""

    def __init__(
        self,
        journal_path: Path | None = None,
        storage_backend: str = "file",
        repository: TradeJournalRepository | None = None,
    ) -> None:
        self._journal_path = journal_path or Path("outputs/journals/trade_journal.jsonl")
        self._storage_backend = storage_backend
        self._repository = repository

        if self._storage_backend == "db" and self._repository is None:
            raise TradeJournalInputError("repository is required when storage_backend='db'.")

        if self._storage_backend not in {"file", "db"}:
            raise TradeJournalInputError("storage_backend must be either 'file' or 'db'.")

    @property
    def journal_path(self) -> Path:
        """Return effective journal path used by service."""
        return self._journal_path

    def write_entry(self, request: JournalWriteRequest) -> TradeJournalEntry:
        """Write one entry and return normalized journal object."""
        self._validate_write_request(request)

        created_at = datetime.now(tz=UTC)
        signal_payload = (
            self._serialize_obj(request.signal_validation.validated_signal)
            if request.signal_validation.validated_signal is not None
            else None
        )
        entry = TradeJournalEntry(
            journal_id=str(uuid4()),
            signal=signal_payload,
            signal_validation=self._serialize_obj(request.signal_validation),
            risk_plan=self._serialize_obj(request.risk_plan),
            simulation_result=self._serialize_obj(request.simulation_result),
            execution_decision=self._serialize_obj(request.execution_decision),
            order_state=self._serialize_obj(request.order_state),
            result=self._serialize_obj(request.result),
            notes=request.notes,
            created_at=created_at,
            closed_at=request.closed_at,
        )

        if self._storage_backend == "db":
            self._repository.save(entry)
        else:
            payload = self._serialize_obj(entry)
            self._journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self._journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        return entry

    def read_entries(self, request: JournalReadRequest | None = None) -> list[TradeJournalEntry]:
        """Read journal entries from JSONL file."""
        read_request = request or JournalReadRequest(journal_path=self._journal_path)
        if self._storage_backend == "db":
            return self._repository.list_entries(limit=read_request.limit)

        if not read_request.journal_path.exists():
            return []

        entries: list[TradeJournalEntry] = []
        with read_request.journal_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                parsed = json.loads(stripped)
                entries.append(self._to_entry(parsed))

        if read_request.limit is not None and read_request.limit >= 0:
            return entries[-read_request.limit :]
        return entries

    def _to_entry(self, payload: dict[str, Any]) -> TradeJournalEntry:
        return TradeJournalEntry(
            journal_id=str(payload["journal_id"]),
            signal=payload.get("signal"),
            signal_validation=dict(payload["signal_validation"]),
            risk_plan=dict(payload["risk_plan"]),
            simulation_result=dict(payload["simulation_result"]),
            execution_decision=dict(payload["execution_decision"]),
            order_state=payload.get("order_state"),
            result=payload.get("result"),
            notes=list(payload.get("notes", [])),
            created_at=datetime.fromisoformat(payload["created_at"]),
            closed_at=datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None,
        )

    def _serialize_obj(self, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {key: self._serialize_obj(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._serialize_obj(item) for item in obj]
        if is_dataclass(obj):
            return self._serialize_obj(asdict(obj))
        if hasattr(obj, "model_dump"):
            return self._serialize_obj(obj.model_dump())
        return obj

    def _validate_write_request(self, request: JournalWriteRequest) -> None:
        if request.signal_validation is None:
            raise TradeJournalInputError("signal_validation must be provided.")
        if request.risk_plan is None:
            raise TradeJournalInputError("risk_plan must be provided.")
        if request.simulation_result is None:
            raise TradeJournalInputError("simulation_result must be provided.")
        if request.execution_decision is None:
            raise TradeJournalInputError("execution_decision must be provided.")
