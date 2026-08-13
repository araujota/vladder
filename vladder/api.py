from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .capabilities import GrammarRegistry, load_registry
from .lowering import LoweringEngine, LoweringRequest, LoweringResult
from .verification_policy import VerificationPolicy
from .rust_adapter import RustRegionRequest
from .zig_adapter import ZigRegionRequest
from .julia_adapter import JuliaRegionRequest


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
class CppRegionRequest:
    source: Path
    function: str
    compilation_database: Path
    output_directory: Path
    action: str = "isolate"
    symbol: str | None = None
    source_line: int | None = None
    command_index: int | None = None
    minimum_speedup_pct: float = 1.0
    benchmark: BenchmarkPolicy = field(default_factory=BenchmarkPolicy)

    def argv(self) -> list[str]:
        if self.action not in {"inspect", "isolate", "synthesize", "optimize"}:
            raise ValueError(f"unsupported C++ region action: {self.action}")
        args = [
            "cpp", self.action, "--source", str(self.source), "--function", self.function,
            "--compile-commands", str(self.compilation_database), "--out-dir", str(self.output_directory),
        ]
        if self.symbol:
            args.extend(("--symbol", self.symbol))
        if self.source_line is not None:
            args.extend(("--source-line", str(self.source_line)))
        if self.command_index is not None:
            args.extend(("--command-index", str(self.command_index)))
        if self.action == "optimize":
            args.extend((
                "--n", str(self.benchmark.element_count), "--reps", str(self.benchmark.repetitions),
                "--inner", str(self.benchmark.inner_calls), "--cpu", str(self.benchmark.cpu),
                "--min-speedup-pct", str(self.minimum_speedup_pct),
            ))
        return args


@dataclass(frozen=True)
class CppAuditRequest:
    manifest: Path
    output_directory: Path
    materialize_isolation: bool = False

    def argv(self) -> list[str]:
        args = ["cpp", "audit", "--manifest", str(self.manifest), "--out-dir", str(self.output_directory)]
        if self.materialize_isolation:
            args.append("--materialize-isolation")
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


@dataclass(frozen=True)
class AgentWorkflowRequest:
    manifest: Path
    output_directory: Path
    force: bool = False

    def argv(self) -> list[str]:
        args = ["workflow", "run", "--manifest", str(self.manifest), "--out-dir", str(self.output_directory)]
        if self.force:
            args.append("--force")
        return args


@dataclass(frozen=True)
class PairedBenchmarkRequest:
    manifest: Path
    output_directory: Path

    def argv(self) -> list[str]:
        return ["benchmark", "paired", "--manifest", str(self.manifest), "--out-dir", str(self.output_directory)]


@dataclass(frozen=True)
class StateProtocolRequest:
    manifest: Path
    output_directory: Path

    def argv(self) -> list[str]:
        return ["protocol", "verify", "--manifest", str(self.manifest), "--out-dir", str(self.output_directory)]


@dataclass(frozen=True)
class DeepKernelRequest:
    output_directory: Path
    target: str
    language: str = "c"
    predicate: str = "equal-u8"
    function: str = "deep_candidate"
    action: str = "benchmark"
    processes: int = 10
    repetitions: int = 3
    element_count: int = 1 << 20
    inner_calls: int = 128
    cpu: int | None = None
    minimum_speedup_pct: float = 1.0

    def argv(self) -> list[str]:
        if self.action not in {"emit", "benchmark"}:
            raise ValueError(f"unsupported deep-kernel action: {self.action}")
        args = [
            "deep", self.action, "--target", self.target, "--language", self.language,
            "--predicate", self.predicate, "--function", self.function,
            "--out-dir", str(self.output_directory),
        ]
        if self.action == "benchmark":
            args.extend((
                "--processes", str(self.processes), "--repetitions", str(self.repetitions),
                "--n", str(self.element_count), "--inner", str(self.inner_calls),
                "--min-speedup-pct", str(self.minimum_speedup_pct),
            ))
            if self.cpu is not None:
                args.extend(("--cpu", str(self.cpu)))
        return args


@dataclass(frozen=True)
class DeepGrammarAuditRequest:
    manifest: Path
    output_directory: Path
    benchmark: bool = False

    def argv(self) -> list[str]:
        args = ["deep", "audit", "--manifest", str(self.manifest), "--out-dir", str(self.output_directory)]
        if self.benchmark:
            args.append("--benchmark")
        return args


@dataclass(frozen=True)
class DeepGrammarRankRequest:
    output_directory: Path
    language: str = "c"
    predicate: str = "equal-u8"
    processes: int = 10
    repetitions: int = 3
    element_count: int = 1 << 20
    inner_calls: int = 128
    cpu: int | None = None
    minimum_speedup_pct: float = 1.0

    def argv(self) -> list[str]:
        args = [
            "deep", "rank", "--language", self.language, "--predicate", self.predicate,
            "--processes", str(self.processes), "--repetitions", str(self.repetitions),
            "--n", str(self.element_count), "--inner", str(self.inner_calls),
            "--min-speedup-pct", str(self.minimum_speedup_pct), "--out-dir", str(self.output_directory),
        ]
        if self.cpu is not None:
            args.extend(("--cpu", str(self.cpu)))
        return args


