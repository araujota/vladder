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
    DEFAULT_MODEL_TRAINING_ENDPOINT, DEFAULT_REVIEW_ENDPOINT,
    load_or_register_capability,
)
from vladder.training_workflow import (
    create_training_bundle_from_prior, create_training_bundle_from_promotion_summary,
    create_training_template, enqueue_training_bundle, export_all_training_bundles_from_prior,
    flush_training_outbox, submit_training_bundle, sync_all_training_bundles_from_prior,
    sync_promotion_summary, validate_training_bundle,
)
from vladder.model_training_data import graph_learning_examples, ingest_model_training_bundle
from vladder.training_privacy import load_or_create_training_identity, private_identity, sanitize_graph
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

    def _legacy_training_bundle(self) -> dict[str, object]:
        return {
            "schema_version": "vladder-training-bundle-v1",
            "bundle_id": "bundle:legacy-fixture",
            "created_at": "2026-08-09T00:00:00Z",
            "vladder_version": "1.0.0rc20",
            "producer": {"agent": "fixture", "model": "fixture", "provider": None},
            "dataset": {
                "project_id": "legacy-project",
                "grammar_version": "legacy-v1",
                "grammar_hash": "0" * 64,
                "hardware_class": "other",
                "hardware_manifest_hash": "0" * 64,
            },
            "examples": [{
                "example_id": "example:legacy-fixture",
                "semantic_root_hash": "0" * 64,
                "candidate_hash": "1" * 64,
                "language": "cpp",
                "region_kind": "legacy_fixture",
                "grammar_family": "legacy_fixture",
                "grammar_rule": "legacy_fixture",
                "numeric_features": [],
                "categorical_features": [],
                "evidence": {
                    "semantic_outcome": "proof_unknown",
                    "physical_outcome": "not_measured",
                    "proof_class": "none",
                    "quality_grade": "D",
                    "benchmark_scope": "none",
                    "speedup_percent": None,
                    "ci_lower_percent": None,
                    "ci_upper_percent": None,
                    "sample_count": 0,
                },
            }],
            "privacy": {
                "source_included": False,
                "raw_artifacts_included": False,
                "prompts_included": False,
                "personal_data_included": False,
                "submission_consent": True,
            },
        }

    def test_schema_registry_lists_stable_public_artifacts(self) -> None:
        report = list_artifact_schemas()
        self.assertEqual(report["schema_version"], "vladder-schema-registry-v1")
        self.assertEqual(
            set(report["artifacts"]),
            {
                "agent-review",
                "benchmark-result",
                "cross-tu-closure",
                "promotion-summary",
                "resource-protocol",
                "semantic-flow",
                "spirv-semantics",
                "system-closure",
                "model-training-bundle",
                "training-bundle",
                "whole-build-index",
            },
        )
        self.assertEqual(report["artifacts"]["model-training-bundle"]["stability"], "candidate")
        self.assertTrue(all(
            item["stability"] == "stable"
            for name, item in report["artifacts"].items() if name != "model-training-bundle"
        ))

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
            self.assertEqual(bundle["schema_version"], "vladder-model-training-bundle-v2")
            self.assertTrue(bundle["roots"][0]["graph"]["nodes"])
            self.assertTrue(bundle["candidates"][0]["baseline"])
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
            self.assertEqual(request.full_url, DEFAULT_MODEL_TRAINING_ENDPOINT + "?validate_only=true")
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
            self.assertEqual(bundle["schema_version"], "vladder-model-training-bundle-v2")
            self.assertGreater(len(bundle["candidates"]), 0)
            self.assertGreater(len(bundle["roots"]), 0)
            self.assertFalse(bundle["privacy"]["submission_consent"])
            serialized = bundle_path.read_text()
            self.assertIn('"graph"', serialized)
            self.assertNotIn('"semantic_graph"', serialized)
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
                sum(len(json.loads(Path(path).read_text())["candidates"]) for path in exported["bundles"]),
                exported["candidate_count"],
            )
            first_export = json.loads(Path(exported["bundles"][0]).read_text())
            self.assertNotEqual(first_export["roots"][0]["project_id"], "private-project-name")
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

    def test_model_training_v2_preserves_topology_and_round_trips_without_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_synthetic_prior_corpus(root / "corpus", root_count=3)
            identity = root / "identity.json"
            bundle_path = root / "model-training.json"
            bundle = create_training_bundle_from_prior(
                root / "corpus/experience", bundle_path,
                project_id="SecretEnterpriseRepository",
                producer_agent="codex", producer_model="fixture", maximum_examples=12,
                identity_path=identity,
            )
            serialized = bundle_path.read_text()
            self.assertEqual(bundle["privacy"]["risk_classification"], "pseudonymized_structural_data")
            self.assertTrue(bundle["privacy"]["topology_included"])
            self.assertNotIn("SecretEnterpriseRepository", serialized)
            self.assertNotIn("source_path", serialized)
            examples = graph_learning_examples(bundle_path)
            self.assertEqual(len(examples), len(bundle["candidates"]))
            self.assertTrue(any(example["graph"]["edge_index"][0] for example in examples))
            groups = {example["ranking_group"] for example in examples}
            self.assertLessEqual(len(groups), len(bundle["roots"]))
            report = ingest_model_training_bundle(bundle_path, root / "ingested")
            self.assertEqual(report["status"], "pass")
            ingested = __import__("vladder.prior_data", fromlist=["PriorExperienceStore"]).PriorExperienceStore(
                root / "ingested",
            ).load()
            self.assertGreater(len(ingested["candidates"]), 0)
            self.assertLessEqual(len(ingested["candidates"]), len(bundle["candidates"]))
            self.assertGreater(len(ingested["observations"]), 0)
            self.assertIn("collapses exact semantic clones", report["compatibility_note"])
            consent_path = root / "consent.json"
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=consent_path, confirmed_user_choice=True,
            )
            consented_path = root / "consented-model-training.json"
            create_training_bundle_from_prior(
                root / "corpus/experience", consented_path,
                project_id="SecretEnterpriseRepository", producer_agent="codex", producer_model="fixture",
                maximum_examples=4, identity_path=identity, apply_durable_consent=True,
                consent_path=consent_path,
            )
            with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_training"):
                with patch("urllib.request.urlopen") as urlopen:
                    response = urlopen.return_value.__enter__.return_value
                    response.status = 200
                    response.read.return_value = b'{"status":"valid","stored":false}'
                    submit_training_bundle(
                        consented_path, endpoint=None, token=None, confirm_upload=True,
                        validate_only=True, consent_path=consent_path,
                    )
                    request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, DEFAULT_MODEL_TRAINING_ENDPOINT + "?validate_only=true")

    def test_legacy_training_opt_in_requires_reconsent_for_structural_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            consent_path = Path(directory) / "consent.json"
            legacy = {
                "schema_version": "vladder-consent-v1",
                "policy_version": "vladder-contribution-consent-v2",
                "updated_at": "2026-01-01T00:00:00Z",
                "decisions": {
                    CANONICAL_TRAINING_DATA: {
                        "decision": "opt_in", "updated_at": "2026-01-01T00:00:00Z",
                        "decision_source": "explicit_user_direction",
                        "policy_version": "vladder-contribution-consent-v2",
                    },
                    AGENT_EXPERIENCE_REVIEW: {
                        "decision": "opt_in", "updated_at": "2026-01-01T00:00:00Z",
                        "decision_source": "explicit_user_direction",
                        "policy_version": "vladder-contribution-consent-v2",
                    },
                },
                "activity": {},
            }
            consent_path.write_text(json.dumps(legacy))
            ledger = load_consent(consent_path)
            self.assertEqual(ledger["states"][CANONICAL_TRAINING_DATA], "unknown")
            self.assertEqual(ledger["states"][AGENT_EXPERIENCE_REVIEW], "opt_in")
            self.assertEqual(ledger["stale_decisions"], [CANONICAL_TRAINING_DATA])

    def test_structural_deidentification_removes_source_vocabulary_and_uses_secret_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = {
                "nodes": [
                    {
                        "id": "AcmeSecret::PricingEngine::alpha.cpp:42",
                        "kind": "ProprietaryNodeKind", "operation": "secret_transform",
                        "output_type": "struct AcmeCustomerRecord", "trip_count": 37,
                        "source_path": "/enterprise/acme/alpha.cpp", "literal": "MATERIAL_SECRET",
                    },
                    {"id": "result", "kind": "Emit", "operation": "output", "output_type": "i32"},
                ],
                "edges": [{
                    "source": "AcmeSecret::PricingEngine::alpha.cpp:42", "destination": "result",
                    "relation": "private_relation_name",
                }],
            }
            sanitized = sanitize_graph(graph)
            rendered = json.dumps(sanitized)
            self.assertEqual([node["index"] for node in sanitized["nodes"]], [0, 1])
            self.assertEqual(sanitized["nodes"][0]["kind"], "Other")
            self.assertEqual(sanitized["nodes"][0]["operation"], "other")
            self.assertEqual(sanitized["edges"][0]["relation"], "other")
            for secret in ("Acme", "PricingEngine", "alpha.cpp", "MATERIAL_SECRET", "/enterprise"):
                self.assertNotIn(secret, rendered)
            first = load_or_create_training_identity(root / "first.json")
            second = load_or_create_training_identity(root / "second.json")
            self.assertEqual(private_identity(first, "root", "same"), private_identity(first, "root", "same"))
            self.assertNotEqual(private_identity(first, "root", "same"), private_identity(second, "root", "same"))
            with self.assertRaisesRegex(ValueError, "1 to 512"):
                sanitize_graph({"nodes": [{"id": f"n{index}"} for index in range(513)], "edges": []})

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
            self.assertEqual(bundle["schema_version"], "vladder-model-training-bundle-v2")
            self.assertGreaterEqual(len(bundle["roots"][0]["graph"]["nodes"]), 7)
            self.assertEqual(len(bundle["candidates"]), 2)
            self.assertTrue(bundle["candidates"][0]["baseline"])
            self.assertTrue(bundle["observations"])
            self.assertEqual(validate_training_bundle(root / "bundle.json")["status"], "pass")
            self.assertNotIn("private/project/path.cpp", json.dumps(bundle))
            with patch.dict("os.environ", {"VLADDER_TRAINING_OUTBOX_DIR": str(root / "outbox")}):
                with patch("vladder.contribution_transport.load_or_register_capability", return_value="vc1_training"):
                    with patch("urllib.request.urlopen") as urlopen:
                        response = urlopen.return_value.__enter__.return_value
                        response.status = 202
                        response.read.return_value = b'{"status":"accepted_for_moderation"}'
                        report = sync_promotion_summary(summary, root / "sync", consent_path=consent_path)
                        self.assertEqual(report["status"], "pass")
                        self.assertTrue(report["current_record_submitted"])
                        self.assertEqual(urlopen.call_count, 1)
                        self.assertEqual(
                            urlopen.call_args.args[0].full_url,
                            DEFAULT_MODEL_TRAINING_ENDPOINT,
                        )
                        self.assertEqual(list((root / "outbox").glob("*.json")), [])

    def test_training_outbox_retains_transport_failures_and_replays_on_next_opportunity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consent_path = root / "consent.json"
            outbox = root / "outbox"
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=consent_path, confirmed_user_choice=True,
            )
            bundle_path = root / "bundle.json"
            bundle = create_training_template(bundle_path)
            bundle["privacy"]["submission_consent"] = True
            bundle_path.write_text(json.dumps(bundle))
            queued = enqueue_training_bundle(bundle_path, outbox_directory=outbox)
            self.assertEqual(Path(queued["entry"]).stat().st_mode & 0o777, 0o600)
            with patch("vladder.training_workflow.submit_training_bundle", side_effect=RuntimeError("HTTP 429")):
                first = flush_training_outbox(outbox_directory=outbox, consent_path=consent_path)
            self.assertEqual(first["status"], "queued_for_retry")
            self.assertEqual(first["pending_count"], 1)
            with patch("vladder.training_workflow.submit_training_bundle", return_value={
                "status": "submitted", "payload_sha256": queued["payload_sha256"],
            }):
                second = flush_training_outbox(outbox_directory=outbox, consent_path=consent_path)
            self.assertEqual(second["status"], "pass")
            self.assertEqual(second["submitted_count"], 1)
            self.assertEqual(second["pending_count"], 0)

    def test_legacy_training_is_historical_only_and_quarantined_without_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consent_path = root / "consent.json"
            outbox = root / "outbox"
            set_consent(
                CANONICAL_TRAINING_DATA, "opt_in", path=consent_path, confirmed_user_choice=True,
            )
            legacy_path = root / "legacy.json"
            legacy_path.write_text(json.dumps(self._legacy_training_bundle()))
            self.assertEqual(validate_training_bundle(legacy_path)["status"], "pass")
            with self.assertRaisesRegex(ValueError, "historical only"):
                enqueue_training_bundle(legacy_path, outbox_directory=outbox)
            with self.assertRaisesRegex(ValueError, "legacy v1 upload is disabled"):
                submit_training_bundle(
                    legacy_path, endpoint=None, token=None, confirm_upload=True,
                    consent_path=consent_path,
                )
            outbox.mkdir()
            queued_legacy = outbox / "legacy.json"
            queued_legacy.write_text(json.dumps(self._legacy_training_bundle()))
            queued_legacy.chmod(0o600)
            with patch("vladder.training_workflow.submit_training_bundle") as submit:
                report = flush_training_outbox(
                    outbox_directory=outbox, consent_path=consent_path,
                )
            submit.assert_not_called()
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["quarantined_legacy_count"], 1)
            self.assertEqual(report["pending_count"], 0)
            self.assertTrue(Path(report["quarantined_legacy_entries"][0]).exists())

    def test_contributor_capability_is_scope_keyed_cached_and_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "credentials.json"
            with patch("vladder.contribution_transport._register_capability") as register:
                register.return_value = {
                    "credential_id": "credential:test", "scope": "training:write", "token": "vc1_training",
                }
                first = load_or_register_capability(
                    DEFAULT_MODEL_TRAINING_ENDPOINT, "training:write", timeout_seconds=1,
                    credential_path=credential_path,
                )
                second = load_or_register_capability(
                    DEFAULT_MODEL_TRAINING_ENDPOINT, "training:write", timeout_seconds=1,
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
