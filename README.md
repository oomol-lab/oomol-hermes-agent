# OOMOL Hermes Agent

[简体中文](README.zh-CN.md)

A ready-to-run Docker distribution of
[Hermes Agent](https://github.com/NousResearch/hermes-agent), with OO CLI,
OOMOL providers, and selected Skills preconfigured.

> Prefer a managed experience? Use [Leina](https://app.oomol.com/) without
> maintaining your own Docker environment.

## What's Included

- **OO CLI** — preinstalled and available to Hermes at runtime.
- **OOMOL LLM** — use OOMOL-hosted language models as the Hermes model
  provider.
- **Image generation** — GPT Image 2 and Nano Banana providers.
- **Video generation** — Seedance text-to-video and image-to-video provider.
- **Web search** — Jina Reader as the default Hermes search backend.
- **Bundled Skills** — document processing, public social research, diagrams,
  planning, and OO Skill management.

## Quick Start

Before starting:

1. [Create or sign in to an OOMOL account](https://console.oomol.com/).
2. [Create a personal API key](https://console.oomol.com/api-key).
3. Install Docker with Docker Compose.

Create the environment file:

```sh
cp .env.example .env
chmod 600 .env
```

Add your OOMOL API key to `.env`:

```dotenv
OO_API_KEY=your-oomol-api-key
```

The OOMOL LLM endpoint, model, and API mode are already prefilled:

```dotenv
OO_LLM_BASE_URL=https://llm.oomol.com/v1
OO_LLM_MODEL=deepseek-v4-flash
OO_LLM_API_MODE=codex_responses
```

Keep `OO_LLM_MODEL` to use the preconfigured OOMOL model. If it is not set,
configure a model inside Docker yourself.

Use the included [compose.yaml](compose.yaml) to pull the published image and
start the agent:

```sh
docker compose pull
docker compose up -d
docker compose logs -f hermes
```

The Hermes gateway listens on `127.0.0.1:8766` by default.

## Bundled Skills

The image includes selected Hermes, OOMOL, and OO framework Skills.

| Category | Skills |
| --- | --- |
| OO capabilities | `oo` |
| Skill management | `oo-find-skills`, `oo-create-skill`, `oo-publish-skill` |
| Office and PDF | `office-files`, `pdf-files`, `nano-pdf`, `ocr-and-documents` |
| Public research | `public-social-research` |
| Diagrams | `architecture-diagram`, `excalidraw` |
| Planning | `plan` |
| Hermes guidance | `hermes-agent` |

These Skills let Hermes work with Office and PDF files, extract text with OCR,
research public social content, create diagrams, plan complex work, and find or
manage Skills through OO.

## Configuration and Data

Additional settings are available in [.env.example](.env.example), including
the image, gateway address, port, and timezone.

Hermes configuration, sessions, OO CLI state, and workspace files are stored in
the Compose-managed `hermes-data` volume. `docker compose down` preserves the
volume; `docker compose down -v` deletes it.

Keep `.env` private. The gateway binds to localhost by default; only expose it
to other networks when an appropriate security layer is in place.

## About This Project

This repository packages a pinned Hermes Agent release with OO CLI, curated
Skills, and OOMOL provider Plugins. It is a Docker distribution project rather
than an independent Hermes fork.

## Development

```sh
make test
make build
```

See [docs/development.md](docs/development.md) and
[docs/architecture.md](docs/architecture.md) for details.

## License

Distribution-specific code is licensed under the MIT License. Hermes Agent and
bundled third-party components retain their own license terms. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
