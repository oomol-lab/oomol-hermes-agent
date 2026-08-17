# Contributing

Contributors need Git and Docker with BuildKit and Docker Compose. Python and
`uv` run only inside build containers and do not need to be installed on the
development host.

Read `AGENTS.md` and the document matching the work under `docs/` before making
changes. Keep contributions inside the standalone distribution scope and do
not introduce private OOMOL deployment dependencies.

Use focused Conventional Commits and include tests proportional to risk. Before
committing, run:

```sh
make check
```

Docker, upstream, dependency, Skill, and Provider changes also require the full
image build and smoke checks documented in `docs/development.md`. Keep upstream
updates in a dedicated `chore(upstream)` commit, and never commit credentials,
`.env`, runtime state, or generated artifacts.
