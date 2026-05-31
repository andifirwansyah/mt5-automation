# GUIDE: Running AI Trading Automation on Windows

Panduan ini menjelaskan langkah dari **setup PostgreSQL** sampai **bot + API running** di Windows (mode aman: `DRY_RUN=true`, `ACCOUNT_MODE=DEMO_AUTO`).

---

## 1) Prasyarat

Wajib tersedia di Windows machine:

- Python 3.11+ (`python --version`)
- PostgreSQL 14+ (`psql --version`)
- MetaTrader 5 Terminal (desktop)
- Akun MT5 **Demo**

Opsional tapi direkomendasikan:

- Git
- Windows Terminal / PowerShell 7

---

## 2) Clone project dan masuk folder

```powershell
git clone <REPO_URL> ai-trading-automation
cd ai-trading-automation
```

Jika project sudah ada, cukup:

```powershell
cd <path>\ai-trading-automation
```

---

## 3) Setup PostgreSQL

## 3.1 Buat database dan user (contoh)

Login ke `psql` sebagai superuser (misal `postgres`) lalu jalankan:

```sql
CREATE USER trading_user WITH PASSWORD 'trading_password';
CREATE DATABASE ai_trading OWNER trading_user;
GRANT ALL PRIVILEGES ON DATABASE ai_trading TO trading_user;
```

> Kalau mau tetap pakai user `postgres`, boleh. Sesuaikan `DATABASE_URL` nanti.

## 3.2 Test koneksi

```powershell
psql -h localhost -U trading_user -d ai_trading -c "SELECT 1;"
```

---

## 4) Buat virtual environment dan install dependency

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5) Setup environment file

Copy template:

```powershell
copy .env.example .env
```

Lalu edit `.env` (minimal):

- `DATABASE_URL`
- `MT5_PATH`
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`

Contoh aman awal (demo + dry-run):

```env
APP_ENV=production
APP_DEBUG=false

DATABASE_URL=postgresql+psycopg://trading_user:trading_password@localhost:5432/ai_trading

MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_LOGIN=12345678
MT5_PASSWORD=your_demo_password
MT5_SERVER=YourBroker-Demo

ACCOUNT_MODE=DEMO_AUTO
AUTO_TRADE=true
APPROVAL_REQUIRED=false
DRY_RUN=true

TRADING_SYMBOL=XAUUSD
TRADING_TIMEFRAME=M5
```

> `ACCOUNT_MODE=DEMO_AUTO` = execution akan reject jika account terdeteksi bukan demo.

---

## 6) Inisialisasi schema dan migration

Jalankan migration:

```powershell
alembic upgrade head
```

Kalau mau smoke check koneksi DB:

```powershell
python scripts/init_db.py
```

---

## 7) Seed master data

```powershell
python scripts/seed_master_data.py
python scripts/seed_dashboard_user.py --email "youremail@mail.com" --password "Pass234."
```

Script ini akan seed:

- Timeframes (`M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`)
- Symbol default `XAUUSD`
- Strategies:
  - `EMA_ATR_TREND`
  - `VOLATILITY_BREAKOUT`
  - `RANGE_REVERSION`
- Strategy configs default (`lot_size=0.01`)

---

## 8) Validasi koneksi MT5 sebelum start bot

```powershell
python scripts/check_mt5_connection.py
```

Expected output utama:

- `MT5 connected: True`
- version/terminal info tampil
- account login/server/balance/equity tampil
- symbol `XAUUSD` selected
- candle `M5` fetched

Jika gagal konek:

- cek `MT5_PATH` benar
- pastikan terminal MT5 terinstall
- pastikan login demo valid

---

## 9) Jalankan API (Terminal #1)

Pakai script:

```powershell
scripts\run_api.bat
```

Atau manual:

```powershell
.\.venv\Scripts\activate
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Test endpoint health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

---

## 10) Jalankan Bot Worker (Terminal #2)

Pakai script:

```powershell
scripts\run_bot.bat
```

Atau manual:

```powershell
.\.venv\Scripts\activate
python -m src.bot_worker
```

Expected:

- startup sukses
- recovery startup log muncul
- heartbeat update berjalan
- listener polling candle berjalan

---

## 11) Verifikasi runtime safety (dry-run)

Karena `DRY_RUN=true`, sistem harus:

- boleh generate signal/decision
- simpan execution decision ke DB
- **tidak memanggil `mt5.order_send`**

Quick checks:

- lihat `logs/bot_worker.log`
- lihat `logs/execution.log`
- pastikan ada keputusan `DRY_RUN`

---

## 12) Kill switch API test

Aktifkan kill switch:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/bot/kill-switch/activate -ContentType "application/json" -Body '{"reason":"manual_test","actor":"ops"}'
```

Nonaktifkan kill switch:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/bot/kill-switch/deactivate -ContentType "application/json" -Body '{"reason":"resume","actor":"ops"}'
```

Saat kill switch aktif, pipeline harus reject (no execution).

---

## 13) Menjalankan test suite

```powershell
python -m pytest tests/unit tests/integration tests/e2e -q
```

---

## 14) Troubleshooting cepat

## MT5 tidak connect

- Pastikan `MT5_PATH` ke `terminal64.exe` yang benar.
- Pastikan akun login bisa dari MT5 terminal manual.

## `alembic upgrade head` gagal

- Cek `DATABASE_URL`.
- Pastikan DB sudah dibuat.

## Bot start tapi tidak ada event

- Cek symbol di broker (`XAUUSD` mungkin beda suffix, mis. `XAUUSDm`).
- Sesuaikan `TRADING_SYMBOL` di `.env`.

## DRY_RUN tapi tetap ada order live

- Stop bot segera.
- Cek `.env`: `DRY_RUN=true`, `ACCOUNT_MODE=DEMO_AUTO`.
- Cek log execution path.

---

## 15) Stop service

- Di terminal API/Bot: `Ctrl + C`
- Bot akan melakukan graceful shutdown (listener, heartbeat, MT5 shutdown).

---

## Recommended first production-safe profile

Untuk fase awal demo auto-entry:

- `ACCOUNT_MODE=DEMO_AUTO`
- `DRY_RUN=true` (awal)
- `FIXED_LOT=0.01`
- `MAX_OPEN_POSITIONS=1`
- `MAX_TRADES_PER_DAY=5`
- kill switch API siap dipakai

Setelah validasi beberapa hari di dry-run dan semua audit trail bersih, baru evaluasi uji `DRY_RUN=false` tetap di akun demo.
