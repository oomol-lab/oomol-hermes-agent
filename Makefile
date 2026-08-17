SHELL := /bin/sh

IMAGE ?= oomol-hermes-agent:dev
DATA_VOLUME ?= oomol-hermes-agent-data
GATEWAY_PORT ?= 8766
DOCKER ?= docker
UV ?= uv
COMMAND ?=

.DEFAULT_GOAL := help

.PHONY: help sync test check build smoke volume run run-clean auth auth-status gateway

help:
	@echo "OOMOL Hermes Agent development commands:"
	@echo "  make build        Build the local Docker image"
	@echo "  make run          Start Hermes with persistent data"
	@echo "  make run-clean    Start Hermes with fresh, disposable data"
	@echo "  make test         Run repository tests"
	@echo "  make check        Run repository tests and whitespace checks"
	@echo "  make smoke        Check OO and Hermes inside the built image"
	@echo "  make auth         Authenticate OO in the persistent volume"
	@echo "  make auth-status  Inspect persisted OO authentication"
	@echo "  make gateway      Start the Hermes gateway"
	@echo ""
	@echo "Overrides: IMAGE, DATA_VOLUME, GATEWAY_PORT, DOCKER, UV, COMMAND"

sync:
	$(UV) sync

test:
	$(UV) run pytest

check: test
	git diff --check

build:
	$(DOCKER) build --progress=plain -t "$(IMAGE)" .

smoke:
	$(DOCKER) run --rm "$(IMAGE)" oo --version
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

auth: volume
	$(DOCKER) run --rm -it \
		-v "$(DATA_VOLUME):/data" \
		"$(IMAGE)" oo auth login

auth-status: volume
	$(DOCKER) run --rm \
		-v "$(DATA_VOLUME):/data" \
		"$(IMAGE)" oo auth status --json

gateway: volume
	$(DOCKER) run --rm -it \
		-p "$(GATEWAY_PORT):8766" \
		-v "$(DATA_VOLUME):/data" \
		"$(IMAGE)" hermes gateway run
