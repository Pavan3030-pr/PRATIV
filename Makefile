.PHONY: help install dev test agent-test backend-test web-test e2e data run docker

help:
	@echo "make install       create .venv, install Python and frontend dependencies"
	@echo "make dev           run the agent API (:8000) and explorer (:5173)"
	@echo "make test          agent + backend + frontend unit tests and explorer data checks"
	@echo "make e2e           Playwright smoke of the production build"
	@echo "make data          rebuild frontend/public/explore from committed results"
	@echo "make run           crawl the companies in numbers.txt (./run.sh)"
	@echo "make docker        full stack: PostgreSQL + Spring Boot + agent + UI"

install:
	python3 -m venv .venv
	.venv/bin/pip install -q -r agent/requirements.txt
	cd frontend && npm ci

dev:
	./scripts/dev.sh

agent-test:
	cd agent && ../.venv/bin/python -m unittest -v test_main test_web

backend-test:
	cd backend && mvn -B --no-transfer-progress test

web-test:
	cd frontend && npm test

test: agent-test backend-test web-test
	node scripts/smoke_explorer.mjs

e2e:
	cd frontend && npm run build && npm run e2e

data:
	python3 scripts/build_explorer_data.py
	node scripts/smoke_explorer.mjs

run:
	./run.sh numbers.txt

docker:
	docker compose up --build
