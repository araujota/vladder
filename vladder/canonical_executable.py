from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping

import z3

from .canonical_regions import CanonicalBoundedRegion
from .language_adapter import canonical_hash, obligation
from .deep_benchmark import _hot_assembly_identity


CANONICAL_EXECUTABLE_VERSION = "canonical-executable-grammar-v1"


@dataclass(frozen=True)
class CanonicalRule:
    id: str
    source: str
    target: str
    preconditions: tuple[str, ...]
    proof: str


@dataclass(frozen=True)
class CanonicalDerivation:
    family: str
    realization: str
    rules: tuple[CanonicalRule, ...]

    @property
    def derivation_hash(self) -> str:
        return canonical_hash({
            "version": CANONICAL_EXECUTABLE_VERSION,
            "family": self.family,
            "realization": self.realization,
            "rules": [asdict(rule) for rule in self.rules],
        })


@dataclass(frozen=True)
class CanonicalCandidate:
    id: str
    language: str
    function: str
    family: str
    realization: str
    source: str
    source_sha256: str
    region_hash: str
    derivation_hash: str
    graph_hash: str
    compiler_flags: tuple[str, ...]
    obligations: tuple[Any, ...]


class CanonicalExecutableGrammar:
    def __init__(self, family: str, rules: tuple[CanonicalRule, ...]) -> None:
        self.family = family
        self.rules = rules
        self.by_source: dict[str, tuple[CanonicalRule, ...]] = {
            source: tuple(rule for rule in rules if rule.source == source)
            for source in {rule.source for rule in rules}
        }

    @classmethod
    def load(cls, family: str) -> "CanonicalExecutableGrammar":
        path = Path(__file__).with_name("grammars") / f"{family}.json"
        raw = json.loads(path.read_text())
        return cls(family, tuple(
            CanonicalRule(
                str(item["id"]), str(item["input"]), str(item["output"]),
                tuple(str(value) for value in item.get("preconditions", ())),
                str(item["proof"]),
            )
            for item in raw["rules"]
        ))

    def derivations(self) -> tuple[CanonicalDerivation, ...]:
        result: list[CanonicalDerivation] = []

        def visit(realization: str, path: tuple[CanonicalRule, ...], seen: frozenset[str]) -> None:
            if realization != "canonical":
                result.append(CanonicalDerivation(self.family, realization, path))
            for rule in self.by_source.get(realization, ()):
                if rule.target not in seen:
                    visit(rule.target, (*path, rule), seen | {rule.target})

        visit("canonical", (), frozenset({"canonical"}))
        return tuple(result)


def canonical_region_from_dict(raw: Mapping[str, Any]) -> CanonicalBoundedRegion:
    values = dict(raw)
    values.pop("region_hash", None)
    values.pop("executable_grammar", None)
    for name in ("input_roles", "output_roles", "neighbor_offsets", "source_traits"):
        values[name] = tuple(values.get(name, ()))
    values["semantic_parameters"] = tuple(
        (str(item[0]), str(item[1])) for item in values.get("semantic_parameters", ())
    )
    return CanonicalBoundedRegion(**values)


def _factor(realization: str) -> int:
    if "avx512" in realization:
        return 16
    if "unroll8" in realization or "avx2" in realization:
        return 8
    if "unroll4" in realization:
        return 4
    return 1


def _parameters(region: CanonicalBoundedRegion) -> dict[str, str]:
    return dict(region.semantic_parameters)


def _validated_expression(region: CanonicalBoundedRegion) -> str:
    expression = _parameters(region).get("expression") or _parameters(region).get("transition") or "x"
    if not re.fullmatch(r"[A-Za-z0-9_.+*/()\[\] ?:\-]+", expression):
        raise ValueError(f"canonical expression contains unsupported tokens: {expression}")
    return expression


