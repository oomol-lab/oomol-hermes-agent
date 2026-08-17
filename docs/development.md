# Development

## Prerequisites

- Git
- Docker with BuildKit and Docker Compose

Python and `uv` are implementation details inside the build containers. They
do not need to be installed on the development host.

## Repository Tests

```sh
make test
```

These tests validate the version lock, Docker defaults, Skill assembly safety,
OO Skill metadata transformation, and required repository layout. They do not
replace an image build. The equivalent command without Make is:

```sh
docker build --progress=plain \
  --file Dockerfile.test \
  --target repository-tests \
  .
```

## Image Build

```sh
docker build --progress=plain -t oomol-hermes-agent:dev .
```

The build requires internet access to the pinned Hermes repository, OO CLI
artifact host, Debian repositories, and Python package indexes.

Smoke commands:

```sh
docker run --rm -e OO_API_KEY -e OO_LLM_BASE_URL -e OO_LLM_MODEL -e OO_LLM_API_MODE \
  oomol-hermes-agent:dev oo --version
docker run --rm -e OO_API_KEY -e OO_LLM_BASE_URL -e OO_LLM_MODEL -e OO_LLM_API_MODE \
  oomol-hermes-agent:dev hermes --help
docker run --rm -e OO_API_KEY -e OO_LLM_BASE_URL -e OO_LLM_MODEL -e OO_LLM_API_MODE \
  oomol-hermes-agent:dev hermes plugins list --plain
```

Export all four variables before running image commands. `.env.example`
contains the recommended base URL, model, and API mode; never put an API key in
a command literal.

The native linux/arm64 build and these smoke commands passed with Hermes
`0.20.2` and OO CLI `1.7.4` on 2026-08-17. Plugin discovery reported
`oo_gpt_image_2`, `oo_nano_banana`, `oo_seedance`, and `oo_jina` as enabled.
Linux/amd64 remains a release acceptance check.

## Development Compose

Start the development gateway:

```sh
make compose-up
```

Compose runs the messaging gateway from the locally built image and keeps its
state in the Compose-managed `/data` volume. It does not start the Hermes App
backend or publish a host port; use a configured messaging platform such as
Telegram for development testing.

At startup, the entrypoint uses `OO_API_KEY` to persist an oo-cli login under
`/data/.config/oo`. The operation has a 30-second timeout and is best-effort, so
an authentication or network failure warns without stopping the gateway. The
environment variable remains available to the main Hermes process for its
OOMOL model and provider Plugins, while terminal processes use the saved login.
Authentication is staged before replacing the active account; a failed refresh
removes any prior account instead of allowing terminal work to use stale
credentials.

Runtime tests cover required environment validation, base-URL and API-mode
validation, and invalid `OO_API_KEY` behavior in the connector providers.

To verify the saved authentication without the environment override, run:

```sh
docker compose -f compose.yaml -f compose.dev.yaml exec hermes \
  env -u OO_API_KEY oo auth status --json
```

Never place credentials in build arguments, image layers, command literals, or
committed files. The runtime API key is intentionally persisted as oo-cli state
inside the private `/data` volume.

## Editing Skills

Project-owned Skills live below `skills/`, but only paths in
`config/curated-skills.txt` enter the image. Keep ordinary descriptions concise;
only OO-backed routing that genuinely requires it should opt in to a larger
prompt description.

When adding a dependency, pin it in the relevant requirements file and add a
real build-time verification step.

## Editing Providers

Providers are copied into Hermes's category layout during build. Develop against
the pinned Hermes ABCs, keep network operations bounded, and include sanitized
failure tests. Before adding another provider, extract repeated OO subprocess,
upload, polling, and response-normalization logic into a shared module.

## Useful Checks

```sh
make check
```

`make check` runs repository tests in Docker and then checks the working-tree
diff. Use Linux line endings for all text files.
