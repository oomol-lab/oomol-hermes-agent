# Development Handoff

## Goal

Publish a standalone open-source Docker distribution named
`oomol-hermes-agent`. It should offer a normal Hermes experience with OO CLI,
curated Skills, and OOMOL provider Plugins preinstalled, without depending on
the private OOMOL production control plane.

## Completed In The Initial Scaffold

- Created an independent Git repository on `main`.
- Pinned Hermes `0.19.0` at commit
  `a97b6ff8f646f197efa14d405a1130c9951dcdd9`.
- Pinned OO CLI `1.7.0` with linux/amd64 and linux/arm64 SHA-256 values.
- Added the minimal per-Skill description-limit patch.
- Added build-time OO framework Skill export and metadata configuration.
- Migrated the curated Office, PDF, and public-social-research Skills.
- Migrated GPT Image 2, Nano Banana, Seedance, and Jina provider Plugins.
- Added allowlisted Skill assembly and document-runtime verification.
- Added a non-root, persistent `/data` runtime with first-start-only config
  seeding.
- Added public project policy, architecture, development, upstream, licensing,
  CI, and release documentation.
- Passed 11 repository tests.
- Completed a native linux/arm64 image build and verified OO CLI `1.7.0`,
  Hermes CLI startup, UID `10000`, first-start configuration seeding, nine
  curated Skills, and the provider overlay.

## Source Mapping

The initial assets were extracted from the OOMOL-owned layer of
`oomol/hermes-agent`:

| New location | Original area |
| --- | --- |
| `patches/` | OOMOL patch in `agent/skill_utils.py` |
| `scripts/assemble-skills.py` | `oomol/assemble-hermes-skills.py` |
| `scripts/configure-oo-skills.py` | Generic subset of `oomol/configure-oo-skills.py` |
| `skills/` | `oomol/skills/` |
| `plugins/` | `oomol/plugins/` provider backends |
| Document requirements and verifier | `oomol/*requirements.txt`, `oomol/verify-document-runtime.py` |

Leina connection guidance, Platform Bindings, managed authentication writes,
Connector Skill webhooks, message-platform patches, and internal operations
tools were intentionally not migrated.

## Upstream Compatibility Update (2026-08-17)

- Updated Hermes from `0.19.0` to `0.20.2` at immutable commit
  `df4b65147d7ddd74dd449f9067aabbca5aef0ec7`.
- Updated OO CLI from `1.7.0` to `1.7.4`; verified the published linux/amd64
  and linux/arm64 artifacts against the SHA-256 values in
  `upstream.lock.json`.
- Reviewed the Hermes Skill parser and image, video, and web provider ABCs.
  The per-Skill description patch remains necessary and applies cleanly.
- Aligned the build and repository-test images with the upstream-selected
  Python 3.11 interpreter so Hermes can reuse the accessible base interpreter
  instead of installing a second uv-managed interpreter.
- Completed a native linux/arm64 image build. The final image reports Hermes
  `0.20.2`, OO CLI `1.7.4`, Python `3.11.15`, and UID `10000`.
- Verified first-start config seeding, direct `OO_API_KEY` recognition, and
  image-level discovery of all four enabled OO provider Plugins. The later
  terminal-authentication update supersedes the original non-persistence
  behavior.

## Provider Authentication Update (2026-08-17)

- Initially kept `OO_API_KEY` optional and added a shared device-login fallback
  for the four connector-backed providers.
- Added one shared authentication manager for all four OO providers. A provider
  hit while logged out starts `oo auth login`, returns the device-login URL to
  the chat, and keeps the bounded background process alive to persist the
  completed login under `/data`.
- Added real provider imports to the image build so discovery cannot pass while
  a shared runtime module is missing.
- Verified the logged-out URL flow in the final non-root image without making
  authentication a container-startup dependency.

## OOMOL Main Model Update (2026-08-17)

- Made `OO_API_KEY`, `OO_LLM_BASE_URL`, `OO_LLM_MODEL`, and `OO_LLM_API_MODE`
  required runtime inputs because OOMOL now supplies the main Hermes language
  model.
- Added the `oomol` model-provider Plugin through Hermes's provider ABC. It
  supports explicit `codex_responses` and `chat_completions` modes without a
  Hermes core patch.
- Declared the fixed OOMOL base URL directly through the environment and added
  local HTTPS `/v1` validation. Startup performs no OO CLI configuration query
  or remote health check.
- Seeded the normal base URL, `deepseek-v4-flash`, and `codex_responses` as
  recommendations in `.env.example`; none is a hidden runtime default.
- Retained first-start-only Hermes config seeding. The entrypoint materializes
  the three non-secret model settings and safely upgrades only their exact
  legacy placeholders in pre-existing volumes without overwriting customized
  model values.

## OO CLI Terminal Authentication Update (2026-08-17)

- Added a bounded, best-effort `oo auth login --api-key` call during startup.
  It persists a saved account under `/data/.config/oo`, allowing OO Skills to
  work inside Hermes terminal processes after provider environment credentials
  are scrubbed.
- Kept `OO_API_KEY` in the main process for the OOMOL model and provider
  Plugins. Authentication is staged and atomically replaced; login failure
  removes the previous saved account, warns, and does not prevent startup.
- Removed OOMOL credentials and model settings from terminal passthrough. A
  narrow migration cleans the exact previous seed block in existing volumes
  while preserving user-added variables.
- Added non-secret ownership state for materialized model settings so later
  environment changes update distribution-managed values without overwriting
  user customizations.

## Next Work, In Order

1. Run the first complete linux/amd64 Docker build and fix only real integration
   failures found against the pinned source.
2. Automate the image-level Plugin discovery check currently run manually.
3. Consolidate repeated OO subprocess, upload, polling, response parsing, and
   redaction code shared by provider Plugins.
4. Add `doctor` output for required environment, binary, model endpoint, and
   connector access states.
5. Add safe config migrations for existing volumes before changing seed
   defaults after the first release.
6. Confirm and document OO CLI redistribution/license terms.
7. Run the initial release workflow, verify its SBOM and provenance
   attestations, and publish `ghcr.io/oomol-lab/oomol-hermes-agent`.

## Known Design Debt

- The Provider Plugins duplicate their OO CLI client logic.
- The Dockerfile and `upstream.lock.json` duplicate version defaults; tests keep
  them synchronized, but a generated BuildKit input would be cleaner.
- The full document stack makes the single image heavy. Consider `core`,
  `office`, and `full` variants only after the first complete image works.
- `public-social-research` is intentionally OO-backed and has a long routing
  description. Confirm its public API and billing wording before release.

## Acceptance Criteria For The First Public Release

- Both supported architectures build from a clean checkout.
- Rebuilding with identical inputs resolves the same Hermes and OO versions.
- Container startup tolerates unavailable network access and authentication
  failures.
- Hermes fails clearly when required OOMOL runtime variables are absent.
- OOMOL authentication starts from runtime `OO_API_KEY`; oo-cli persists the
  corresponding login only in runtime `/data`, never in image layers.
- All four OO framework Skills appear with their full routing descriptions.
- Ordinary Skills retain the 60-character default.
- Curated Skills, the OOMOL model provider, and all four connector-backed
  Provider Plugins are discoverable.
- Representative Office/PDF work passes the image build verification.
- Public CI, image documentation, license notices, SBOM, and security contact
  are present.
