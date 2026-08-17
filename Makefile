SHELL := /bin/sh

IMAGE ?= oomol-hermes-agent:dev
DATA_VOLUME ?= oomol-hermes-agent-data
GATEWAY_PORT ?= 8766
DOCKER ?= docker
COMMAND ?=
COMPOSE ?= $(DOCKER) compose
DEV_COMPOSE_FILES := -f compose.yaml -f compose.dev.yaml

.DEFAULT_GOAL := help

.PHONY: help test check build smoke volume run run-clean gateway compose-config compose-build compose-up compose-down compose-logs compose-cli

help:
	@echo "OOMOL Hermes Agent development commands:"
	@echo "  make test         Run repository tests inside Docker"
	@echo "  make check        Run tests and whitespace checks"
	@echo "  make build        Build the local Docker image"
	@echo "  make run          Start Hermes with persistent data"
	@echo "  make run-clean    Start Hermes with fresh, disposable data"
	@echo "  make smoke        Check Hermes inside the built image"
	@echo "  make gateway      Start the Hermes gateway"
	@echo "  make compose-up   Build and start the development gateway"
	@echo "  make compose-down Stop the development gateway"
	@echo "  make compose-logs Follow development gateway logs"
	@echo "  make compose-cli  Open a one-off Hermes CLI"
	@echo ""
	@echo "Overrides: IMAGE, DATA_VOLUME, GATEWAY_PORT, DOCKER, COMMAND, COMPOSE"

test:
	$(DOCKER) build --progress=plain \
		--file Dockerfile.test \
		--target repository-tests \
		.

check: test
	git diff --check

build:
	$(DOCKER) build --progress=plain -t "$(IMAGE)" .

smoke:
	$(DOCKER) run --rm "$(IMAGE)" hermes --help

volume:
	@$(DOCKER) volume inspect "$(DATA_VOLUME)" >/dev/null 2>&1 || \
		$(DOCKER) volume create "$(DATA_VOLUME)" >/dev/null

run: volume
	$(DOCKER) run --rm -it \
		-v "$(DATA_VOLUME):/data" \
		"$(IMAGE)" $(COMMAND)

run-clean:
	$(DOCKER) run --rm -it "$(IMAGE)" $(COMMAND)

gateway: volume
	$(DOCKER) run --rm -it \
		-p "$(GATEWAY_PORT):8766" \
		-v "$(DATA_VOLUME):/data" \
		"$(IMAGE)" hermes gateway run

compose-config:
	$(COMPOSE) $(DEV_COMPOSE_FILES) config

compose-build:
	$(COMPOSE) $(DEV_COMPOSE_FILES) build

compose-up:
	$(COMPOSE) $(DEV_COMPOSE_FILES) up -d --build

compose-down:
	$(COMPOSE) $(DEV_COMPOSE_FILES) down

compose-logs:
	$(COMPOSE) $(DEV_COMPOSE_FILES) logs -f hermes

compose-cli:
	$(COMPOSE) $(DEV_COMPOSE_FILES) run --rm hermes hermes