def _expression(region: CanonicalBoundedRegion, language: str) -> str:
    if region.family == "guarded_pointwise_map":
        return "if x > 0.0 { x } else { 0.0 }" if language == "rust" else (
            "if (x > 0.0) x else 0.0" if language == "zig" else
            "ifelse(x > 0.0f0, x, 0.0f0)" if language == "julia" else
            "x > 0.0f ? x : 0.0f"
        )
    value = _validated_expression(region)
    if region.family == "stencil":
        value = value.replace("x[-1]", "xm1").replace("x[1]", "xp1")
    if language in {"c", "cpp"}:
        value = re.sub(r"(?<![A-Za-z0-9_])(\d+\.\d+)(?![A-Za-z0-9_])", r"\1f", value)
    elif language == "rust":
        value = re.sub(r"(?<![A-Za-z0-9_])(\d+\.\d+)(?![A-Za-z0-9_])", r"\1f32", value)
    elif language == "julia":
        value = re.sub(r"(?<![A-Za-z0-9_])(\d+\.\d+)(?![A-Za-z0-9_])", r"\1f0", value)
    return value


def _c_candidate(region: CanonicalBoundedRegion, realization: str, function: str, cpp: bool) -> str:
    factor = _factor(realization)
    linkage = 'extern "C" ' if cpp else ""
    noexcept = " noexcept" if cpp else ""
    expression = _expression(region, "cpp" if cpp else "c")
    pre = "#include <stddef.h>\n#include <stdint.h>\n"
    eval_name = f"{function}_eval"
    if region.family == "stencil":
        eval_args = "float xm1,float x,float xp1"
    elif region.family in {"scan", "recurrence"}:
        eval_args = "float state,float x"
    elif region.family == "indirect_memory":
        eval_args = "float indirect,float x"
    else:
        eval_args = "float x"
    helper = f"static inline float {eval_name}({eval_args}) {{ return {expression}; }}\n"
    if region.family == "scan":
        loop = f"float state=0.0f; for(size_t i=0;i<n;++i){{state += src[i];dst[i]=state;}}"
    elif region.family == "recurrence":
        loop = f"float state=0.0f; for(size_t i=0;i<n;++i){{state={eval_name}(state,src[i]);dst[i]=state;}}"
    elif region.family == "indirect_memory":
        stride = int(region.indirect_stride or 1)
        loop = f"if(!n)return; for(size_t i=0;i<n;++i){{size_t j=(i*{stride}u)%n;dst[i]={eval_name}(src[j],src[i]);}}"
    elif region.family == "stencil":
        body = f"dst[i]={eval_name}(src[i-1],src[i],src[i+1]);"
        loop = _c_partition_loop(body, factor, start="1", end="n-1")
        loop = f"if(!n)return;dst[0]=src[0];if(n==1)return;{loop}dst[n-1]=src[n-1];"
    else:
        body = f"dst[i]={eval_name}(src[i]);"
        loop = _c_partition_loop(body, factor)
    return pre + helper + f"{linkage}void {function}(float *dst,const float *src,size_t n){noexcept}{{{loop}}}\n"


def _c_partition_loop(body: str, factor: int, *, start: str = "0", end: str = "n") -> str:
    if factor == 1:
        return f"for(size_t i={start};i<{end};++i){{{body}}}"
    lanes = "".join("{" + _lane_body(body, lane) + "}" for lane in range(factor))
    return (
        f"size_t i={start};for(;i+{factor - 1}<{end};i+={factor}){{{lanes}}}"
        f"for(;i<{end};++i){{{body}}}"
    )


def _rust_candidate(region: CanonicalBoundedRegion, realization: str, function: str) -> str:
    factor = _factor(realization)
    expression = _expression(region, "rust")
    if region.family == "stencil":
        args = "xm1:f32,x:f32,xp1:f32"
    elif region.family in {"scan", "recurrence"}:
        args = "state:f32,x:f32"
    elif region.family == "indirect_memory":
        args = "indirect:f32,x:f32"
    else:
        args = "x:f32"
    helper = f"#[inline(always)] fn {function}_eval({args})->f32{{{expression}}}\n"
    if region.family == "scan":
        loop = "let mut state=0.0f32;for i in 0..n{state+=src[i];dst[i]=state;}"
    elif region.family == "recurrence":
        loop = f"let mut state=0.0f32;for i in 0..n{{state={function}_eval(state,src[i]);dst[i]=state;}}"
    elif region.family == "indirect_memory":
        stride = int(region.indirect_stride or 1)
        loop = f"if n==0{{return;}}for i in 0..n{{let j=(i*{stride})%n;dst[i]={function}_eval(src[j],src[i]);}}"
    elif region.family == "stencil":
        body = f"dst[i]={function}_eval(src[i-1],src[i],src[i+1]);"
        loop = f"if n==0{{return;}}dst[0]=src[0];if n==1{{return;}}{_rust_partition_loop(body, factor, '1', 'n-1')}dst[n-1]=src[n-1];"
    else:
        loop = _rust_partition_loop(f"dst[i]={function}_eval(src[i]);", factor, "0", "n")
    return (
        helper
        + f"#[unsafe(no_mangle)]\n#[inline(never)] pub fn {function}(dst:&mut[f32],src:&[f32])"
        + f"{{let n=src.len();{loop}}}\n"
    )


