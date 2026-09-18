.PHONY: demo report serve sync docker

demo:
	python -m app.main demo --period month --year 2026 --month 9

report-month:
	python -m app.main report --period month --year 2026 --month 9

report-quarter:
	python -m app.main report --period quarter --year 2026 --quarter 3

report-year:
	python -m app.main report --period year --year 2026

sync:
	python -m app.main sync

serve:
	python -m app.main serve

docker:
	docker compose up -d --build
