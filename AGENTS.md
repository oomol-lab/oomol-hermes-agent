# OOMOL Hermes Agent Development Guide

This repository builds the standalone open-source OOMOL Hermes Agent Docker
distribution from a pinned NousResearch Hermes Agent revision. These rules are
mandatory.

## Required Reading

Read the document matching the work before editing:

| Work | Required document |
| --- | --- |
| Project boundaries and runtime layout | `docs/architecture.md` |
| Local setup, tests, or Docker builds | `docs/development.md` |
| Hermes version or patch changes | `docs/upstream-maintenance.md` |
| Current migration status and next work | `docs/handoff.md` |

## Project Boundaries

This is a Docker distribution project, not an independent Hermes fork. It may
assemble OO CLI, curated Skills, provider Plugins, and minimal generic Hermes
patches that cannot use an existing extension surface.

Do not add OOMOL production bindings, internal operations tooling, messaging
platform patches, or reimplementations of Hermes core behavior. Do not copy
internal operational code from `oomol/hermes-agent` merely because it exists.

## Change Policy

- Prefer the distribution layer: Docker, configuration, scripts, Skills,
  Plugins, tests, and public documentation.
- Add an upstream patch only when no extension surface can implement the
  behavior. Keep patches small, reviewable, and fail closed with
  `git apply --check`; never replace a complete upstream source file.
- Treat `upstream.lock.json` as the canonical Hermes and OO CLI version record.
  Pin Hermes by full commit SHA and OO CLI artifacts by version and per-arch
  SHA-256.
- Follow `docs/upstream-maintenance.md` for upstream changes and keep each
  upstream update in its own commit.

## Skills And Providers

- Install only Skills listed in `config/curated-skills.txt` or
  `config/hermes-skills.txt`. Reject collisions, traversal, and symlinks.
- Install runtime dependencies at image build time. Keep image-owned Skills
  immutable and user Skills under `$HERMES_HOME`.
- Keep Hermes's 60-character Skill-description default. Any larger limit must
  be an explicit per-Skill exception.
- Verify artifacts created by document-producing Skills by reading or rendering
  them back.
- Register providers through Hermes provider ABCs; do not add model tools to
  core.
- Invoke OO CLI with argument arrays, bound timeouts, and sanitized errors.
  Never log prompts, uploaded contents, credentials, signed URLs, or sensitive
  raw responses.
- Keep non-secret configuration in `config.yaml`. OO credentials come only from
  the required runtime `OO_API_KEY`, never image layers or persisted files.
- Provider failures must not prevent Hermes from starting.

## Runtime And Security

- Startup requires `OO_API_KEY`, `OO_LLM_BASE_URL`, `OO_LLM_MODEL`, and
  `OO_LLM_API_MODE`, but it must not validate them with a network request.
- Keep mutable state under `/data`; `$HERMES_HOME` and `OO_CONFIG_DIR` must live
  below it.
- Seed `config.yaml` only when missing and never overwrite user changes.
- Run the final process as the `hermes` user and keep the entrypoint small and
  transparent.
- Do not add private registries, internal endpoints, or company credentials.

## Validation And Commits

- Run repository tooling through Docker. `uv` may be used inside build
  containers but must not be a host prerequisite.
- Follow `docs/development.md`; release and upstream changes require the full
  Docker integration test.
- Run `git diff --check` before committing.
- Keep unrelated changes in separate Conventional Commits.

## Open-Source Hygiene

- Preserve the OOMOL MIT license and required upstream or third-party notices.
- Never commit `.env`, credentials, user data, generated artifacts, runtime
  state, or downloaded Hermes source.
- Use placeholders in public examples and document current public behavior, not
  internal deployment history.
