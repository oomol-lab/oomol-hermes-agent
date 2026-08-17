# OOMOL Hermes Agent Development Guide

This repository builds the standalone open-source OOMOL Hermes Agent Docker
distribution. It consumes a pinned NousResearch Hermes Agent revision and adds
OO CLI, curated Skills, and OOMOL-backed provider Plugins.

The rules in this file are mandatory.

## Required Reading

Read the document matching the work before editing:

| Work | Required document |
| --- | --- |
| Project boundaries and runtime layout | `docs/architecture.md` |
| Local setup, tests, or Docker builds | `docs/development.md` |
| Hermes version or patch changes | `docs/upstream-maintenance.md` |
| Current migration status and next work | `docs/handoff.md` |

## Scope

In scope:

- A reproducible Docker image built from an immutable Hermes upstream commit.
- OO CLI installation with per-architecture SHA-256 verification.
- Build-time export of OO framework Skills.
- Curated, image-owned Skills and their runtime dependencies.
- OOMOL image, video, and web-search provider Plugins.
- Minimal generic Hermes patches that cannot be implemented by an existing
  extension surface.

Out of scope:

- OOMOL production Platform Bindings, Leina, billing, or team bootstrap.
- DingTalk, Feishu, WeCom, Weixin, Slack, or other platform patches.
- Internal Kubernetes, release-notification, conversation-review, or support
  tooling.
- Reimplementing Hermes core behavior in this repository.

Do not copy internal operational code from `oomol/hermes-agent` into this
repository merely because it already exists there.

## Ownership And Change Order

Classify every change before editing:

1. **Distribution layer**: Dockerfile, configuration seed, scripts, curated
   Skills, provider Plugins, tests, and public documentation. Prefer this layer.
2. **Upstream patch**: a small generic patch under `patches/` applied to the
   pinned Hermes source. Use only when an extension surface cannot implement the
   required behavior.
3. **Upstream update**: a deliberate change to `upstream.lock.json`, Docker
   defaults, patches, and compatibility validation.

Do not copy or replace an entire upstream source file. Store reviewable unified
patches that fail closed through `git apply --check`.

## Upstream Pinning

- `upstream.lock.json` is the canonical Hermes and OO CLI version record.
- Docker build defaults must match the lock file exactly.
- Pin Hermes by a full commit SHA, never a branch.
- Pin OO CLI by version and SHA-256 for every supported architecture.
- An upstream update must review every patch and every provider ABC import.
- Keep an upstream update in its own commit.

## Skill Description Policy

Hermes keeps the default 60-character prompt-index limit. The single upstream
patch allows a Skill to opt in with:

```yaml
metadata:
  hermes:
    prompt_description_max_chars: 1200
```

The image build adds this metadata only to the four OO framework Skills. A
curated OO-backed Skill may declare it explicitly when a concise description
cannot route safely. Ordinary bundled Skills should keep descriptions at or
below 60 characters.

Never raise the global default.

## Skills

- Curated Skill source lives under `skills/`.
- Installation is controlled by `config/curated-skills.txt` and
  `config/hermes-skills.txt`; unlisted Skills do not enter the image.
- Reject path collisions, traversal, and symlinks.
- Install all runtime dependencies at image build time.
- Do not download packages during container startup.
- Keep image-owned Skills immutable and user Skills under `$HERMES_HOME`.
- Every document-producing Skill must verify created artifacts by reading or
  rendering them back.

## Provider Plugins

- Providers live under the Hermes-compatible category layout in `plugins/`.
- Register through Hermes provider ABCs; do not add model tools to core.
- Keep OO CLI invocation in argument arrays, never shell-concatenated strings.
- Bound timeouts and redact subprocess errors before returning them.
- Do not log prompts, uploaded file contents, credentials, signed URLs, or raw
  connector responses that may contain them.
- Configuration that is not secret belongs in `config.yaml`. OO credentials
  come from the runtime `OO_API_KEY` environment variable or the OO
  configuration volume; never bake them into image layers.
- Provider failures must not prevent Hermes from starting.

Shared OO subprocess, upload, polling, and redaction behavior should move into
one common client before adding more providers.

## Docker Runtime

- The container must start without OO authentication and without network calls.
- Persist `/data`; `$HERMES_HOME` and `OO_CONFIG_DIR` live under it.
- Seed `config.yaml` only when it does not exist. Never overwrite user changes
  during startup.
- Run the final process as the `hermes` user.
- Keep the entrypoint small and transparent.
- Do not add private registries, internal endpoints, or company credentials.

## Validation

Use `uv` for repository tooling.

For narrow Python or metadata changes:

```sh
uv run pytest
```

For Docker, dependency, Skill, Plugin, or upstream changes:

```sh
docker build -t oomol-hermes-agent:dev .
docker run --rm oomol-hermes-agent:dev oo --version
docker run --rm oomol-hermes-agent:dev hermes --help
```

The full Docker build is the integration test: it applies the upstream patch,
installs OO, exports Skills, validates Node scripts, imports provider code, and
exercises Office/PDF generation. Do not replace it with mocks for release work.

Before every commit, run:

```sh
git diff --check
```

## Commit Boundaries

Keep separate logical commits for:

- Upstream pin or patch updates.
- Docker/runtime assembly.
- Curated Skills and their dependencies.
- Provider Plugins and focused tests.
- Documentation and repository policy.

Use Conventional Commits with scopes such as `build(image)`, `feat(skills)`,
`feat(providers)`, `fix(runtime)`, `docs(project)`, and `chore(upstream)`.

## Open-Source Hygiene

- Keep the OOMOL MIT license and required upstream/third-party notices.
- Never commit `.env`, OO credentials, user data, generated documents, runtime
  state, or downloaded Hermes source.
- Public examples use placeholders only.
- Documentation describes current behavior, not internal deployment history.
