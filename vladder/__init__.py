"""vLadder: verified information-flow superoptimization for systems languages."""

__version__ = "1.0.0rc21"

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
from .region_closure import build_region_closure_graph, describe_c_boundary, prove_region_closure
from .gpu_ir import GPUArchitecture, GPUExecutionPlan, GPUKernelCapture, capture_gpu_kernel
from .heterogeneous_plan import (
    HeterogeneousPlanGraph,
    PlanCandidate,
    audit_heterogeneous_project,
    rank_heterogeneous_plans,
    synthesize_heterogeneous_plans,
)
from .cuda_runtime import probe_cuda_architecture, run_cuda_artifact
from .cuda_synthesis import optimize_cuda_pointwise, synthesize_cuda_pointwise
from .device_protocol import DeviceProtocolEvidence, verify_device_protocol
from .device_topology import probe_device_topology, probe_drm_presentation, probe_vulkan_capabilities
from .semantic_closure import CallRelation, EffectFootprint, FunctionSummary, compose_system_graph, prove_system_graph
from .protocol_envelopes import ProtocolEnvelope, protocol_registry, validate_protocol_application
from .resource_protocol import protocol_template, verify_resource_protocol
from .spirv_semantics import analyze_spirv_semantics, parse_spirv_instructions
from .structured_dataflow import classify_structured_dataflow
from .system_closure import run_system_closure
from .whole_build import (
    BidirectionalProgramSlice,
    CrossTUSummaryDatabase,
    OwnershipClosureGraph,
    SummaryCompositionProof,
    WholeBuildIndex,
    run_cross_tu_closure,
)

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
    "GPUArchitecture",
    "GPUExecutionPlan",
    "GPUKernelCapture",
    "HeterogeneousPlanGraph",
    "PlanCandidate",
    "DeviceProtocolEvidence",
    "EffectFootprint",
    "CallRelation",
    "FunctionSummary",
    "WholeBuildIndex",
    "CrossTUSummaryDatabase",
    "BidirectionalProgramSlice",
    "OwnershipClosureGraph",
    "SummaryCompositionProof",
    "ProtocolEnvelope",
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
    "build_region_closure_graph",
    "describe_c_boundary",
    "prove_region_closure",
    "capture_gpu_kernel",
    "audit_heterogeneous_project",
    "synthesize_heterogeneous_plans",
    "rank_heterogeneous_plans",
    "probe_cuda_architecture",
    "run_cuda_artifact",
    "synthesize_cuda_pointwise",
    "optimize_cuda_pointwise",
    "verify_device_protocol",
    "probe_device_topology",
    "probe_drm_presentation",
    "probe_vulkan_capabilities",
    "compose_system_graph",
    "prove_system_graph",
    "protocol_registry",
    "validate_protocol_application",
    "run_system_closure",
    "run_cross_tu_closure",
    "protocol_template",
    "verify_resource_protocol",
    "analyze_spirv_semantics",
    "parse_spirv_instructions",
    "classify_structured_dataflow",
]
