# torgitsync

Dedicated sync controller keeping [`1aeo/tor`](https://github.com/1aeo/tor) (and our `gitlab.torproject.org` fork) synchronized with upstream [`tpo/core/tor`](https://gitlab.torproject.org/tpo/core/tor) without polluting `1aeo/tor`'s git history.

## What It Syncs

1. **Upstream → GitHub (`1aeo/tor`):**
   - `main`, `maint-*`, `release-*`, and all `refs/tags/*` from `https://gitlab.torproject.org/tpo/core/tor.git`.
   - Leaves all WIP / feature branches on `1aeo/tor` untouched.
2. **Upstream + `mr/*` → GitLab Fork (when GitLab secrets are configured):**
   - Keeps `main`, `maint-*`, `release-*`, and tags on `https://gitlab.torproject.org/<TOR_GITLAB_FORK_PATH>.git` aligned with upstream.
   - Syncs opt-in `mr/<branch>` branches from `1aeo/tor` → `<branch>` on the GitLab fork (stripping the `mr/` prefix) for submitting and updating GitLab Merge Requests.

## Repository Secrets (`1aeo/torgitsync`)

| Secret | Required | Description |
| :--- | :--- | :--- |
| `TOR_SYNC_GITHUB_PAT` | **Yes** | Fine-grained GitHub PAT (`1aeo`) scoped to `1aeo/tor` with **Contents: Read and write** |
| `TOR_GITLAB_FORK_PATH` | When GitLab fork ready | Path on `gitlab.torproject.org`, e.g. `<user>/tor` |
| `TOR_SYNC_GITLAB_PAT` | When GitLab fork ready | GitLab Personal or Project Access Token with `write_repository` |
| `TOR_GITLAB_USER` | Optional | GitLab username (defaults to `oauth2`, which works for all GitLab PATs) |

Optional repository variable:
- `TOR_GITHUB_REPO` (defaults to `1aeo/tor`)

### Configure Secrets via `gh` (as user `1aeo`)

```bash
GH_TOKEN="$(gh auth token -u 1aeo)" gh secret set TOR_SYNC_GITHUB_PAT  -R 1aeo/torgitsync
GH_TOKEN="$(gh auth token -u 1aeo)" gh secret set TOR_GITLAB_FORK_PATH -R 1aeo/torgitsync
GH_TOKEN="$(gh auth token -u 1aeo)" gh secret set TOR_SYNC_GITLAB_PAT  -R 1aeo/torgitsync
```

## Publishing a Branch to GitLab for an MR

1. Develop and review on `1aeo/tor` (`topic/*` branches off `main` or `maint-*`) and pass `~/1aeo/ctor/tor-research/bin/ctor-audit --build`.
2. Before pushing any `mr/*` branch to the GitLab fork, `sync-tor.yml` enforces a pre-MR hygiene gate (rejects reserved names and `release-*`/tag bases, enforces `1aeo <github@1aeo.com>` author/committer identity, blocks local path/agent-file leaks, and runs `checkSpace.pl`, `lintChanges.py`, and `checkIncludes.py`).
3. When ready to open or update a GitLab Merge Request, push under `mr/*` on `1aeo/tor` and trigger an immediate sync:

```bash
git push origin topic/my-feature:mr/my-feature --force-with-lease
GH_TOKEN="$(gh auth token -u 1aeo)" gh workflow run sync-tor.yml -R 1aeo/torgitsync
GH_TOKEN="$(gh auth token -u 1aeo)" gh run watch -R 1aeo/torgitsync
```
