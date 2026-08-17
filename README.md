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

Authenticate OO using the same volume:

```sh
make auth
```

Or without Make:

```sh
docker run --rm -it \
  -v oomol-hermes-agent-data:/data \
  oomol-hermes-agent:dev \
  oo auth login
```

Inspect authentication:

```sh
make auth-status
```

Or without Make:

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

## Development

```sh
make sync
make test
make smoke
```

`make test` runs repository tests without building the image. `make smoke`
checks the OO and Hermes CLIs in an image previously built by `make build`.

Read [AGENTS.md](AGENTS.md) before changing the repository. Architecture,
development, upstream maintenance, and handoff details live under `docs/`.

## Licensing

Distribution-specific code is MIT licensed. Hermes Agent and other bundled
components retain their own copyright and license terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
