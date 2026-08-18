# OOMOL Hermes Agent

[简体中文](README.zh-CN.md)

A ready-to-run Docker distribution of
[Hermes Agent](https://github.com/NousResearch/hermes-agent), with OO CLI,
OOMOL providers, and selected Skills preconfigured.

> Prefer a managed experience? Use [Leina](https://leina.ai/) without
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

[![OOMOL Hermes Agent quick-start video](https://i.ytimg.com/vi/jc7Y2Oy1hhA/hqdefault.jpg)](https://youtu.be/jc7Y2Oy1hhA)

[Watch the quick-start video on YouTube](https://youtu.be/jc7Y2Oy1hhA).

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
start the agent. Messaging setup is optional:

```sh
docker compose pull

# Optional: configure a messaging platform with the interactive wizard
# Settings are saved in the persistent data volume. Skip this command if a
# messaging platform is already configured.
# Supported platforms: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/
docker compose run --rm hermes hermes gateway setup

docker compose up -d
docker compose logs -f hermes
```

The messaging gateway does not expose a network port.

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
the image and OOMOL model configuration.

Hermes configuration, sessions, OO CLI state, and workspace files are stored in
the Compose-managed `hermes-data` volume. `docker compose down` preserves the
volume; `docker compose down -v` deletes it. On startup, the runtime API key is
also saved there as oo-cli login state so bundled OO Skills work from messaging
sessions.

Keep `.env` private because it contains the OOMOL API key.

## About This Project

This repository packages a pinned Hermes Agent release with OO CLI, curated
Skills, and OOMOL provider Plugins. It is a Docker distribution project rather
than an independent Hermes fork.

## Development

```sh
make test
make build
make compose-up
```

Development Compose runs only the messaging gateway and does not publish a host
port. Use a configured messaging platform for testing.

See [docs/development.md](docs/development.md) and
[docs/architecture.md](docs/architecture.md) for details.

## License

Distribution-specific code is licensed under the MIT License. Hermes Agent and
bundled third-party components retain their own license terms. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
