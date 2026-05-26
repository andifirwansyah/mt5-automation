"""Repository layer for paper execution persistence."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import PaperOrder


class PaperExecutionBase(DeclarativeBase):
    """Declarative base for paper execution persistence."""


class PaperOrderRecord(PaperExecutionBase):
    """SQLAlchemy model for paper orders."""

    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    signal_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    direction: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    lot_size: Mapped[float] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperOrderRepository:
    """Persistence repository for paper orders."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_tables(self) -> None:
        """Create DB tables for paper execution module."""
        engine = self._session_factory.kw["bind"]
        PaperExecutionBase.metadata.create_all(bind=engine)

    def save(self, order: PaperOrder) -> PaperOrder:
        """Persist one paper order into DB."""
        with self._session_factory() as session:
            record = PaperOrderRecord(
                order_id=order.order_id,
                signal_id=order.signal_id,
                run_id=None,
                symbol=order.symbol,
                timeframe=order.timeframe,
                direction=order.direction,
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                lot_size=order.lot_size,
                status=order.status,
                created_at=order.created_at,
                updated_at=order.updated_at,
                closed_at=order.closed_at,
            )
            session.add(record)
            session.commit()
        return order

    def get_by_order_id(self, order_id: str) -> PaperOrder | None:
        """Read one paper order by public order_id."""
        with self._session_factory() as session:
            record = (
                session.query(PaperOrderRecord)
                .filter(PaperOrderRecord.order_id == order_id)
                .first()
            )

        if record is None:
            return None
        return self._to_model(record)

    def update_status(
        self,
        order_id: str,
        status: str,
        updated_at: datetime,
        closed_at: datetime | None,
    ) -> None:
        """Update persisted order status by order_id."""
        with self._session_factory() as session:
            record = (
                session.query(PaperOrderRecord)
                .filter(PaperOrderRecord.order_id == order_id)
                .first()
            )
            if record is None:
                return

            record.status = status
            record.updated_at = updated_at
            record.closed_at = closed_at
            session.commit()

    def _to_model(self, record: PaperOrderRecord) -> PaperOrder:
        return PaperOrder(
            order_id=record.order_id,
            signal_id=record.signal_id,
            symbol=record.symbol,
            timeframe=record.timeframe,
            direction=record.direction,
            entry_price=float(record.entry_price) if record.entry_price is not None else None,
            stop_loss=float(record.stop_loss) if record.stop_loss is not None else None,
            take_profit=float(record.take_profit) if record.take_profit is not None else None,
            lot_size=float(record.lot_size),
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            closed_at=record.closed_at,
        )
