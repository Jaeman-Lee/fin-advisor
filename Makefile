.PHONY: install init collect test dashboard monitor monitor-dry docker-up docker-down clean

# Install all dependencies
install:
	pip install -r requirements.txt
	python -c "import nltk; nltk.download('vader_lexicon', quiet=True)"

# Initialize database (schema + seed data)
init:
	python scripts/init_db.py

# Collect market data (default: 30 days + technical indicators)
collect:
	python scripts/collect_market_data.py --days 30 --indicators

# Collect full data (90 days + indicators)
collect-full:
	python scripts/collect_market_data.py --days 90 --indicators

# Run tests
test:
	pytest tests/ -v

# Start Streamlit dashboard (local)
dashboard:
	streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true

# Quick setup: install + init + collect + launch
setup: install init collect dashboard

# Docker
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

# Run market monitor (full: refresh + check + send)
monitor:
	python scripts/run_monitor.py

# Run market monitor (dry run: check + print only)
monitor-dry:
	python scripts/run_monitor.py --dry-run

# Remove generated files
clean:
	rm -f data/investment.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
