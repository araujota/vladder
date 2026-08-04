"""vLadder: verified information-flow superoptimization for C and C++."""

__version__ = "1.0.0rc5"

from .api import AutomaticRegionRequest, BenchmarkPolicy, CppAuditRequest, CppRegionRequest, LifetimeRequest, OptimizationRequest, OptimizationResult, VelocityLadder
from .automatic import AdapterRequirement, AutomaticSupport
from .cpp_closure import classify_cpp_closure
from .cpp_regions import CPP_SUPPORT_VERSION, CppAdapterRequirement, inspect_cpp_matrix, inspect_cpp_region, isolate_cpp_region
from .capabilities import GrammarRegistry, load_registry
from .lowering import LoweringEngine, LoweringMode, LoweringPlan, LoweringRequest, LoweringResult, LoweringStatus
from .lifetime_graph import LifetimeFlowGraph, LifetimeInformation, load_lifetime_flow_graph
from .verification_policy import VerificationPolicy

__all__ = [
    "BenchmarkPolicy",
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
    "VelocityLadder",
    "VerificationPolicy",
    "__version__",
    "load_registry",
    "load_lifetime_flow_graph",
    "inspect_cpp_region",
    "inspect_cpp_matrix",
    "isolate_cpp_region",
    "classify_cpp_closure",
]