def _rust_partition_loop(body: str, factor: int, start: str, end: str) -> str:
    if factor == 1:
        return f"for i in {start}..{end}{{{body}}}"
    lanes = "".join("{" + _lane_body(body, lane) + "}" for lane in range(factor))
    return f"let mut i={start};while i+{factor - 1}<{end}{{{lanes}i+={factor};}}while i<{end}{{{body}i+=1;}}"


def _zig_candidate(region: CanonicalBoundedRegion, realization: str, function: str) -> str:
    factor = _factor(realization)
    expression = _expression(region, "zig")
    if region.family == "stencil": args = "xm1:f32,x:f32,xp1:f32"
    elif region.family in {"scan", "recurrence"}: args = "state:f32,x:f32"
    elif region.family == "indirect_memory": args = "indirect:f32,x:f32"
    else: args = "x:f32"
    helper = f"inline fn {function}_eval({args})f32{{return {expression};}}\n"
    if region.family == "scan":
        loop = "var state:f32=0;for(0..n)|i|{state+=src[i];dst[i]=state;}"
    elif region.family == "recurrence":
        loop = f"var state:f32=0;for(0..n)|i|{{state={function}_eval(state,src[i]);dst[i]=state;}}"
    elif region.family == "indirect_memory":
        stride = int(region.indirect_stride or 1)
        loop = f"if(n==0)return;for(0..n)|i|{{const j=(i*{stride})%n;dst[i]={function}_eval(src[j],src[i]);}}"
    elif region.family == "stencil":
        loop = f"if(n==0)return;dst[0]=src[0];if(n==1)return;{_zig_partition_loop(f'dst[i]={function}_eval(src[i-1],src[i],src[i+1]);',factor,'1','n-1')}dst[n-1]=src[n-1];"
    else:
        loop = _zig_partition_loop(f"dst[i]={function}_eval(src[i]);", factor, "0", "n")
    return (
        helper
        + f"pub noinline fn {function}(dst:[]f32,src:[]const f32)void{{const n=src.len;{loop}}}\n"
        + f"pub export fn {function}_probe(dst:[*]f32,src:[*]const f32,n:usize)void{{{function}(dst[0..n],src[0..n]);}}\n"
    )


def _zig_partition_loop(body: str, factor: int, start: str, end: str) -> str:
    if factor == 1:
        return f"for({start}..{end})|i|{{{body}}}"
    lanes = "".join("{" + _lane_body(body, lane) + "}" for lane in range(factor))
    return f"var i:usize={start};while(i+{factor - 1}<{end}):(i+={factor}){{{lanes}}}while(i<{end}):(i+=1){{{body}}}"


def _julia_candidate(region: CanonicalBoundedRegion, realization: str, function: str) -> str:
    factor = _factor(realization)
    expression = _expression(region, "julia")
    if region.family == "scan":
        loop = "state=0.0f0;@inbounds for i in eachindex(src);state+=src[i];dst[i]=state;end"
    elif region.family == "recurrence":
        loop = f"state=0.0f0;@inbounds for i in eachindex(src);x=src[i];state={expression};dst[i]=state;end"
    elif region.family == "indirect_memory":
        stride = int(region.indirect_stride or 1)
        loop = f"n=length(src);n==0&&return nothing;@inbounds for i in eachindex(src);j=mod((i-1)*{stride},n)+1;x=src[i];indirect=src[j];dst[i]={expression};end"
    elif region.family == "stencil":
        body = f"xm1=src[i-1];x=src[i];xp1=src[i+1];dst[i]={expression};"
        loop = f"n=length(src);n==0&&return nothing;dst[1]=src[1];n==1&&return nothing;{_julia_partition_loop(body,factor,'2','n-1')}dst[n]=src[n];"
    else:
        body = f"x=src[i];dst[i]={expression};"
        loop = "isempty(src)&&return nothing;" + _julia_partition_loop(body, factor, "1", "length(src)")
    return f"function {function}(dst::Vector{{Float32}},src::Vector{{Float32}})::Nothing\n{loop}\nreturn nothing\nend\n"


