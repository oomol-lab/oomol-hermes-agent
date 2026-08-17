# OOMOL Hermes Agent

OOMOL Hermes Agent is an opinionated Docker distribution of
[Hermes Agent](https://github.com/NousResearch/hermes-agent). It bundles the OO
CLI, curated document and research Skills, and OOMOL-backed image, video, and
web-search providers.

This is a standalone open-source distribution project. It is not the OOMOL
production Hermes fork and does not contain OOMOL Platform Bindings, Leina, or
internal operations tooling.

## Included

- Hermes Agent pinned to an immutable upstream commit.
- OO CLI pinned and SHA-256 verified for linux/amd64 and linux/arm64.
- Full routing descriptions for the four OO framework Skills while preserving
  Hermes's 60-character default for ordinary Skills.
- Curated Office, PDF, and public-social-research Skills.
- GPT Image 2, Nano Banana, Seedance, and Jina provider Plugins backed by OO.
- Build-time Office/PDF, Plugin syntax, and Skill assembly verification.

## Status

The repository is ready for continued development. Repository tests and a full
native linux/arm64 image build have passed, including container smoke checks.
Linux/amd64 validation and the remaining public-release work are tracked in
[docs/handoff.md](docs/handoff.md).

## Build

```sh
make build
```

The build downloads the pinned Hermes source and OO CLI. It fails if the Hermes
patch no longer applies, a checksum differs, an allowlisted Skill is missing,
or the bundled document runtime cannot create and verify representative files.

The equivalent command without Make is:

```sh
docker build -t oomol-hermes-agent:dev .
```

## Run

Start Hermes locally with a persistent Docker volume:

```sh
make run
```

Start with fresh, disposable state instead:

```sh
make run-clean
```

`run-clean` does not mount the named data volume. Docker creates an anonymous
`/data` volume for the container and removes it when the container exits.

The equivalent persistent run commands without Make are:

```sh
docker volume create oomol-hermes-agent-data
docker run --rm -it \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev
```

Authenticate OO using the same volume when using the low-level Docker flow:

```sh
docker run --rm -it \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev \
  oo auth login
```

Inspect authentication:

```sh
docker run --rm \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev \
  oo auth status --json
```

Run a messaging gateway after configuring Hermes:

```sh
make gateway
```

Or without Make:

```sh
docker run --rm -it \
  -p 8766:8766 \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev \
  hermes gateway run
```

The first start seeds `/data/.hermes/config.yaml`. Later starts never overwrite
that file.

## Docker Compose

The public installation path uses `compose.yaml`, a prebuilt image, and a named
volume for all state. The gateway binds to `127.0.0.1:8766` by default.
`OO_API_KEY` is the only OO-specific Compose environment variable.

Prepare the local environment file once before starting either workflow:

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set `OO_API_KEY`. Compose reads this file automatically and
passes the explicitly declared variables to the container; users do not need
to configure the container environment separately.

The image has not been published to GHCR yet. Until the first release, use the
development override to build it from this checkout:

```sh
docker compose -f compose.yaml -f compose.dev.yaml build
docker compose -f compose.yaml -f compose.dev.yaml up -d
docker compose -f compose.yaml -f compose.dev.yaml logs -f hermes
```

The same development flow is available through shorter Make targets:

```sh
make compose-build
make compose-up
make compose-logs
```

After the image is published, the end-user installation flow will require only
the released Compose files, not a source checkout or the development override:

```sh
docker compose pull
docker compose up -d
docker compose logs -f hermes
```

Use `docker compose run --rm hermes hermes` for a one-off interactive Hermes
CLI. `docker compose down` stops the gateway but preserves `hermes-data`;
`docker compose down -v` also deletes configuration and workspace data.

OO CLI reads `OO_API_KEY` directly and treats it as the active in-memory
credential, so no interactive login or persisted OO account is required. The
variable is passed both to the bundled provider processes and to terminal
commands launched by Hermes. Keep `.env` private: it is ignored by Git and
excluded from the Docker build context, but Docker still exposes container
environment variables to users with daemon access.

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
