# Contributing

Read `AGENTS.md` and the relevant document under `docs/` before changing the
project. Keep contributions inside the standalone distribution scope and avoid
introducing private OOMOL deployment dependencies.

Use focused Conventional Commits, include tests proportional to risk, and run:

```sh
uv run pytest
git diff --check
```

Docker, upstream, dependency, Skill, or Provider changes also require a full
image build before release.
