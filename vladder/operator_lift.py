from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .extractor import extract_function
from .operator_contract import OperatorContract
from .operator_grammar import OperatorPlan


@dataclass(frozen=True)
class LiftedOperatorCandidate:
    name: str
    source: str
    plan: OperatorPlan
    cflags: tuple[str, ...]
    preconditions: tuple[str, ...]
    proof_obligations: tuple[str, ...]


def lift_operator_candidates(contract: OperatorContract, source_text: str, plans: list[OperatorPlan]) -> list[LiftedOperatorCandidate]:
    if contract.name == "rope_qk":
        baseline_plan = next(plan for plan in plans if plan.id == "baseline")
        baseline = extract_function(source_text, contract.entrypoint).source
        candidates = [LiftedOperatorCandidate("baseline", baseline, baseline_plan, (), (), ("identity",))]
        layout_plan = next((plan for plan in plans if "layout_split" in plan.effects), None)
        if layout_plan:
            candidates.append(LiftedOperatorCandidate(
                "split_plane_adapter_128", _lift_rope_split_adapter(), layout_plan, (),
                ("pairs <= 128 guarded with general fallback",),
                ("layout_adapter_bijection", "multi_output_equivalence", "bounds_and_alias"),
            ))
        return candidates
    if contract.name != "residual_rmsnorm_quant":
        baseline = extract_function(source_text, contract.entrypoint).source
        plan = next(plan for plan in plans if plan.id == "baseline")
        return [LiftedOperatorCandidate("baseline", baseline, plan, (), (), ("identity",))]
    candidates: list[LiftedOperatorCandidate] = []
    seen_sources: set[str] = set()
    baseline_plan = next(plan for plan in plans if plan.id == "baseline")
    baseline_source = extract_function(source_text, contract.entrypoint).source
    candidates.append(LiftedOperatorCandidate("baseline", baseline_source, baseline_plan, (), (), ("identity",)))
    seen_sources.add(hashlib.sha256(baseline_source.encode()).hexdigest())
    for plan in plans:
        if plan.id == "baseline":
            continue
        reduction = "linear"
        if "reduction_multi4" in plan.effects:
            reduction = "multi4"
        elif "reduction_pairwise" in plan.effects:
            reduction = "pairwise"
        fused = "eliminate_private_materialization" in plan.effects
        epilogue = "fuse_map_pack_emit" in plan.effects
        if not (fused or epilogue or reduction != "linear"):
            continue
        source = _lift_residual_rmsnorm_quant(fused, reduction)
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in seen_sources:
            continue
        seen_sources.add(digest)
        obligations = ["multi_output_equivalence", "quantization_equivalence", "bounds_and_alias"]
        if fused:
            obligations.append("private_scratch_no_external_observer")
        if reduction != "linear":
            obligations.append("deterministic_fp_tolerance")
        preconditions = ["n > 0", "declared input/output alias sets are disjoint"]
        if reduction == "pairwise":
            preconditions.append("n == 256 guarded with a general fallback")
        candidates.append(LiftedOperatorCandidate(
            f"synth_{'fused' if fused else 'staged'}_{reduction}", source, plan, (), tuple(preconditions), tuple(obligations)
        ))
    return candidates


def _lift_rope_split_adapter() -> str:
    return """void rope_qk(const float *q, const float *k, const float *cos_values, const float *sin_values,
             float *q_out, float *k_out, size_t pairs) {
    if (pairs <= 128) {
        float q_real[128], q_imag[128], k_real[128], k_imag[128];
        for (size_t p = 0; p < pairs; ++p) {
            q_real[p] = q[2*p]; q_imag[p] = q[2*p + 1];
            k_real[p] = k[2*p]; k_imag[p] = k[2*p + 1];
        }
        for (size_t p = 0; p < pairs; ++p) {
            float c = cos_values[p], s = sin_values[p];
            q_out[2*p] = q_real[p]*c - q_imag[p]*s;
            q_out[2*p + 1] = q_real[p]*s + q_imag[p]*c;
            k_out[2*p] = k_real[p]*c - k_imag[p]*s;
            k_out[2*p + 1] = k_real[p]*s + k_imag[p]*c;
        }
        return;
    }
    for (size_t p = 0; p < pairs; ++p) {
        size_t i = 2*p; float c = cos_values[p], s = sin_values[p];
        q_out[i] = q[i]*c - q[i+1]*s; q_out[i+1] = q[i]*s + q[i+1]*c;
        k_out[i] = k[i]*c - k[i+1]*s; k_out[i+1] = k[i]*s + k[i+1]*c;
    }
}"""


