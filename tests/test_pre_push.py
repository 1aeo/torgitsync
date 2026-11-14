"""The local hook is tested directly; no network or Git pushes are involved."""
import os
from pathlib import Path
import subprocess
import unittest


HOOK = Path(__file__).resolve().parents[1] / "hooks/tor-pre-push"
SHA = "a" * 40
ZERO = "0" * 40


class PrePushTest(unittest.TestCase):
    def check_push(self, destination="refs/heads/mr/fix", *, allow=False,
                   url="https://1aeo@github.com/1aeo/tor.git", sha=SHA, extra=""):
        env = dict(os.environ)
        env.pop("CTOR_ALLOW_MR_PUSH", None)
        if allow:
            env["CTOR_ALLOW_MR_PUSH"] = "1"
        return subprocess.run([str(HOOK), "arbitrary-remote-name", url], env=env,
                              input=f"refs/heads/topic/fix {sha} {destination} {ZERO}\n{extra}",
                              capture_output=True, text=True)

    def test_authorized_opt_in_accepts_canonical_https_and_ssh_destinations(self):
        for url in ("https://1aeo@github.com/1aeo/tor.git", "https://github.com/1aeo/tor",
                    "git@github.com:1aeo/tor.git", "ssh://git@github.com/1aeo/tor.git"):
            with self.subTest(url=url):
                result = self.check_push(allow=True, url=url)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_opt_in_is_required(self):
        self.assertNotEqual(self.check_push().returncode, 0)

    def test_wrong_destination_is_rejected_despite_opt_in(self):
        for url in ("https://gitlab.torproject.org/1aeo/tor.git",
                    "https://github.com/another-account/tor.git",
                    "https://github.com/1aeo/tor-other.git",
                    "https://github.com.attacker.invalid/1aeo/tor.git"):
            with self.subTest(url=url):
                self.assertNotEqual(self.check_push(allow=True, url=url).returncode, 0)

    def test_mirror_tags_ad_hoc_and_reserved_mr_names_are_rejected(self):
        for ref in ("refs/heads/main", "refs/heads/maint-0.4.9", "refs/heads/release-0.4.9",
                    "refs/tags/test", "refs/heads/topic/test", "refs/heads/mr/main",
                    "refs/heads/mr/HEAD", "refs/heads/mr/maint-0.4.9", "refs/heads/mr/release-0.4.9"):
            with self.subTest(ref=ref):
                self.assertNotEqual(self.check_push(ref, allow=True).returncode, 0)

    def test_deletion_is_rejected_despite_opt_in(self):
        self.assertNotEqual(self.check_push(allow=True, sha=ZERO).returncode, 0)

    def test_all_refs_in_multi_ref_push_are_checked(self):
        second = f"refs/heads/topic/other {SHA} refs/heads/main {ZERO}\n"
        self.assertNotEqual(self.check_push(allow=True, extra=second).returncode, 0)


if __name__ == "__main__":
    unittest.main()
