# Thin wrappers so the same commands work locally and in CI.
.DEFAULT_GOAL := help
SHELL := /bin/bash
IMAGE ?= pulsecheck
TAG   ?= dev

.PHONY: help install lint fmt typecheck test build scan up down clean kind-up kind-deploy kind-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create a virtualenv and install dev dependencies
	python -m venv .venv && .venv/bin/pip install -e ".[dev]"

lint: ## Run ruff
	ruff check . && ruff format --check .

fmt: ## Auto-format
	ruff check --fix . && ruff format .

typecheck: ## Run mypy
	mypy app

test: ## Run the test suite with coverage
	pytest

build: ## Build the container image
	docker build -t $(IMAGE):$(TAG) \
		--build-arg VERSION=$(TAG) \
		--build-arg VCS_REF=$$(git rev-parse --short HEAD) \
		--build-arg BUILD_DATE=$$(date -u +%Y-%m-%dT%H:%M:%SZ) .

scan: build ## Scan the image for known CVEs
	trivy image --severity HIGH,CRITICAL --exit-code 1 $(IMAGE):$(TAG)

up: ## Start the local stack
	docker compose up --build -d && docker compose ps

down: ## Stop the local stack
	docker compose down -v

kind-up: ## Create a local Kubernetes cluster
	kind create cluster --name pulsecheck --config deploy/kind-config.yaml

kind-deploy: build ## Load the image into kind and apply the manifests
	kind load docker-image $(IMAGE):$(TAG) --name pulsecheck
	kubectl apply -k deploy/k8s
	kubectl -n pulsecheck rollout status deploy/pulsecheck --timeout=120s

kind-down: ## Delete the local Kubernetes cluster
	kind delete cluster --name pulsecheck

clean: ## Remove build and test artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov coverage.xml .coverage *.egg-info
