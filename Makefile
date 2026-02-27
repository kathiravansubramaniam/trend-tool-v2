.PHONY: setup parse watch ui api dev test reindex

setup:
	pip3 install -r requirements.txt
	python3 -c "from src.index.schema import init_db; init_db()"
	@echo "Setup complete. Copy .env.example to .env and fill in your values."

parse:
	python3 scripts/bulk_parse.py

watch:
	python3 -m src.trigger.watcher

ui:
	python3 -m streamlit run ui/app.py

test:
	python3 -m pytest tests/ -v

api:
	python3 -m uvicorn api.main:app --reload --port 8000

dev:
	cd frontend && npm run dev

reindex:
	python3 scripts/reindex.py --all
