.PHONY: run test lint clean

run:
	@echo "Starting RESQ application..."

test:
	pytest tests/

lint:
	@echo "Running lint checks..."

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
