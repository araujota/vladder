from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .capabilities import GrammarRegistry, load_registry
from .lowering import LoweringEngine, LoweringRequest, LoweringResult
from .verification_policy import VerificationPolicy


@dataclass(frozen=True)
class BenchmarkPolicy:
    element_count: int = 1 << 20
    repetitions: int = 25
    inner_calls: int = 8
    cpu: int = 0
    flush_cache: bool = False
    collect_perf: bool = False


@dataclass(frozen=True)
class OptimizationRequest:
    source: Path
    function: str
    output_directory: Path
    verification_policy: VerificationPolicy = VerificationPolicy.STRICT
    minimum_speedup_pct: float = 1.0
    benchmark: BenchmarkPolicy = field(default_factory=BenchmarkPolicy)
    assume_no_alias: bool = False
    graph_inner_loop: bool = True
    search_nodes: int = 64
    search_milliseconds: int = 1000
    llm_lift: bool = False
    llm_rounds: int = 3

    def argv(self) -> list[str]:
        args = [
            "optimize",
            str(self.source),
            "--function",
            self.function,
            "--out-dir",
            str(self.output_directory),
            "--verification-policy",
            self.verification_policy.value,
            "--min-speedup-pct",
            str(self.minimum_speedup_pct),
            "--n",
            str(self.benchmark.element_count),
            "--reps",
            str(self.benchmark.repetitions),
            "--inner",
            str(self.benchmark.inner_calls),
            "--cpu",
            str(self.benchmark.cpu),
            "--search-nodes",
            str(self.search_nodes),
            "--search-ms",
            str(self.search_milliseconds),
        ]
        if self.verification_policy is VerificationPolicy.STRICT:
            args.append("--alive2")
        if self.assume_no_alias:
            args.append("--assume-no-alias")
        if self.graph_inner_loop:
            args.append("--graph-inner-loop")
        if self.benchmark.flush_cache:
            args.append("--flush-cache")
        if self.benchmark.collect_perf:
            args.append("--perf")
        if self.llm_lift:
            args.extend(("--llm-lift", "--llm-rounds", str(self.llm_rounds)))
        return args


@dataclass(frozen=True)
class OptimizationResult:
    return_code: int
    report_path: Path
    report: dict[str, Any]

    @property
    def promoted(self) -> bool:
        return bool(self.report.get("promotion", {}).get("promotable", False))

    @property
    def winner(self) -> dict[str, Any] | None:
        value = self.report.get("winner")
        return value if isinstance(value, dict) else None

    @property
    def patch_path(self) -> Path | None:
        value = self.report.get("promoted_patch")
        return self.report_path.parent / str(value) if value else None


@dataclass(frozen=True)
class AutomaticRegionRequest:
    source: Path
    function: str
    output_directory: Path
    minimum_speedup_pct: float = 1.0
    benchmark: BenchmarkPolicy = field(default_factory=BenchmarkPolicy)
    assume_no_alias: bool = False

    def argv(self) -> list[str]:
        args = [
            "region", "optimize", "--source", str(self.source), "--function", self.function,
            "--out-dir", str(self.output_directory), "--min-speedup-pct", str(self.minimum_speedup_pct),
            "--n", str(self.benchmark.element_count), "--reps", str(self.benchmark.repetitions),
            "--inner", str(self.benchmark.inner_calls), "--cpu", str(self.benchmark.cpu),
        ]
        if self.assume_no_alias:
            args.append("--assume-no-alias")
        if self.benchmark.flush_cache:
            args.append("--flush-cache")
        if self.benchmark.collect_perf:
            args.append("--perf")
        return args


@dataclass(frozen=True)
class LifetimeRequest:
    manifest: Path
    trace: Path
    output_directory: Path
    action: str = "synthesize"

    def argv(self) -> list[str]:
        if self.action not in {"analyze", "synthesize", "evaluate-corpus"}:
            raise ValueError(f"unsupported lifetime action: {self.action}")
        return [
            "lifetime", self.action,
            "--manifest", str(self.manifest),
            "--trace", str(self.trace),
            "--out-dir", str(self.output_directory),
        ]


class VelocityLadder:
    """Stable embedding facade for vLadder's optimization workflow."""

    def __init__(self, registry: GrammarRegistry | None = None) -> None:
        self.registry = registry or load_registry()
        self.lowering = LoweringEngine(self.registry)

    def lower(self, request: LoweringRequest) -> LoweringResult:
        return self.lowering.lower(request)

    def optimize(self, request: OptimizationRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "perf.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def optimize_region(self, request: AutomaticRegionRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "perf.json"
        if not report_path.exists():
            report_path = request.output_directory / "automatic-support.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def lifetime(self, request: LifetimeRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_name = {
            "analyze": "lifetime-analysis.json",
            "synthesize": "lifetime-report.json",
            "evaluate-corpus": "lifetime-evaluation.json",
        }[request.action]
        report_path = request.output_directory / report_name
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)
