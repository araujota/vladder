"""vLadder: verified information-flow superoptimization for systems languages."""

__version__ = "1.0.0rc11"

from .api import (
    AgentWorkflowRequest,
    AutomaticRegionRequest,
    BenchmarkPolicy,
    CppAuditRequest,
    CppRegionRequest,
    DeepGrammarAuditRequest,
    DeepGrammarRankRequest,
    DeepKernelRequest,
    LifetimeRequest,
    OptimizationRequest,
    OptimizationResult,
    PairedBenchmarkRequest,
    StateProtocolRequest,
    RustRegionRequest,
    ZigRegionRequest,
    JuliaRegionRequest,
    VelocityLadder,
)
from .agent_workflow import build_promotion_summary, run_agent_workflow
from .automatic import AdapterRequirement, AutomaticSupport
from .cpp_closure import classify_cpp_closure
from .cpp_regions import CPP_SUPPORT_VERSION, CppAdapterRequirement, inspect_cpp_matrix, inspect_cpp_region, isolate_cpp_region
from .capabilities import GrammarRegistry, load_registry
from .lowering import LoweringEngine, LoweringMode, LoweringPlan, LoweringRequest, LoweringResult, LoweringStatus
from .lifetime_graph import LifetimeFlowGraph, LifetimeInformation, load_lifetime_flow_graph
from .verification_policy import VerificationPolicy
from .language_adapter import LanguageAdapterRegistry, SemanticFlowGraph
from .rust_semantics import RUST_SUPPORT_VERSION
from .zig_adapter import ZIG_SUPPORT_VERSION
from .julia_adapter import JULIA_SUPPORT_VERSION
from .deep_grammar import DeepGrammar, load_deep_grammar, search_deep_grammar
from .deep_ir import DeepKernelContract, DeepRealizationGraph
from .dataflow_grammar import BoundedDataflowGrammar, load_bounded_dataflow_grammar
from .dataflow_ir import BoundedDataflowContract, BoundedDataflowGraph, build_bounded_dataflow_graph

__all__ = [
    "BenchmarkPolicy",
    "AgentWorkflowRequest",
    "CPP_SUPPORT_VERSION",
    "CppAdapterRequirement",
    "CppAuditRequest",
    "CppRegionRequest",
    "DeepGrammar",
    "DeepGrammarAuditRequest",
    "DeepGrammarRankRequest",
    "DeepKernelContract",
    "DeepKernelRequest",
    "DeepRealizationGraph",
    "BoundedDataflowContract",
    "BoundedDataflowGrammar",
    "BoundedDataflowGraph",
    "AutomaticRegionRequest",
    "AutomaticSupport",
    "AdapterRequirement",
    "GrammarRegistry",
    "LoweringEngine",
    "LoweringMode",
    "LoweringPlan",
    "LoweringRequest",
    "LoweringResult",
    "LoweringStatus",
    "LifetimeFlowGraph",
    "LifetimeInformation",
    "LifetimeRequest",
    "OptimizationRequest",
    "OptimizationResult",
    "PairedBenchmarkRequest",
    "StateProtocolRequest",
    "RustRegionRequest",
    "RUST_SUPPORT_VERSION",
    "ZigRegionRequest",
    "ZIG_SUPPORT_VERSION",
    "JuliaRegionRequest",
    "JULIA_SUPPORT_VERSION",
    "LanguageAdapterRegistry",
    "SemanticFlowGraph",
    "VelocityLadder",
    "VerificationPolicy",
    "__version__",
    "load_registry",
    "load_deep_grammar",
    "load_bounded_dataflow_grammar",
    "load_lifetime_flow_graph",
    "inspect_cpp_region",
    "inspect_cpp_matrix",
    "isolate_cpp_region",
    "classify_cpp_closure",
    "build_promotion_summary",
    "run_agent_workflow",
    "search_deep_grammar",
    "build_bounded_dataflow_graph",
]