class VelocityLadder:
    """Stable embedding facade for vLadder's optimization workflow."""

    def __init__(self, registry: GrammarRegistry | None = None) -> None:
        self.registry = registry or load_registry()
        self.lowering = LoweringEngine(self.registry)

    def lower(self, request: LoweringRequest) -> LoweringResult:
        return self.lowering.lower(request)

    def deep_kernel(self, request: DeepKernelRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "deep-workflow.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def deep_grammar_audit(self, request: DeepGrammarAuditRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "expert-grammar-audit.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def deep_grammar_rank(self, request: DeepGrammarRankRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "deep-ranking.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

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

    def cpp_region(self, request: CppRegionRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_name = "cpp-optimization.json" if request.action == "optimize" else "cpp-support.json"
        report_path = request.output_directory / report_name
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def cpp_audit(self, request: CppAuditRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "cpp-audit.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def rust_region(self, request: RustRegionRequest, action: str = "optimize") -> OptimizationResult:
        from .cli import main

        if action not in {"inspect", "isolate", "synthesize", "optimize"}:
            raise ValueError(f"unsupported Rust region action: {action}")
        request.output_directory.mkdir(parents=True, exist_ok=True)
        args = [
            "rust", action, "--manifest-path", str(request.manifest_path),
            "--source", str(request.source), "--function", request.function,
            "--target-kind", request.target_kind, "--profile", request.profile,
            "--proof-bound", str(request.proof_bound), "--out-dir", str(request.output_directory),
        ]
        if request.package:
            args.extend(("--package", request.package))
        if request.target_name:
            args.extend(("--target-name", request.target_name))
        for feature in request.features:
            args.extend(("--feature", feature))
        if action == "optimize":
            args.extend((
                "--min-speedup-pct", str(request.minimum_speedup_pct),
                "--n", str(request.benchmark_elements), "--inner", str(request.benchmark_inner),
                "--processes", str(request.benchmark_processes),
                "--repetitions", str(request.benchmark_repetitions),
            ))
            if request.cpu is not None:
                args.extend(("--cpu", str(request.cpu)))
        return_code = main(args)
        report_name = {
            "inspect": "rust-support.json", "isolate": "rust-isolation.json",
            "synthesize": "rust-synthesis.json", "optimize": "rust-optimization.json",
        }[action]
        report_path = request.output_directory / report_name
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def zig_region(self, request: ZigRegionRequest, action: str = "optimize") -> OptimizationResult:
        from .zig_adapter import inspect_zig_region, isolate_zig_region, optimize_zig_region, synthesize_zig_region
        actions = {"inspect": inspect_zig_region, "isolate": isolate_zig_region, "synthesize": synthesize_zig_region, "optimize": optimize_zig_region}
        if action not in actions: raise ValueError(f"unsupported Zig region action: {action}")
        request.output_directory.mkdir(parents=True, exist_ok=True)
        report = actions[action](request)
        report_path = request.output_directory / {"inspect": "zig-support.json", "isolate": "zig-isolation.json", "synthesize": "zig-synthesis.json", "optimize": "zig-optimization.json"}[action]
        return OptimizationResult(0 if report.get("status") in {"pass", "supported"} else 1, report_path, report)

    def julia_region(self, request: JuliaRegionRequest, action: str = "optimize") -> OptimizationResult:
        from .julia_adapter import inspect_julia_region, isolate_julia_region, optimize_julia_region, synthesize_julia_region
        actions = {"inspect": inspect_julia_region, "isolate": isolate_julia_region, "synthesize": synthesize_julia_region, "optimize": optimize_julia_region}
        if action not in actions: raise ValueError(f"unsupported Julia region action: {action}")
        request.output_directory.mkdir(parents=True, exist_ok=True)
        report = actions[action](request)
        report_path = request.output_directory / {"inspect": "julia-support.json", "isolate": "julia-isolation.json", "synthesize": "julia-synthesis.json", "optimize": "julia-optimization.json"}[action]
        return OptimizationResult(0 if report.get("status") in {"pass", "supported"} else 1, report_path, report)

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

    def workflow(self, request: AgentWorkflowRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "promotion-summary.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def paired_benchmark(self, request: PairedBenchmarkRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "paired-benchmark.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)

    def state_protocol(self, request: StateProtocolRequest) -> OptimizationResult:
        from .cli import main

        request.output_directory.mkdir(parents=True, exist_ok=True)
        return_code = main(request.argv())
        report_path = request.output_directory / "protocol-proof.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        return OptimizationResult(return_code, report_path, report)
