# Development

## Prerequisites

- Git
- Docker with BuildKit
- `uv`
- Python 3.11 through 3.13 for repository tests

## Repository Tests

```sh
uv sync
uv run pytest
```

These tests validate the version lock, Docker defaults, Skill assembly safety,
OO Skill metadata transformation, and required repository layout. They do not
replace an image build.

## Image Build

```sh
docker build --progress=plain -t oomol-hermes-agent:dev .
```

The build requires internet access to the pinned Hermes repository, OO CLI
artifact host, Debian repositories, and Python package indexes.

Smoke commands:

```sh
docker run --rm oomol-hermes-agent:dev oo --version
docker run --rm oomol-hermes-agent:dev hermes --help
```

The native linux/arm64 build and both smoke commands passed with Hermes
`0.20.2` and OO CLI `1.7.4` on 2026-08-17. Linux/amd64 remains a release
acceptance check.

For authentication checks, use the Compose `OO_API_KEY` flow or the persistent
volume commands in the root README. Never place credentials in build arguments,
image layers, or committed files.

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
python -m compileall -q scripts plugins
git diff --check
```

Use Linux line endings for all text files.