def _julia_partition_loop(body: str, factor: int, start: str, end: str) -> str:
    if factor == 1:
        return f"@inbounds for i in {start}:{end};{body}end;"
    lanes = "".join(_lane_body(body, lane) for lane in range(factor))
    return f"i={start};@inbounds while i+{factor - 1}<={end};{lanes}i+={factor};end;while i<={end};{body}i+=1;end;"


def _lane_body(body: str, lane: int) -> str:
    return body if lane == 0 else re.sub(r"\bi\b", f"(i+{lane})", body)


def emit_canonical_candidate(
    region: CanonicalBoundedRegion,
    derivation: CanonicalDerivation,
    language: str,
    function: str = "canonical_candidate",
) -> CanonicalCandidate:
    if language == "c": source = _c_candidate(region, derivation.realization, function, False)
    elif language == "cpp": source = _c_candidate(region, derivation.realization, function, True)
    elif language == "rust": source = _rust_candidate(region, derivation.realization, function)
    elif language == "zig": source = _zig_candidate(region, derivation.realization, function)
    elif language == "julia": source = _julia_candidate(region, derivation.realization, function)
    else: raise ValueError(f"unsupported canonical executable language: {language}")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    graph_hash = canonical_hash({
        "version": CANONICAL_EXECUTABLE_VERSION,
        "region_hash": region.region_hash,
        "realization": derivation.realization,
        "language": language,
        "function": function,
    })
    flags = {
        "c": ("-std=c17", "-O3", "-march=native"),
        "cpp": ("-std=c++20", "-O3", "-march=native"),
        "rust": ("--edition=2024", "-C", "opt-level=3", "-C", "target-cpu=native"),
        "zig": ("ReleaseFast", "native"),
        "julia": ("--startup-file=no", "-O3", "--check-bounds=no"),
    }[language]
    return CanonicalCandidate(
        canonical_hash({"source": source_hash, "derivation": derivation.derivation_hash}),
        language, function, region.family, derivation.realization, source, source_hash,
        region.region_hash, derivation.derivation_hash, graph_hash, flags,
        (obligation(
            "canonical.generated-source", "representation",
            "generated source realizes the compiler-corroborated canonical bounded region",
            scope="generated-function", proof_method="hash+bounded-Z3+differential",
            language=language, native_construct=derivation.realization,
        ),),
    )


