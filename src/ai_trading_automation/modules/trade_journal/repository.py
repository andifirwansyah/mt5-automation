"""Repository layer for trade journal persistence."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import TradeJournalEntry


class TradeJournalBase(DeclarativeBase):
    """Declarative base for trade_journal persistence models."""


class TradeJournalRecord(TradeJournalBase):
    """SQLAlchemy model for trade journal entries."""

    __tablename__ = "trade_journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journal_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signal_validation: Mapped[dict] = mapped_column(JSON)
    risk_plan: Mapped[dict] = mapped_column(JSON)
    simulation_result: Mapped[dict] = mapped_column(JSON)
    execution_decision: Mapped[dict] = mapped_column(JSON)
    order_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeJournalRepository:
    """Persistence repository for TradeJournalEntry objects."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_tables(self) -> None:
        """Create DB tables for trade journal module."""
        engine = self._session_factory.kw["bind"]
        TradeJournalBase.metadata.create_all(bind=engine)

    def save(self, entry: TradeJournalEntry) -> TradeJournalEntry:
        """Persist one journal entry and return normalized object."""
        with self._session_factory() as session:
            record = TradeJournalRecord(
                journal_id=entry.journal_id,
                signal=entry.signal,
                signal_validation=entry.signal_validation,
                risk_plan=entry.risk_plan,
                simulation_result=entry.simulation_result,
                execution_decision=entry.execution_decision,
                order_state=entry.order_state,
                result=entry.result,
                notes=entry.notes,
                created_at=entry.created_at,
                closed_at=entry.closed_at,
            )
            session.add(record)
            session.commit()
        return entry

    def list_entries(self, limit: int | None = None) -> list[TradeJournalEntry]:
        """Read journal entries from DB ordered by insert id."""
        with self._session_factory() as session:
            query = session.query(TradeJournalRecord).order_by(TradeJournalRecord.id.asc())
            records = query.all()

        entries = [self._to_entry(record) for record in records]
        if limit is not None and limit >= 0:
            return entries[-limit:]
        return entries

    def _to_entry(self, record: TradeJournalRecord) -> TradeJournalEntry:
        return TradeJournalEntry(
            journal_id=record.journal_id,
            signal=record.signal,
            signal_validation=record.signal_validation,
            risk_plan=record.risk_plan,
            simulation_result=record.simulation_result,
            execution_decision=record.execution_decision,
            order_state=record.order_state,
            result=record.result,
            notes=list(record.notes),
            created_at=record.created_at,
            closed_at=record.closed_at,
        )
