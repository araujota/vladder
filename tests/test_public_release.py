from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from vladder.consent import (
    AGENT_EXPERIENCE_REVIEW,
    CANONICAL_TRAINING_DATA,
    ConsentRequiredError,
    load_consent,
    record_review_request,
    set_consent,
)
from vladder.review_workflow import create_review_template, submit_review, validate_review
from vladder.contribution_transport import (
    DEFAULT_REVIEW_ENDPOINT, DEFAULT_TRAINING_ENDPOINT, load_or_register_capability,
)
from vladder.training_workflow import (
    create_training_bundle_from_prior, create_training_bundle_from_promotion_summary,
    create_training_template, export_all_training_bundles_from_prior, submit_training_bundle,
    sync_all_training_bundles_from_prior, sync_promotion_summary, validate_training_bundle,
)
from vladder.prior_synthetic import generate_synthetic_prior_corpus
from vladder.paired_benchmark import run_paired_benchmark
from vladder.schema_registry import list_artifact_schemas, validate_artifact
from scripts.validate_release_seeds import validate as validate_release_seeds


class PublicReleaseContractTests(unittest.TestCase):
    def _summary(self) -> dict[str, object]:
        return {
            "schema_version": "vladder-promotion-summary-v1",
            "workflow_kind": "cpp",
            "states": {
                "workflow_completed": True,
                "meaningful_semantic_coverage": True,
                "candidate_generated": True,
                "candidate_proved": True,
                "physically_benchmarked": False,
                "application_integrated": False,
                "production_promoted": False,
                "production_retained": False,
            },
            "proof_class": "local_ir_effects_captured",
            "disposition": "proof_unit_only",
            "result_classification": "candidate_proved_not_benchmarked",
            "promotion_permitted": False,
            "blockers": ["application benchmark adapter required"],
            "next_action": "complete the benchmark adapter",
            "claim_boundary": "local proof does not establish owning wrapper equivalence",
        }

    def test_schema_registry_lists_stable_public_artifacts(self) -> None:
        report = list_artifact_schemas()
        self.assertEqual(report["schema_version"], "vladder-schema-registry-v1")
        self.assertEqual(
            set(report["artifacts"]),
            {
                "agent-review",
                "benchmark-result",
                "promotion-summary",
                "semantic-flow",
                "system-closure",
                "training-bundle",
            },
        )
        self.assertTrue(all(item["stability"] == "stable" for item in report["artifacts"].values()))

    def test_promotion_summary_validation_accepts_contract_and_rejects_missing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "promotion-summary.json"
            payload = self._summary()
            path.write_text(json.dumps(payload))
            self.assertEqual(validate_artifact("promotion-summary", path)["status"], "pass")
            del payload["states"]["candidate_proved"]  # type: ignore[index]
            path.write_text(json.dumps(payload))
            report = validate_artifact("promotion-summary", path)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("candidate_proved" in item["message"] for item in report["errors"]))

    def test_review_template_is_local_and_upload_requires_all_consent_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "promotion-summary.json"
            summary.write_text(json.dumps(self._summary()))
            review_path = root / "review.json"
            consent_path = root / "consent.json"
            review = create_review_template(
                summary, review_path, project_name="fixture", project_revision="1234567",
            )
            self.assertFalse(review["privacy"]["submission_consent"])
            self.assertEqual(validate_review(review_path)["status"], "pass")
            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaisesRegex(ConsentRequiredError, "must ask the user"):
                    submit_review(
                        review_path, endpoint="https://example.invalid", token="secret", confirm_upload=True,
                        consent_path=consent_path,
                    )
                set_consent(
                    AGENT_EXPERIENCE_REVIEW, "opt_in", path=consent_path, confirmed_user_choice=True,
                )
                with self.assertRaisesRegex(ValueError, "disabled by default"):
                    submit_review(
                        review_path, endpoint="https://example.invalid", token="secret", confirm_upload=False,
                        consent_path=consent_path,
                    )
                with self.assertRaisesRegex(ValueError, "submission_consent=true"):
                    submit_review(
                        review_path, endpoint="https://example.invalid", token="secret", confirm_upload=True,
                        consent_path=consent_path,
                    )
                urlopen.assert_not_called()

    def test_consent_decisions_are_scoped_persistent_and_opt_out_is_sticky(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            consent_path = Path(directory) / "state" / "consent.json"
            initial = load_consent(consent_path)
            self.assertEqual(initial["states"][CANONICAL_TRAINING_DATA], "unknown")
            self.assertEqual(initial["states"][AGENT_EXPERIENCE_REVIEW], "unknown")
            self.assertIn("every eligible", initial["scope_notices"][CANONICAL_TRAINING_DATA]["frequency"])
            set_consent(CANONICAL_TRAINING_DATA, "opt_out", path=consent_path, confirmed_user_choice=True)
            reloaded = load_consent(consent_path)
            self.assertEqual(reloaded["states"][CANONICAL_TRAINING_DATA], "opt_out")
            self.assertEqual(reloaded["states"][AGENT_EXPERIENCE_REVIEW], "unknown")
            self.assertEqual(consent_path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ConsentRequiredError, "do not upload or ask again"):
                from vladder.consent import require_consent
                require_consent(CANONICAL_TRAINING_DATA, consent_path)

    def test_review_opt_in_uses_persistent_periodic_request_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            consent_path = Path(directory) / "consent.json"
            ledger = set_consent(
                AGENT_EXPERIENCE_REVIEW, "opt_in", path=consent_path, confirmed_user_choice=True,
            )
            self.assertEqual(ledger["review_request"]["status"], "due")
            ledger = record_review_request(path=consent_path, confirmed_user_prompt=True)
            self.assertEqual(ledger["review_request"]["status"], "not_due")
            self.assertEqual(load_consent(consent_path)["review_request"]["interval_days"], 30)

    def test_review_submission_uses_installation_scoped_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "promotion-summary.json"
            summary.write_text(json.dumps(self._summary()))
            review_path = root / "review.json"
            consent_path = root / "consent.json"
            review = create_review_template(summary, review_path, project_name="fixture", project_revision="1234567")
            review["privacy"]["submission_consent"] = True
            review_path.write_text(json.dumps(review))
            set_consent(AGENT_EXPERIENCE_REVIEW, "opt_in", path=consent_path, confirmed_user_choice=True)
            with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_review"):
                with patch("urllib.request.urlopen") as urlopen:
                    response = urlopen.return_value.__enter__.return_value
                    response.status = 202
                    response.read.return_value = b'{"status":"accepted_for_moderation"}'
                    result = submit_review(
                        review_path, endpoint=None, token=None, confirm_upload=True, consent_path=consent_path,
                    )
                    request = urlopen.call_args.args[0]
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(request.full_url, DEFAULT_REVIEW_ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer vc1_review")
        self.assertEqual(result["authorization"], "installation_scoped_capability")

    def test_training_bundle_is_source_free_and_capability_submittable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "training.json"
            consent_path = Path(directory) / "consent.json"
            bundle = create_training_template(bundle_path)
            self.assertEqual(validate_training_bundle(bundle_path)["status"], "pass")
            with self.assertRaisesRegex(ConsentRequiredError, "must ask the user"):
                submit_training_bundle(
                    bundle_path, endpoint=None, token=None, confirm_upload=False, consent_path=consent_path,
                )
            set_consent(CANONICAL_TRAINING_DATA, "opt_in", path=consent_path, confirmed_user_choice=True)
            with self.assertRaisesRegex(ValueError, "disabled by default"):
                submit_training_bundle(
                    bundle_path, endpoint=None, token=None, confirm_upload=False, consent_path=consent_path,
                )
            bundle["privacy"]["submission_consent"] = True
            bundle_path.write_text(json.dumps(bundle))
            with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_training"):
                with patch("urllib.request.urlopen") as urlopen:
                    response = urlopen.return_value.__enter__.return_value
                    response.status = 200
                    response.read.return_value = b'{"status":"valid","stored":false}'
                    result = submit_training_bundle(
                        bundle_path, endpoint=None, token=None, confirm_upload=True, validate_only=True,
                        consent_path=consent_path,
                    )
                    request = urlopen.call_args.args[0]
            self.assertEqual(result["status"], "validated_remotely")
            self.assertEqual(request.full_url, DEFAULT_TRAINING_ENDPOINT + "?validate_only=true")
            self.assertEqual(request.get_header("Authorization"), "Bearer vc1_training")
            bundle["privacy"]["source_included"] = True
            bundle_path.write_text(json.dumps(bundle))
            self.assertEqual(validate_training_bundle(bundle_path)["status"], "fail")

    def test_canonical_prior_store_derives_only_source_free_contribution_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_synthetic_prior_corpus(root / "corpus", root_count=3)
            bundle_path = root / "training.json"
            bundle = create_training_bundle_from_prior(
                root / "corpus/experience", bundle_path,
                project_id="opaque-fixture", producer_agent="codex", producer_model="fixture",
                maximum_examples=8,
            )
            self.assertEqual(validate_training_bundle(bundle_path)["status"], "pass")
            self.assertGreater(len(bundle["examples"]), 0)
            self.assertFalse(bundle["privacy"]["submission_consent"])
            serialized = bundle_path.read_text()
            self.assertNotIn("semantic_graph", serialized)
            self.assertNotIn("provenance", serialized)
            with self.assertRaisesRegex(ConsentRequiredError, "must ask the user"):
                create_training_bundle_from_prior(
                    root / "corpus/experience", root / "blocked.json",
                    project_id="opaque-fixture", producer_agent="codex", producer_model="fixture",
                    maximum_examples=2, apply_durable_consent=True, consent_path=root / "consent.json",
                )
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=root / "consent.json", confirmed_user_choice=True,
            )
            consented = create_training_bundle_from_prior(
                root / "corpus/experience", root / "consented.json",
                project_id="opaque-fixture", producer_agent="codex", producer_model="fixture",
                maximum_examples=2, apply_durable_consent=True, consent_path=root / "consent.json",
            )
            self.assertTrue(consented["privacy"]["submission_consent"])
            exported = export_all_training_bundles_from_prior(
                root / "corpus/experience", root / "export",
                project_id="private-project-name", producer_agent="codex", producer_model="fixture",
                examples_per_bundle=2,
            )
            self.assertTrue(exported["all_supported_candidates_exported"])
            self.assertEqual(
                sum(len(json.loads(Path(path).read_text())["examples"]) for path in exported["bundles"]),
                exported["candidate_count"],
            )
            first_export = json.loads(Path(exported["bundles"][0]).read_text())
            self.assertNotEqual(first_export["dataset"]["project_id"], "private-project-name")
            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaisesRegex(ConsentRequiredError, "must ask the user"):
                    sync_all_training_bundles_from_prior(
                        root / "corpus/experience", root / "blocked-sync",
                        project_id="private-project-name", producer_agent="codex", producer_model="fixture",
                        consent_path=root / "unknown-consent.json",
                    )
                urlopen.assert_not_called()
            with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_training"):
                with patch("urllib.request.urlopen") as urlopen:
                    response = urlopen.return_value.__enter__.return_value
                    response.status = 200
                    response.read.return_value = b'{"status":"valid","stored":false}'
                    synced = sync_all_training_bundles_from_prior(
                        root / "corpus/experience", root / "sync",
                        project_id="private-project-name", producer_agent="codex", producer_model="fixture",
                        examples_per_bundle=2, validate_only=True, consent_path=root / "consent.json",
                    )
                    self.assertEqual(urlopen.call_count, synced["export"]["bundle_count"])
                    self.assertTrue(synced["continuous_opt_in_applied"])

    def test_review_schema_rejects_source_or_raw_artifact_inclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "promotion-summary.json"
            summary.write_text(json.dumps(self._summary()))
            review_path = root / "review.json"
            review = create_review_template(summary, review_path, project_name="fixture", project_revision="1234567")
            review["privacy"]["source_included"] = True
            review_path.write_text(json.dumps(review))
            report = validate_review(review_path)
        self.assertEqual(report["status"], "fail")

    def test_generic_promotion_summary_contribution_is_anonymized_and_consent_gated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consent_path = root / "consent.json"
            summary = self._summary()
            summary["workflow_key"] = "a" * 64
            summary["blockers"] = ["private/project/path.cpp requires adapter"]
            with self.assertRaisesRegex(ConsentRequiredError, "must ask the user"):
                create_training_bundle_from_promotion_summary(
                    summary, root / "blocked.json", consent_path=consent_path,
                )
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=consent_path, confirmed_user_choice=True,
            )
            bundle = create_training_bundle_from_promotion_summary(
                summary, root / "bundle.json", consent_path=consent_path,
            )
            self.assertEqual(validate_training_bundle(root / "bundle.json")["status"], "pass")
            self.assertNotIn("private/project/path.cpp", json.dumps(bundle))
            with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_training"):
                with patch("urllib.request.urlopen") as urlopen:
                    response = urlopen.return_value.__enter__.return_value
                    response.status = 202
                    response.read.return_value = b'{"status":"accepted_for_moderation"}'
                    report = sync_promotion_summary(summary, root / "sync", consent_path=consent_path)
                    self.assertEqual(report["status"], "pass")
                    self.assertEqual(urlopen.call_count, 1)

    def test_contributor_capability_is_scope_keyed_cached_and_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "credentials.json"
            with patch("vladder.contribution_transport._register_capability") as register:
                register.return_value = {
                    "credential_id": "credential:test", "scope": "training:write", "token": "vc1_training",
                }
                first = load_or_register_capability(
                    DEFAULT_TRAINING_ENDPOINT, "training:write", timeout_seconds=1,
                    credential_path=credential_path,
                )
                second = load_or_register_capability(
                    DEFAULT_TRAINING_ENDPOINT, "training:write", timeout_seconds=1,
                    credential_path=credential_path,
                )
            self.assertEqual(first, "vc1_training")
            self.assertEqual(second, first)
            self.assertEqual(register.call_count, 1)
            self.assertEqual(credential_path.stat().st_mode & 0o777, 0o600)
            serialized = credential_path.read_text()
            self.assertIn("training:write", serialized)
            self.assertNotIn("review:write", serialized)

    def test_actual_paired_benchmark_output_matches_stable_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "paired.yaml"
            manifest.write_text(
                "\n".join([
                    f'executable: "{sys.executable}"',
                    "baseline_args:",
                    "  - -c",
                    '  - \'import json; print(json.dumps({"metric": 2.0, "hash": "same"}))\'',
                    "candidate_args:",
                    "  - -c",
                    '  - \'import json; print(json.dumps({"metric": 1.0, "hash": "same"}))\'',
                    "processes: 2",
                    "repetitions_per_process: 1",
                    "bootstrap_rounds: 20",
                    "metric_key: metric",
                    "observable_key: hash",
                    "exact_observables: true",
                    "minimum_effect_percent: 1",
                ]) + "\n"
            )
            output = root / "out"
            report = run_paired_benchmark(manifest, output)
            validation = validate_artifact("benchmark-result", output / "paired-benchmark.json")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(validation["status"], "pass")

    def test_seeded_good_and_bad_transformations_have_expected_dispositions(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            report = validate_release_seeds(
                root / "examples" / "release_seeds" / "transformations.yaml",
                Path(directory),
            )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["accepted_seed_count"], 2)
        self.assertEqual(report["rejected_seed_count"], 2)


if __name__ == "__main__":
    unittest.main()
