# AI Trading Automation (Bootstrap)

Bootstrap project untuk AI Trading Automation production-grade berbasis Python, FastAPI, PostgreSQL, dan MetaTrader 5.

## 1) Setup Virtual Environment (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Konfigurasi Environment

Copy file `.env.example` menjadi `.env`, lalu sesuaikan nilainya:

```powershell
copy .env.example .env
```

Hal yang paling penting disesuaikan:

- `DATABASE_URL`
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `MT5_PATH`

Mode awal aman:

- `DRY_RUN=true`
- `AUTO_TRADE=true`
- `APPROVAL_REQUIRED=false`

## 3) Menjalankan Bot Worker

```powershell
python -m src.bot_worker
```

Atau via script:

```powershell
scripts\run_bot.bat
```

## 4) Menjalankan API Server

```powershell
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Atau via script:

```powershell
scripts\run_api.bat
```

## 5) Struktur Project

```text
src/
├── bot_worker.py
├── api_server.py
├── config/
├── api/
├── orchestrators/
├── pipeline/
├── engines/
├── strategies/
├── domain/
├── infrastructure/
│   ├── mt5/
│   ├── database/
│   └── notification/
├── repositories/
├── services/
├── schemas/
└── utils/
```

## 6) Logging Output

Aplikasi akan membuat log files di folder `logs/`:

- `logs/bot_worker.log`
- `logs/api_server.log`
- `logs/execution.log`
- `logs/safety.log`
- `logs/error.log`
