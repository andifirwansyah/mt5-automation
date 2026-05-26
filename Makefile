.PHONY: run test migrate-up migrate-down migrate-current

run:
	uvicorn ai_trading_automation.api.app:app --reload --app-dir src

test:
	pytest tests -q

migrate-up:
	alembic -c alembic.ini upgrade head

migrate-down:
	alembic -c alembic.ini downgrade -1

migrate-current:
	alembic -c alembic.ini current
