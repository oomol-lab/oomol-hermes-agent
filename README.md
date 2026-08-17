# OOMOL Hermes Agent

OOMOL Hermes Agent is an opinionated Docker distribution of
[Hermes Agent](https://github.com/NousResearch/hermes-agent). It bundles the OO
CLI, curated document and research Skills, and OOMOL-backed language-model,
image, video, and web-search providers.

This is a standalone open-source distribution project. It is not the OOMOL
production Hermes fork and does not contain OOMOL Platform Bindings, Leina, or
internal operations tooling.

## Included

- Hermes Agent pinned to an immutable upstream commit.
- OO CLI pinned and SHA-256 verified for linux/amd64 and linux/arm64.
- Full routing descriptions for the four OO framework Skills while preserving
  Hermes's 60-character default for ordinary Skills.
- Curated Office, PDF, and public-social-research Skills.
- OOMOL LLM as the default Hermes model provider, with an explicitly selected
  OpenAI-compatible API mode.
- GPT Image 2, Nano Banana, Seedance, and Jina provider Plugins backed by OO.
- Build-time Office/PDF, Plugin syntax, and Skill assembly verification.

## Status

The repository is ready for continued development. Repository tests and a full
native linux/arm64 image build have passed, including container smoke checks.
Linux/amd64 validation and the remaining public-release work are tracked in
[docs/handoff.md](docs/handoff.md).

Current pinned components:

| Component | Version | Immutable source |
| --- | --- | --- |
| Hermes Agent | `0.20.2` | `df4b65147d7ddd74dd449f9067aabbca5aef0ec7` |
| OO CLI | `1.7.4` | Architecture-specific SHA-256 in `upstream.lock.json` |

## Install With Docker Compose

Docker Compose is the recommended installation and distribution path. It keeps
the image, gateway port, required OOMOL model configuration, and persistent
`/data` volume in one declarative configuration. The gateway binds to
`127.0.0.1:8766` by default.

Prepare the local environment file:

```sh
cp .env.example .env
chmod 600 .env
```

Fill in `OO_API_KEY` before starting the container. The example file recommends
the normal OOMOL base URL, `deepseek-v4-flash`, and `codex_responses`. Change
`OO_LLM_MODEL` or `OO_LLM_API_MODE` when the selected OOMOL-hosted model
requires a different setting. `OO_LLM_BASE_URL` normally should not be changed.
The supported API modes are `codex_responses` and `chat_completions`. All four
variables are required at runtime; their recommended values live only in
`.env.example`, not as hidden application defaults.

At startup, the entrypoint validates the declared base URL locally without
making a remote health check. The key remains in the process environment and is
never written into Hermes configuration. A missing variable or malformed base
URL stops startup with a sanitized error.

Compose passes the model settings to Hermes and makes `OO_API_KEY` available to
the bundled language, image, video, and search providers.

The image has not been published to GHCR yet. Until the first release, build and
start it from this checkout with the development override:

```sh
docker compose -f compose.yaml -f compose.dev.yaml build
docker compose -f compose.yaml -f compose.dev.yaml up -d
docker compose -f compose.yaml -f compose.dev.yaml logs -f hermes
```

Equivalent development shortcuts are available through Make:

```sh
make compose-build
make compose-up
make compose-logs
```

After the image is published, end users will only need the released
`compose.yaml` and `.env.example` files:

```sh
docker compose pull
docker compose up -d
docker compose logs -f hermes
```

Use `docker compose run --rm hermes hermes` for a one-off interactive Hermes
CLI. `docker compose down` stops the gateway but preserves `hermes-data`.
`docker compose down -v` also deletes configuration and workspace data.

The first start seeds `/data/.hermes/config.yaml` with the OOMOL model provider;
later starts never overwrite it. Existing development volumes created before
this provider was added must be updated manually or recreated. Keep `.env`
private: it is ignored by Git and excluded from the Docker build context, but
Docker still exposes container environment variables to users with daemon
access.

## Local Build And Direct Docker Use

Build the image without Compose:

```sh
make build
```

The equivalent command is:

```sh
docker build -t oomol-hermes-agent:dev .
```

The build downloads the pinned Hermes source and OO CLI. It fails if the Hermes
patch no longer applies, a checksum differs, an allowlisted Skill is missing,
or the bundled document runtime cannot create and verify representative files.

For low-level Docker use, export all four runtime variables in the host shell
and pass them by name so the credential is not embedded in the command:

```sh
docker volume create oomol-hermes-agent-data
docker run --rm -it \
  -e OO_API_KEY \
  -e OO_LLM_BASE_URL \
  -e OO_LLM_MODEL \
  -e OO_LLM_API_MODE \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev
```

Start a gateway the same way:

```sh
docker run --rm -it \
  -e OO_API_KEY \
  -e OO_LLM_BASE_URL \
  -e OO_LLM_MODEL \
  -e OO_LLM_API_MODE \
  -p 8766:8766 \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev \
  hermes gateway run
```

After exporting the same four variables, Make also provides:

```sh
make run
make run-clean
make gateway
```

These targets pass the named variables through without reading `.env` or
persisting credentials. Use Compose for the normal workflow. `run-clean` uses
disposable `/data` state; `run` and `gateway` use the named
`oomol-hermes-agent-data` volume.

## Development

```sh
make compose-build
make compose-up
make compose-logs
```

These targets use `compose.yaml` with `compose.dev.yaml`, so Hermes runs from a
locally built development image rather than directly on the host.

Read [AGENTS.md](AGENTS.md) before changing the repository. Architecture,
development, upstream maintenance, and handoff details live under `docs/`.

## Licensing

Distribution-specific code is MIT licensed. Hermes Agent and other bundled
components retain their own copyright and license terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
