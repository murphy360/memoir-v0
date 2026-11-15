# Everything runs in the project's Docker images, never on the host (murphy360/standards).
# TAG keeps parallel sessions from overwriting each other's images.
SHELL := /bin/sh
TAG ?= dev
API_TEST := memoir-api-test:$(TAG)
WEB_TEST := memoir-web-test:$(TAG)
RUN := docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -v "$(CURDIR):/src"

.PHONY: images test test-api test-web lint lint-api lint-web format

images:
	docker build --target test -t $(API_TEST) backend
	docker build --target test -t $(WEB_TEST) frontend

test: test-api test-web

test-api: images
	$(RUN) -w /src/backend $(API_TEST) pytest -q

test-web: images
	$(RUN) -w /src/frontend $(WEB_TEST) sh -c "npm run typecheck && npm test"

lint: lint-api lint-web

lint-api: images
	$(RUN) -w /src/backend $(API_TEST) sh -c "ruff format --no-cache --check . && ruff check --no-cache ."

lint-web: images
	$(RUN) -w /src/frontend $(WEB_TEST) sh -c "prettier --check . && eslint ."

format: images
	$(RUN) -w /src/backend $(API_TEST) ruff format --no-cache .
	$(RUN) -w /src/frontend $(WEB_TEST) prettier --write .
