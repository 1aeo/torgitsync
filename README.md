# torgitsync

Dedicated sync controller keeping [`1aeo/tor`](https://github.com/1aeo/tor) (and our `gitlab.torproject.org` fork) synchronized with upstream [`tpo/core/tor`](https://gitlab.torproject.org/tpo/core/tor) without polluting `1aeo/tor`'s git history.

## What It Syncs

1. **Upstream → GitHub (`1aeo/tor`):**
   - `main`, `maint-*`, `release-*`, and all `refs/tags/*` from `https://gitlab.torproject.org/tpo/core/tor.git`.
   - Leaves all WIP / feature branches on `1aeo/tor` untouched.
2. **Upstream + `mr/*` → GitLab Fork (when GitLab secrets are configured):**
   - Keeps `main`, `maint-*`, `release-*`, and tags on `https://gitlab.torproject.org/<TOR_GITLAB_FORK_PATH>.git` aligned with upstream.
   - Syncs opt-in `mr/<branch>` branches from `1aeo/tor` → `<branch>` on the GitLab fork (stripping the `mr/` prefix) for submitting and updating GitLab Merge Requests. MR updates are fast-forward only; divergent maintainer edits or rebases stop publication until reconciled. Upstream mirror pushes request exact upstream refs, subject to destination protections.

## Mirror protection

Verified 2026-11-14: GitHub ruleset `27279925` blocks deletion and non-fast-forward updates of `main`, `maint-*`, and `release-*` with no bypass actors. Ruleset `26185050` also requires a reviewed pull request, with a repository-role bypass. These rules do **not** restrict writes exclusively to this sync controller: a permitted actor can still advance a branch. Tags are outside these branch rulesets.

The workflow's `+` mirror refspecs cannot override GitHub's no-bypass rule. Normal upstream fast-forwards continue to work; upstream rewinds or accidental divergent mirror commits cause sync to fail and need deliberate reconciliation. This workflow never changes branch protections to unblock itself.

The local `tor.git/hooks/pre-push` links to [hooks/tor-pre-push](hooks/tor-pre-push). It prevents accidental direct mirror/tag pushes, wrong destinations and MR deletion, and requires `CTOR_ALLOW_MR_PUSH=1` for an already-authorized `mr/*` submission to GitHub `1aeo/tor`. The flag records intent, not approval or test evidence. Hooks are local and bypassable (`--no-verify` or a changed hooks path); they are not a server authorization boundary.

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
2. Before pushing any `mr/*` branch to the GitLab fork, `sync-tor.yml` rejects reserved names and release-only ancestry, checks every outgoing commit for the expected identity and private metadata/artifacts, and runs upstream-baseline `checkSpace.pl`, `lintChanges.py`, and `practracker/includes.py` against the candidate. It also blocks the known private-canary metric identifiers from patch-stack commits 18/19, even in removed code or renamed branches. Candidate changes cannot replace these validators. This is a hygiene check; build and behavioral evidence remain the responsibility of `ctor-audit --build` and the effort review.
3. When ready to open or update a GitLab Merge Request, push under `mr/*` on `1aeo/tor` and trigger an immediate sync:

```bash
CTOR_ALLOW_MR_PUSH=1 git push origin topic/my-feature:mr/my-feature --force-with-lease
GH_TOKEN="$(gh auth token -u 1aeo)" gh workflow run sync-tor.yml -R 1aeo/torgitsync
GH_TOKEN="$(gh auth token -u 1aeo)" gh run watch -R 1aeo/torgitsync
```

If a GitLab MR branch diverges, fetch and review its changes before reconciling the source branch. The scheduled sync never force-updates an MR branch. Naming a ref after a release tag cannot be reconstructed from Git ancestry; use the worktree helper to select a supported development base.

## Local verification

`python3 -m unittest discover -s tests -v` exercises the actual workflow shell script against disposable local repositories, including lint failures, deleted private artifacts, validator replacement, symlink escapes, and divergent MR updates. It does not contact GitHub or GitLab. Run `actionlint .github/workflows/sync-tor.yml` for workflow validation.
