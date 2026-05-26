# AI Trading Automation

Project ini adalah sistem backend dan engine untuk trading automation XAUUSD berbasis data OHLCV multi-timeframe.

Project ini **belum masuk fase live trading real money**. Fase awal fokus ke engine, kontrak data, validasi, risk control, paper execution, journal, dan performance analyzer.

## Quick Start

### 1) Prerequisites

- Python 3.11+
- MySQL berjalan di lokal (default: `127.0.0.1:3306`)
- Dataset OHLCV tersedia di folder `dataset/{D1,H4,H1,M30,M15,M5}`

### 2) Setup environment

Buat virtualenv dan install dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### 3) Konfigurasi `.env`

Pastikan `.env` terisi minimal:

```env
DB_CONNECTION=mysql
DATABASE_URL=mysql+pymysql://root:%40Andi12345@127.0.0.1:3306/ai_trading_automation?charset=utf8mb4

TRADE_JOURNAL_BACKEND=db
PAPER_EXECUTION_BACKEND=db
STRICT_DB_RUNTIME=true

TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
```

> `STRICT_DB_RUNTIME=true` artinya app wajib terkoneksi DB saat startup (tanpa fallback memory/file).

### 4) Jalankan migration

```bash
alembic -c alembic.ini upgrade head
```

Verifikasi migration:

```bash
alembic -c alembic.ini current
```

### 5) Jalankan API

```bash
uvicorn ai_trading_automation.api.app:app --reload --app-dir src
```

Atau lebih singkat:

```bash
make run
```

---

## Endpoint Utama (Simulasi Manual)

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Pipeline status

```bash
curl http://127.0.0.1:8000/pipeline/status
```

### Trigger simulasi trading (manual)

```bash
curl -X POST "http://127.0.0.1:8000/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_path": "dataset",
    "symbol": "XAUUSD",
    "timeframe": "H1",
    "account_balance": 10000,
    "requested_risk_percent": 0.5,
    "daily_realized_loss": 0.0,
    "open_positions_count": 0,
    "persist_performance_report": true
  }'
```

### Lihat hasil run terakhir

```bash
curl http://127.0.0.1:8000/pipeline/last-run
```

---

## Testing

Jalankan seluruh test:

```bash
pytest tests -q
```

Atau:

```bash
make test
```

Atau test targeted:

```bash
pytest tests/api tests/core tests/trade_journal tests/paper_execution -q
```

---

## Output & Persisted Artifacts

- Journal file mode (jika backend `file`):
  - `outputs/journals/trade_journal.jsonl`
- Performance report file:
  - `outputs/reports/performance_report.json`
- DB mode (recommended):
  - tabel `pipeline_runs`
  - tabel `trade_journal_entries`
  - tabel `paper_orders`

---

## Troubleshooting

### 1) Error startup saat strict mode

Jika `STRICT_DB_RUNTIME=true`, app akan gagal start jika DB tidak siap.

Cek:
- MySQL aktif
- `DATABASE_URL` benar
- migration sudah dijalankan

### 2) Error Alembic terkait URL `%`

Gunakan password URL-encoded (`@` -> `%40`) pada `DATABASE_URL`.

### 3) Pipeline gagal di stage market_data/validation

Pastikan dataset timeframe dan format OHLCV valid.

## Cara Kerja AI-Workspace

Semua dokumen AI project disimpan di folder:

```txt
.ai/
```

Source code disimpan di folder:

```txt
src/
tests/
```

AI agent tidak boleh membuat file sembarangan di root project. Jika perlu membuat/mengubah file, agent wajib mengikuti:

```txt
AGENTS.md
.ai/project-map.md
.ai/docs/02-feature-boundary.md
.ai/task-list.md
```

## Fase Awal

1. Bootstrap project
2. Dataset loader
3. OHLCV validation
4. Market regime engine
5. Strategy selector
6. Strategy engine shell
7. Signal contract
8. Signal validator
9. Risk engine
10. Pre-trade simulation
11. Execution gate
12. Paper execution engine
13. Position monitor
14. Trade journal
15. Performance analyzer
16. API service shell

## Prinsip Utama

- Jangan live trading dulu.
- Jangan prediction-first.
- Semua sinyal harus melewati validator, risk engine, simulation, dan execution gate.
- Semua keputusan harus bisa dijelaskan dan dicatat.
- Semua module punya boundary yang jelas.
