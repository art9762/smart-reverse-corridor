# Smart Reverse Corridor — root Makefile
# One-liner for the demo:  make up && make demo

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
PROFILES_ALL ?= --profile sim --profile ml
RUN_DIR      ?= runs
BENCH_MIN    ?= 5

# Pick up .env automatically (compose does it too, but useful for non-compose targets).
ifneq (,$(wildcard ./.env))
include .env
export
endif

.PHONY: help up up-all down restart logs ps demo demo-quick bench lint lint-py lint-web test test-py test-web build clean nuke env

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make <target>\n\nTargets:\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

env: ## Create .env from .env.example if missing
	@[ -f .env ] || (cp .env.example .env && echo "created .env from .env.example")

up: env ## Bring up the core stack (mosquitto, influxdb, controller, web, grafana)
	$(COMPOSE) up -d --build

up-all: env ## Bring up core + sim + ml profiles
	$(COMPOSE) $(PROFILES_ALL) up -d --build

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) $(PROFILES_ALL) down

restart: down up ## Restart the stack

logs: ## Tail logs of all services
	$(COMPOSE) logs -f --tail=200

ps: ## Show running services
	$(COMPOSE) ps

build: env ## Build all images (no start)
	$(COMPOSE) $(PROFILES_ALL) build

demo: env ## Bring up stack and run the asymmetric simulator scenario
	SIM_SCENARIO=asymmetric SIM_MODE=adaptive $(COMPOSE) --profile sim up -d --build
	@echo ""
	@echo "  Web      : http://localhost:$${WEB_PORT:-5173}"
	@echo "  API      : http://localhost:$${CONTROLLER_PORT:-8000}"
	@echo "  Grafana  : http://localhost:$${GRAFANA_PORT:-3001}"
	@echo "  InfluxDB : http://localhost:8086"
	@echo ""
	$(COMPOSE) logs -f --tail=50 controller simulator

demo-quick: ## Quick 60s demo (no ML)
	docker compose up -d
	docker compose --profile sim up -d
	@echo "Dashboard: http://localhost:$${WEB_PORT:-5173}"
	@echo "Grafana:   http://localhost:$${GRAFANA_PORT:-3001}"
	@echo "Controller: http://localhost:$${CONTROLLER_PORT:-8000}/state"

bench: env ## Run baseline + adaptive scenarios for $(BENCH_MIN) minutes each, save metrics under runs/
	@mkdir -p $(RUN_DIR)
	@ts=$$(date +%Y%m%d-%H%M%S); \
	  out=$(RUN_DIR)/$$ts; mkdir -p $$out; \
	  echo ">> baseline run for $(BENCH_MIN)m → $$out/baseline.log"; \
	  SIM_MODE=baseline SIM_SCENARIO=asymmetric $(COMPOSE) --profile sim up -d --build; \
	  sleep $$(( $(BENCH_MIN) * 60 )); \
	  $(COMPOSE) logs --no-color simulator controller > $$out/baseline.log; \
	  $(COMPOSE) --profile sim down; \
	  echo ">> adaptive run for $(BENCH_MIN)m → $$out/adaptive.log"; \
	  SIM_MODE=adaptive SIM_SCENARIO=asymmetric $(COMPOSE) --profile sim up -d --build; \
	  sleep $$(( $(BENCH_MIN) * 60 )); \
	  $(COMPOSE) logs --no-color simulator controller > $$out/adaptive.log; \
	  $(COMPOSE) --profile sim down; \
	  echo "bench results in $$out"

lint: lint-py lint-web ## Lint everything (ruff + eslint)

lint-py: ## ruff over services/*
	@for d in services/controller services/ml services/simulator; do \
	  if [ -d $$d ]; then echo ">> ruff $$d"; (cd $$d && ruff check . || exit $$?); fi; \
	done

lint-web: ## eslint over web/
	@if [ -d web ] && [ -f web/package.json ]; then (cd web && npm run lint --if-present); else echo "web/ skipped"; fi

test: test-py test-web ## Run all tests (pytest + vitest)

test-py: ## pytest in each python service
	@for d in services/controller services/ml services/simulator; do \
	  if [ -d $$d ]; then \
	    echo ">> pytest $$d"; \
	    (cd $$d && [ -d tests ] && pytest -q || echo "no tests in $$d"); \
	  fi; \
	done

test-web: ## vitest in web/
	@if [ -d web ] && [ -f web/package.json ]; then (cd web && npm test --if-present -- --run); else echo "web/ skipped"; fi

clean: ## Stop stack and remove volumes (DATA LOSS for influxdb/grafana)
	$(COMPOSE) $(PROFILES_ALL) down -v

nuke: clean ## clean + prune dangling images
	docker image prune -f