def _lift_residual_rmsnorm_quant(fused: bool, reduction: str) -> str:
    signature = """void residual_rmsnorm_quant(
    const float * restrict x,
    const float * restrict residual,
    const float * restrict weight,
    float * restrict scratch,
    float * restrict y,
    int8_t * restrict q,
    float * restrict scale_out,
    size_t n,
    float epsilon) {"""
    lines = [signature]
    if fused:
        lines.append("    (void)scratch;")
    if not fused:
        lines.extend([
            "    for (size_t i = 0; i < n; ++i) scratch[i] = x[i] + residual[i];",
        ])
    if reduction == "pairwise":
        lines.extend([
            "    if (n == 256) {",
            "        float squares[256];",
            "        for (size_t i = 0; i < 256; ++i) {",
            "            float value = x[i] + residual[i];",
            "            squares[i] = value * value;",
            "        }",
            "        for (size_t width = 128; width > 0; width >>= 1)",
            "            for (size_t i = 0; i < width; ++i) squares[i] = squares[2 * i] + squares[2 * i + 1];",
            "        float scale = 1.0f / sqrtf(squares[0] / 256.0f + epsilon);",
            "        *scale_out = scale;",
            "        for (size_t i = 0; i < 256; ++i) {",
            "            float value = (x[i] + residual[i]) * scale * weight[i];",
            "            y[i] = value;",
            "            int quantized = (int)(value * 127.0f);",
            "            if (quantized > 127) quantized = 127;",
            "            if (quantized < -127) quantized = -127;",
            "            q[i] = (int8_t)quantized;",
            "        }",
            "        return;",
            "    }",
        ])
        reduction = "linear"
        fused = True
    if reduction == "multi4":
        lines.extend([
            "    float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;",
            "    size_t r = 0;",
            "    for (; r + 3 < n; r += 4) {",
        ])
        for lane in range(4):
            value = f"(x[r + {lane}] + residual[r + {lane}])" if fused else f"scratch[r + {lane}]"
            lines.append(f"        float v{lane} = {value}; s{lane} += v{lane} * v{lane};")
        lines.extend([
            "    }",
            "    float sum_sq = (s0 + s1) + (s2 + s3);",
            "    for (; r < n; ++r) {",
            f"        float value = {'x[r] + residual[r]' if fused else 'scratch[r]'};",
            "        sum_sq += value * value;",
            "    }",
        ])
    else:
        lines.extend([
            "    float sum_sq = 0.0f;",
            "    for (size_t i = 0; i < n; ++i) {",
            f"        float value = {'x[i] + residual[i]' if fused else 'scratch[i]'};",
            "        sum_sq += value * value;",
            "    }",
        ])
    lines.extend([
        "    float scale = 1.0f / sqrtf(sum_sq / (float)n + epsilon);",
        "    *scale_out = scale;",
        "    for (size_t i = 0; i < n; ++i) {",
        f"        float combined = {'x[i] + residual[i]' if fused else 'scratch[i]'};",
        "        float value = combined * scale * weight[i];",
        "        y[i] = value;",
        "        int quantized = (int)(value * 127.0f);",
        "        if (quantized > 127) quantized = 127;",
        "        if (quantized < -127) quantized = -127;",
        "        q[i] = (int8_t)quantized;",
        "    }",
        "}",
    ])
    return "\n".join(lines)
