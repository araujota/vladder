"""vLadder: verified information-flow superoptimization for C and C++."""

__version__ = "1.0.0rc6"

from .api import (
    AgentWorkflowRequest,
    AutomaticRegionRequest,
    BenchmarkPolicy,
    CppAuditRequest,
    CppRegionRequest,
    LifetimeRequest,
    OptimizationRequest,
    OptimizationResult,
    PairedBenchmarkRequest,
    StateProtocolRequest,
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

__all__ = [
    "BenchmarkPolicy",
    "AgentWorkflowRequest",
    "CPP_SUPPORT_VERSION",
    "CppAdapterRequirement",
    "CppAuditRequest",
    "CppRegionRequest",
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
    "VelocityLadder",
    "VerificationPolicy",
    "__version__",
    "load_registry",
    "load_lifetime_flow_graph",
    "inspect_cpp_region",
    "inspect_cpp_matrix",
    "isolate_cpp_region",
    "classify_cpp_closure",
    "build_promotion_summary",
    "run_agent_workflow",
]
