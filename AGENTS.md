# torgitsync Rules

- GitHub account `1aeo` only: always prefix CLI calls with `GH_TOKEN="$(gh auth token -u 1aeo)"` and never run `gh auth switch` or `git config --global`.
- Commit locally as `1aeo <github@1aeo.com>`.
- `torgitsync` keeps `1aeo/tor` and the `gitlab.torproject.org` fork aligned with `tpo/core/tor` and enforces pre-MR hygiene checks on `mr/*` branches before pushing to GitLab.
- See `~/1aeo/ctor/tor-research/AGENTS.md` and `REGISTRY.md` for C-Tor effort tracking.
