"""Exercise the actual workflow script against disposable local Git mirrors."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sync-tor.yml"
GIT = shutil.which("git")
BASH = shutil.which("bash")


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        self.git(self.seed, "init", "-b", "main")
        self.git(self.seed, "config", "user.name", "Upstream")
        self.git(self.seed, "config", "user.email", "upstream@example.invalid")
        self.write(self.seed, "src/example.c", "int example;\n")
        self.write(self.seed, "scripts/maint/checkSpace.pl", """
for (@ARGV) {
    next if /^-/;
    open(my $f, '<', $_) or die $!;
    while (<$f>) { exit 7 if /BAD_SPACE/; }
}
""")
        self.write(self.seed, "scripts/maint/lintChanges.py", """
import pathlib, sys
sys.exit(any('BAD_CHANGE' in pathlib.Path(p).read_text() for p in sys.argv[1:]))
""")
        self.write(self.seed, "scripts/maint/practracker/includes.py", """
import pathlib, sys
sys.exit('BAD_INCLUDE' in pathlib.Path('src/example.c').read_text())
""")
        self.commit(self.seed)
        self.upstream = self.root / "upstream.git"
        self.github = self.root / "github.git"
        self.fork = self.root / "fork.git"
        self.git(self.root, "clone", "--bare", str(self.seed), str(self.upstream))
        self.git(self.root, "clone", "--bare", str(self.seed), str(self.github))
        self.git(self.root, "init", "--bare", str(self.fork))
        self.topic = self.root / "topic"
        self.git(self.root, "clone", str(self.seed), str(self.topic))
        self.git(self.topic, "config", "user.name", "1aeo")
        self.git(self.topic, "config", "user.email", "github@1aeo.com")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        wrapper = self.bin / "git"
        wrapper.write_text("""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[:2] == ['remote', 'add']:
    target = {'upstream': 'upstream.git', 'github': 'github.git', 'gitlab': 'fork.git'}
    args[-1] = os.path.join(os.environ['FIXTURES'], target[args[2]])
