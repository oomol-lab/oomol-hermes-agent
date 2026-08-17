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

## Next Work, In Order

1. Run the first complete linux/amd64 Docker build and fix only real integration
   failures found against the pinned source.
2. Add an image-level Plugin discovery smoke test, not only compile checks.
3. Consolidate repeated OO subprocess, upload, polling, response parsing, and
   redaction code shared by provider Plugins.
4. Add `doctor` output for missing `OO_API_KEY` or persisted login, binary, and
   connector access states.
5. Decide whether OO providers should be selected by default before login or
   merely preinstalled and selectable through `hermes tools`.
6. Add safe config migrations for existing volumes before changing seed
   defaults after the first release.
7. Confirm and document OO CLI redistribution/license terms.
8. Generate an SBOM and provenance attestation in the release workflow.
9. Publish the initial image to `ghcr.io/oomol/oomol-hermes-agent`.

## Known Design Debt

- The Provider Plugins duplicate their OO CLI client logic.
- The seed selects OO providers even when OO is not authenticated. Hermes still
  starts, but the first-call failure experience must be evaluated.
- The Dockerfile and `upstream.lock.json` duplicate version defaults; tests keep
  them synchronized, but a generated BuildKit input would be cleaner.
- The full document stack makes the single image heavy. Consider `core`,
  `office`, and `full` variants only after the first complete image works.
- `public-social-research` is intentionally OO-backed and has a long routing
  description. Confirm its public API and billing wording before release.

## Acceptance Criteria For The First Public Release

- Both supported architectures build from a clean checkout.
- Rebuilding with identical inputs resolves the same Hermes and OO versions.
- Container startup performs no network access.
- Hermes starts without OO authentication.
- OO authentication works through runtime `OO_API_KEY` or persisted `/data`
  state, and no credential enters image layers.
- All four OO framework Skills appear with their full routing descriptions.
- Ordinary Skills retain the 60-character default.
- Curated Skills and all four Provider Plugins are discoverable.
- Representative Office/PDF work passes the image build verification.
- Public CI, image documentation, license notices, SBOM, and security contact
  are present.
