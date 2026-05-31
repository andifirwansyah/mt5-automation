# GUIDE SHORT (Windows Quickstart)

Panduan cepat untuk menjalankan bot + API di Windows.

## 1) Setup awal

```powershell
cd <path>\ai-trading-automation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` minimal:

- `DATABASE_URL`
- `MT5_PATH`
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`

Mode aman:

- `ACCOUNT_MODE=DEMO_AUTO`
- `DRY_RUN=true`

---

## 2) Setup database

```powershell
alembic upgrade head
python scripts/seed_master_data.py
```

---

## 3) Cek koneksi MT5

```powershell
python scripts/check_mt5_connection.py
```

Pastikan output menunjukkan:

- MT5 connected `True`
- account info terbaca
- symbol selected
- candle fetched

---

## 4) Jalankan API (Terminal #1)

```powershell
scripts\run_api.bat
```

Test health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

---

## 5) Jalankan Bot (Terminal #2)

```powershell
scripts\run_bot.bat
```

---

## 6) Test kill switch

Aktif:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/bot/kill-switch/activate -ContentType "application/json" -Body '{"reason":"manual_test","actor":"ops"}'
```

Nonaktif:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/bot/kill-switch/deactivate -ContentType "application/json" -Body '{"reason":"resume","actor":"ops"}'
```

---

## 7) Validasi cepat safety

- `DRY_RUN=true` => tidak kirim `mt5.order_send`
- `ACCOUNT_MODE=DEMO_AUTO` => real account harus direject
- keputusan/reject harus tercatat di DB/log/journal

---

## 8) Menjalankan test

```powershell
python -m pytest tests/unit tests/integration tests/e2e -q
```