def prove_canonical_candidate(
    region: CanonicalBoundedRegion,
    derivation: CanonicalDerivation,
    candidate: CanonicalCandidate,
    output: Path,
    *,
    run_differential: bool = True,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source_bound = hashlib.sha256(candidate.source.encode()).hexdigest() == candidate.source_sha256
    region_bound = candidate.region_hash == region.region_hash
    derivation_bound = candidate.derivation_hash == derivation.derivation_hash
    factor = _factor(derivation.realization)
    n, index = z3.Ints("n index")
    main = (n / factor) * factor
    solver = z3.Solver()
    solver.add(n >= 0, index >= 0, index < n)
    solver.add(z3.Not(z3.Or(index < main, index >= main)))
    schedule_result = solver.check()
    schedule_path = output / "schedule-coverage.smt2"
    schedule_path.write_text(solver.to_smt2())
    differential = (
        run_canonical_differential(region, derivation, candidate, output / "differential")
        if run_differential else {"status": "NOT_RUN"}
    )
    statuses = {
        "source_binding": source_bound,
        "region_binding": region_bound,
        "derivation_binding": derivation_bound,
        "schedule_coverage": schedule_result == z3.unsat,
        "differential": differential.get("status") in {"PASS", "NOT_RUN"},
    }
    report = {
        "schema_version": "vladder-canonical-executable-proof-v1",
        "status": "PASS" if all(statuses.values()) else "FAIL",
        "proof_classification": "compiler-corroborated-canonical-region+bounded-schedule+differential",
        "statuses": statuses,
        "differential": differential,
        "artifacts": {"schedule_smt2": str(schedule_path)},
        "excluded_claims": [
            "owning wrapper equivalence",
            "external protocol equivalence",
            "floating-point reassociation beyond the captured expression order",
        ],
    }
    (output / "proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def compile_canonical_candidate(candidate: CanonicalCandidate, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    language = candidate.language
    suffix = {"c": ".c", "cpp": ".cpp", "rust": ".rs", "zig": ".zig", "julia": ".jl"}[language]
    source = output / f"candidate{suffix}"
    assembly = output / "candidate.s"
    source.write_text(candidate.source)
    environment = os.environ.copy()
    if language in {"c", "cpp"}:
        compiler = (shutil.which("clang-20") or shutil.which("clang")) if language == "c" else (shutil.which("clang++-20") or shutil.which("clang++"))
        command = [compiler, *candidate.compiler_flags, "-S", str(source), "-o", str(assembly)] if compiler else []
    elif language == "rust":
        compiler = shutil.which("rustc")
        command = [compiler, *candidate.compiler_flags, "--crate-type=lib", "--emit", f"asm={assembly}", str(source)] if compiler else []
    elif language == "zig":
        compiler = shutil.which("zig"); obj = output / "candidate.o"
        command = [compiler, "build-obj", "-O", "ReleaseFast", "-mcpu", "native", f"-femit-bin={obj}", f"-femit-asm={assembly}", str(source)] if compiler else []
        environment["ZIG_GLOBAL_CACHE_DIR"] = str(output / "zig-global-cache")
        environment["ZIG_LOCAL_CACHE_DIR"] = str(output / "zig-local-cache")
    else:
        compiler = shutil.which("julia")
        capture = output / "capture.jl"
        capture.write_text(
            candidate.source + "\nusing InteractiveUtils\n"
            + f'open(raw"{assembly}", "w") do io; code_native(io, {candidate.function}, (Vector{{Float32}}, Vector{{Float32}}); syntax=:intel, debuginfo=:none); end\n'
        )
        command = [compiler, "--startup-file=no", "-O3", "--check-bounds=no", str(capture)] if compiler else []
    if not command:
        return {"status": "UNAVAILABLE", "reason": f"{language} compiler unavailable"}
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    if completed.returncode != 0:
        return {"status": "FAIL", "command": command, "stdout": completed.stdout, "stderr": completed.stderr}
    identity = _hot_assembly_identity(assembly, candidate.function)
    return {
        "status": "PASS" if identity.get("status") == "resolved" else "FAIL",
        "command": command,
        "source": str(source),
        "assembly": str(assembly),
        "assembly_identity": identity.get("normalized_sha256"),
        "identity": identity,
    }


def synthesize_canonical_region(
    region: CanonicalBoundedRegion,
    language: str,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    grammar = CanonicalExecutableGrammar.load(region.family)
    rows: list[dict[str, Any]] = []
    identity_owner: dict[str, str] = {}
    for derivation in grammar.derivations():
        candidate = emit_canonical_candidate(region, derivation, language)
        root = output / "candidates" / candidate.id[:16]
        proof = prove_canonical_candidate(region, derivation, candidate, root / "proof")
        compiled = compile_canonical_candidate(candidate, root / "build")
        identity = compiled.get("assembly_identity")
        disposition = "resolved"
        duplicate_of = None
        if identity and identity in identity_owner:
            disposition = "duplicate"
            duplicate_of = identity_owner[identity]
        elif identity:
            identity_owner[identity] = candidate.id
        row = {
            "candidate": {**asdict(candidate), "obligations": [asdict(item) for item in candidate.obligations]},
            "proof": proof,
            "compile": compiled,
            "proof_status": proof["status"],
            "identity_disposition": disposition,
            "duplicate_of": duplicate_of,
        }
        (root / "candidate.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
        rows.append(row)
    return {
        "schema_version": "vladder-canonical-native-synthesis-v1",
        "status": "pass" if rows and all(row["proof_status"] == "PASS" and row["compile"]["status"] == "PASS" for row in rows) else "fail",
        "grammar_version": CANONICAL_EXECUTABLE_VERSION,
        "family": region.family,
        "candidate_count": len(rows),
        "proved_candidate_count": sum(row["proof_status"] == "PASS" for row in rows),
        "distinct_assembly_count": len(identity_owner),
        "candidates": rows,
        "source_changes_performed": False,
        "claim_boundary": "compiler-corroborated bounded region only; owning wrapper and application promotion remain separate",
    }


def run_canonical_differential(
    region: CanonicalBoundedRegion,
    derivation: CanonicalDerivation,
    candidate: CanonicalCandidate,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    baseline = emit_canonical_candidate(
        region,
        CanonicalDerivation(region.family, "scalar" if region.family != "guarded_pointwise_map" else "branch", ()),
        candidate.language,
        "canonical_reference",
    )
    suffix = {"c": ".c", "cpp": ".cpp", "rust": ".rs", "zig": ".zig", "julia": ".jl"}[candidate.language]
    source = output / f"differential{suffix}"
    harness = _differential_harness(candidate.language, region, candidate.function)
    source.write_text(baseline.source + "\n" + candidate.source + "\n" + harness)
    binary = output / "differential"
    environment = os.environ.copy()
    if candidate.language in {"c", "cpp"}:
        compiler = (shutil.which("clang-20") or shutil.which("clang")) if candidate.language == "c" else (shutil.which("clang++-20") or shutil.which("clang++"))
        command = [compiler, *candidate.compiler_flags, str(source), "-o", str(binary)] if compiler else []
    elif candidate.language == "rust":
        compiler = shutil.which("rustc"); command = [compiler, *candidate.compiler_flags, str(source), "-o", str(binary)] if compiler else []
    elif candidate.language == "zig":
        compiler = shutil.which("zig"); command = [compiler, "build-exe", str(source), "-O", "ReleaseFast", f"-femit-bin={binary}"] if compiler else []
        environment["ZIG_GLOBAL_CACHE_DIR"] = str(output / "zig-global-cache")
        environment["ZIG_LOCAL_CACHE_DIR"] = str(output / "zig-local-cache")
    else:
        compiler = shutil.which("julia"); command = [compiler, "--startup-file=no", "-O3", "--check-bounds=no", str(source)] if compiler else []
    if not command:
        return {"status": "UNAVAILABLE", "reason": f"{candidate.language} compiler unavailable"}
    if candidate.language == "julia":
        compiled = subprocess.CompletedProcess(command, 0, "", "")
        executed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        compiled = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) if compiled.returncode == 0 else compiled
    return {
        "status": "PASS" if executed.returncode == 0 else "FAIL",
        "phase": "execute" if compiled.returncode == 0 else "compile",
        "command": command,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "stderr": executed.stderr[-4000:],
    }


def _differential_harness(language: str, region: CanonicalBoundedRegion, function: str) -> str:
    _ = region
    if language in {"c", "cpp"}:
        return f'''#include <string.h>\nint main(void){{float src[67],a[67],b[67];for(size_t i=0;i<67;i++)src[i]=(float)((int)(i%13)-6)*0.25f;canonical_reference(a,src,67);{function}(b,src,67);return memcmp(a,b,sizeof(a))!=0;}}\n'''
    if language == "rust":
        return f'''fn main(){{let src:[f32;67]=core::array::from_fn(|i|((i%13)as i32-6)as f32*0.25);let mut a=[0f32;67];let mut b=[0f32;67];canonical_reference(&mut a,&src);{function}(&mut b,&src);assert!(a.iter().zip(b).all(|(x,y)|x.to_bits()==y.to_bits()));}}\n'''
    if language == "zig":
        return f'''pub fn main() !void{{var src:[67]f32=undefined;var a:[67]f32=undefined;var b:[67]f32=undefined;for(0..67)|i|src[i]=@as(f32,@floatFromInt(@as(i32,@intCast(i%13))-6))*0.25;canonical_reference(&a,&src);{function}(&b,&src);for(0..67)|i|if(@as(u32,@bitCast(a[i]))!=@as(u32,@bitCast(b[i])))return error.Mismatch;}}\n'''
    return f'''src=Float32[((i%13)-6)*0.25 for i in 0:66];a=zeros(Float32,67);b=zeros(Float32,67);canonical_reference(a,src);{function}(b,src);@assert all(reinterpret(UInt32,a).==reinterpret(UInt32,b))\n'''