os.execv(os.environ['REAL_GIT'], [os.environ['REAL_GIT'], *args])
""")
        wrapper.chmod(0o755)
        workflow = WORKFLOW.read_text()
        script = workflow.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
        self.script = self.root / "sync.sh"
        self.script.write_text(textwrap.dedent(script))

    def git(self, cwd, *args, check=True):
        return subprocess.run([GIT, "-C", str(cwd), *args], text=True,
                              capture_output=True, check=check)

    def write(self, repo, path, content):
        path = repo / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, repo, message="Test change"):
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-m", message)

    def run_sync(self, branch="feature", **extra_env):
        self.git(self.topic, "push", str(self.github), f"HEAD:refs/heads/mr/{branch}")
        runner = self.root / "runner"
        runner.mkdir()
        temp = self.root / "runner-temp"
        temp.mkdir()
        env = {**os.environ, "FIXTURES": str(self.root), "REAL_GIT": GIT,
               "PATH": f"{self.bin}:{os.environ['PATH']}", "RUNNER_TEMP": str(temp),
               "GH_PAT": "fake-github-token", "GH_REPO": "1aeo/tor",
               "GL_PAT": "fake-gitlab-token", "GL_FORK_PATH": "1aeo/tor",
               "GL_USER": "oauth2", "DRY_RUN": "false", **extra_env}
        result = subprocess.run([BASH, str(self.script)], cwd=runner, env=env,
                                text=True, capture_output=True)
        return result

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        ref = self.git(self.fork, "show-ref", "--verify", "refs/heads/feature", check=False)
        self.assertNotEqual(ref.returncode, 0)

    def test_valid_branch_and_upstream_are_synced(self):
        self.write(self.topic, "src/example.c", "int changed;\n")
        self.commit(self.topic)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = self.git(self.topic, "rev-parse", "HEAD").stdout
        self.assertEqual(head, self.git(self.fork, "rev-parse", "feature").stdout)
        self.assertEqual(self.git(self.seed, "rev-parse", "HEAD").stdout,
                         self.git(self.fork, "rev-parse", "main").stdout)

    def test_first_validator_failure_is_not_masked(self):
        self.write(self.topic, "src/example.c", "BAD_SPACE\n")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_middle_validator_failure_is_not_masked(self):
        self.write(self.topic, "changes/test", "BAD_CHANGE\n")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_candidate_cannot_replace_validator(self):
        self.write(self.topic, "src/example.c", "BAD_SPACE\n")
        self.write(self.topic, "scripts/maint/checkSpace.pl", "exit 0;\n")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_transient_private_content_is_rejected_without_echoing_it(self):
        secret_path = "/Users/private-operator/session-file"
        self.write(self.topic, "note.txt", secret_path + "\n" + "safe\n" * 30000)
        self.commit(self.topic)
        (self.topic / "note.txt").unlink()
        self.commit(self.topic)
        result = self.run_sync()
        self.assert_rejected(result)
        self.assertNotIn(secret_path, result.stdout + result.stderr)

    def test_transient_raw_artifact_is_rejected(self):
        self.write(self.topic, "samples.csv", "value\n1\n")
        self.commit(self.topic)
        (self.topic / "samples.csv").unlink()
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_private_canary_history_is_rejected_under_an_unrelated_branch_name(self):
        markers = ["relay_create_cell_source_total", "relay_begindir_cell_source_total",
                   "relay_hsdir_fetch_descriptor_total"]
        for marker in markers:
            self.write(self.topic, "src/example.c", f'const char *metric = "{marker}";\n')
            self.commit(self.topic)
        self.write(self.topic, "src/example.c", "int changed;\n")
        self.commit(self.topic)
        result = self.run_sync(branch="ordinary-bugfix")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("private-canary-only", result.stdout + result.stderr)
        self.assertNotEqual(self.git(self.fork, "show-ref", "--verify", "refs/heads/ordinary-bugfix", check=False).returncode, 0)
        for marker in markers:
            self.assertNotIn(marker, result.stdout + result.stderr)

    def test_binary_payload_does_not_hide_private_metadata(self):
        private = b"/Users/private-operator/session-file"
        (self.topic / "fixture.bin").write_bytes(b"\x00\xff" + private + b"\n")
        self.commit(self.topic)
        result = self.run_sync()
        self.assert_rejected(result)
        self.assertNotIn(private.decode(), result.stdout + result.stderr)

    def test_added_content_resembling_diff_header_is_checked(self):
        self.write(self.topic, "note.txt", "++ /Users/private-operator/session-file\n")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_transient_agent_file_is_rejected(self):
        self.write(self.topic, ".codex/config.toml", "instructions = 'test'\n")
        self.commit(self.topic)
        (self.topic / ".codex/config.toml").unlink()
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_private_root_commit_merged_without_its_file_is_rejected(self):
        self.git(self.topic, "checkout", "--orphan", "hidden")
        self.git(self.topic, "rm", "-rf", ".")
        self.write(self.topic, "samples.csv", "value\n1\n")
        self.commit(self.topic)
        self.git(self.topic, "checkout", "main")
        self.git(self.topic, "merge", "--allow-unrelated-histories", "--no-commit", "hidden")
        (self.topic / "samples.csv").unlink()
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_escaping_symlink_is_rejected(self):
        (self.topic / "src/leak.c").symlink_to("/proc/self/environ")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync())

    def test_reserved_branch_is_rejected(self):
        self.write(self.topic, "src/example.c", "int changed;\n")
        self.commit(self.topic)
        result = self.run_sync(branch="main")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.seed, "rev-parse", "HEAD").stdout,
                         self.git(self.fork, "rev-parse", "main").stdout)

    def test_canonical_upstream_is_not_a_fork_target(self):
        self.write(self.topic, "src/example.c", "int changed;\n")
        self.commit(self.topic)
        self.assert_rejected(self.run_sync(GL_FORK_PATH="https://gitlab.torproject.org/tpo/core/tor.git"))

    def test_dry_run_does_not_publish(self):
        self.write(self.topic, "src/example.c", "int changed;\n")
        self.commit(self.topic)
        result = self.run_sync(DRY_RUN="true")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.git(self.fork, "show-ref", "--verify", "refs/heads/feature", check=False).returncode, 0)

    def test_divergent_gitlab_changes_survive(self):
        self.write(self.topic, "src/example.c", "int maintainer;\n")
        self.commit(self.topic)
        old = self.git(self.topic, "rev-parse", "HEAD").stdout.strip()
        self.git(self.topic, "push", str(self.fork), "HEAD:refs/heads/feature")
        self.git(self.topic, "reset", "--hard", "HEAD^")
        self.write(self.topic, "src/example.c", "int developer;\n")
        self.commit(self.topic)
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(old, self.git(self.fork, "rev-parse", "feature").stdout.strip())


if __name__ == "__main__":
    unittest.main()
