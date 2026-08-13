from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vladder.release_readiness import (
    ReadinessCheck, TARGETS, _online_checks, _read_toml, _target_summary, evaluate_release_readiness,
)


ROOT = Path(__file__).resolve().parent.parent


class ReleaseReadinessTests(unittest.TestCase):
    def test_static_report_is_target_aware_and_actionable(self):
        report = evaluate_release_readiness(ROOT)
        self.assertEqual(report["schema_version"], "vladder-release-readiness-v2")
        self.assertEqual(set(report["targets"]), set(TARGETS))
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["source.version-identity"]["status"], "pass")
        self.assertEqual(checks["source.pypi-metadata"]["status"], "pass")
        self.assertEqual(checks["homebrew.python-resource-closure"]["status"], "pass")
        self.assertEqual(checks["validation.full-tests"]["status"], "not_run")
        self.assertEqual(
            checks["validation.production-canonical-search-smoke"]["status"],
            "not_run",
        )
        self.assertTrue(report["next_actions"])

    def test_target_summary_does_not_hide_setup_or_unavailable_states(self):
        checks = [
            ReadinessCheck("ok", "source", "ok", "pass", "ok"),
            ReadinessCheck("pypi", "channels", "publisher", "setup_required", "missing", blocks=("pypi", "formal_release")),
            ReadinessCheck("brew", "channels", "tap", "unavailable", "missing", blocks=("homebrew", "formal_release")),
            ReadinessCheck("note", "source", "note", "warning", "warning"),
        ]
        summary = _target_summary(checks)
        self.assertTrue(summary["release_candidate"]["ready"])
        self.assertFalse(summary["pypi"]["ready"])
        self.assertFalse(summary["homebrew"]["ready"])
        self.assertEqual(summary["formal_release"]["blocker_count"], 2)

    def test_report_writer_can_target_an_isolated_work_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            report = evaluate_release_readiness(ROOT, work_directory=Path(directory))
            self.assertEqual(report["work_directory"], str(Path(directory).resolve()))

    def test_online_channels_pass_only_with_public_state_and_private_setup_attestations(self):
        channels = _read_toml(ROOT / "release" / "channels.toml")
        channels["pypi"]["trusted_publisher_configured"] = True
        channels["testpypi"]["trusted_publisher_configured"] = True
        channels["homebrew"]["tap_configured"] = True

        def gh_result(_root, arguments):
            joined = " ".join(arguments)
            if "repo view araujota/vladder" in joined:
                return 0, {"visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}}, ""
            if "branches/main/protection" in joined:
                return 0, {"required_status_checks": {"contexts": ["CI"]}}, ""
            if arguments[:2] == ["run", "list"]:
                return 0, [{"status": "completed", "conclusion": "success"}], ""
            if arguments[-1] == "repos/araujota/vladder/environments":
                return 0, {
                    "environments": [
                        {"name": name, "protection_rules": [{"type": "required_reviewers"}]}
                        for name in ("pypi", "testpypi", "homebrew")
                    ]
                }, ""
            if arguments[:2] == ["variable", "list"]:
                return 0, [{"name": "HOMEBREW_TAP_REPOSITORY", "value": "araujota/homebrew-tap"}], ""
            if arguments[:2] == ["secret", "list"]:
                return 0, [{"name": "HOMEBREW_TAP_TOKEN"}], ""
            if "repo view araujota/homebrew-tap" in joined:
                return 0, {"visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}}, ""
            raise AssertionError(arguments)

        def http_result(url):
            if url.endswith("/api/health"):
                return 200, {"status": "ok", "capability_submission": True}
            return 200, {"info": {"version": "1.0.0rc29"}}

        with patch("vladder.release_readiness.shutil.which", return_value="/usr/bin/gh"), patch(
            "vladder.release_readiness._gh_json", side_effect=gh_result
        ), patch("vladder.release_readiness._http_json", side_effect=http_result):
            checks = _online_checks(ROOT, channels)
        self.assertTrue(checks)
        self.assertTrue(all(check.status == "pass" for check in checks), [check.to_dict() for check in checks])

    def test_explicit_testpypi_waiver_is_visible_and_non_blocking(self):
        channels = _read_toml(ROOT / "release" / "channels.toml")
        channels["pypi"]["trusted_publisher_configured"] = True
        channels["testpypi"].update({
            "trusted_publisher_configured": False,
            "waived": True,
            "waived_by": "release-owner",
            "waived_at": "2026-08-06",
            "waiver_reason": "No TestPyPI account is maintained.",
        })

        def gh_result(_root, arguments):
            joined = " ".join(arguments)
            if "repo view araujota/vladder" in joined:
                return 0, {"visibility": "PUBLIC", "defaultBranchRef": {"name": "main"}}, ""
            if "branches/main/protection" in joined:
                return 0, {"required_status_checks": {"contexts": ["CI"]}}, ""
            if arguments[:2] == ["run", "list"]:
                return 0, [{"status": "completed", "conclusion": "success"}], ""
            if arguments[-1] == "repos/araujota/vladder/environments":
                return 0, {"environments": [
                    {"name": name, "protection_rules": [{"type": "required_reviewers"}]}
                    for name in ("pypi", "testpypi", "homebrew")
                ]}, ""
            if arguments[:2] == ["variable", "list"]:
                return 0, [], ""
            if arguments[:2] == ["secret", "list"]:
                return 0, [], ""
            if "repo view araujota/homebrew-tap" in joined:
                return 1, None, "missing"
            raise AssertionError(arguments)

        def http_result(url):
            if "test.pypi.org/pypi" in url:
                return 404, None
            if "pypi.org/pypi" in url:
                return 404, None
            return 200, {"status": "ok", "capability_submission": True}

        with patch("vladder.release_readiness.shutil.which", return_value="/usr/bin/gh"), patch(
            "vladder.release_readiness._gh_json", side_effect=gh_result
        ), patch("vladder.release_readiness._http_json", side_effect=http_result):
            checks = _online_checks(ROOT, channels)
        testpypi = next(check for check in checks if check.check_id == "testpypi.trusted-publisher")
        self.assertEqual(testpypi.status, "warning")
        self.assertIn("waived_by=release-owner", testpypi.detail)
        self.assertTrue(_target_summary(checks)["pypi"]["ready"])


if __name__ == "__main__":
    unittest.main()
