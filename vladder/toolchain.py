from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess


@dataclass(frozen=True)
class Toolchain:
    compiler: str
    compiler_kind: str
    llvm_mca: str | None
    alive_tv: str | None
    cbmc: str | None
    perf: str | None
    objdump: str | None
    nm: str | None


def discover_toolchain() -> Toolchain:
    compiler = None
    for name in ("clang-20", "clang", "gcc", "cc"):
        path = shutil.which(name)
        if path:
            compiler = path
            break
    if not compiler:
        raise RuntimeError("no C compiler found; install clang-20, clang, gcc, or cc")

    base = os.path.basename(compiler)
    kind = "clang" if "clang" in base else "gcc"
    llvm_mca = next(
        (
            path
            for name in ("llvm-mca-20", "llvm-mca", "llvm-mca-19", "llvm-mca-18", "llvm-mca-17")
            if (path := shutil.which(name))
        ),
        None,
    )
    return Toolchain(
        compiler=compiler,
        compiler_kind=kind,
        llvm_mca=llvm_mca,
        alive_tv=shutil.which("alive-tv"),
        cbmc=shutil.which("cbmc"),
        perf=shutil.which("perf"),
        objdump=shutil.which("objdump"),
        nm=shutil.which("nm"),
    )


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = None if env is None else {**os.environ, **env}
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, env=process_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def cpu_flags() -> set[str]:
    try:
        text = Path("/proc/cpuinfo").read_text()
    except OSError:
        return set()
    match = re.search(r"^flags\s*:\s*(.*)$", text, re.MULTILINE)
    if not match:
        return set()
    return set(match.group(1).split())


def cpu_model() -> str:
    try:
        text = Path("/proc/cpuinfo").read_text()
    except OSError:
        return "unknown"
    match = re.search(r"^model name\s*:\s*(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def compiler_version(compiler: str) -> str:
    result = run([compiler, "--version"], timeout=10)
    if result.returncode != 0:
        return compiler
    return result.stdout.splitlines()[0]


def tool_version(tool: str | None) -> str | None:
    if not tool:
        return None
    result = run([tool, "--version"], timeout=10)
    text = (result.stdout + result.stderr).strip()
    return text.splitlines()[0] if text else tool


def compile_c(
    tc: Toolchain,
    source: Path,
    output: Path,
    extra_flags: tuple[str, ...] = (),
    emit_asm: Path | None = None,
    emit_ir: Path | None = None,
) -> tuple[bool, str]:
    base_flags = ["-std=c99", "-O3", "-march=native", "-Wall", "-Wextra", "-fno-omit-frame-pointer"]
    cmd = [tc.compiler, *base_flags, *extra_flags, str(source), "-lm", "-o", str(output)]
    result = run(cmd, timeout=120)
    if result.returncode != 0:
        return False, result.stdout + result.stderr

    if emit_asm:
        asm_cmd = [tc.compiler, *base_flags, *extra_flags, "-S", str(source), "-o", str(emit_asm)]
        run(asm_cmd, timeout=120)
    if emit_ir and tc.compiler_kind == "clang":
        ir_cmd = [tc.compiler, *base_flags, *extra_flags, "-S", "-emit-llvm", str(source), "-o", str(emit_ir)]
        run(ir_cmd, timeout=120)
    return True, result.stdout + result.stderr


def emit_alive2_ir(tc: Toolchain, source: Path, output: Path, extra_flags: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Emit tractable proof IR without changing source-level arithmetic flags."""
    if tc.compiler_kind != "clang":
        return False, "Alive2 proof IR requires Clang"
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = [
        "-std=c99",
        "-march=native",
        *extra_flags,
        "-O1",
        "-fno-vectorize",
        "-fno-slp-vectorize",
        "-fno-unroll-loops",
        "-S",
        "-emit-llvm",
    ]
    result = run([tc.compiler, *flags, str(source), "-o", str(output)], timeout=120)
    return result.returncode == 0, result.stdout + result.stderr


def static_estimates(tc: Toolchain, binary: Path, asm: Path | None = None, function: str = "transform_candidate") -> dict[str, object]:
    estimates: dict[str, object] = {}
    if tc.nm:
        nm_result = run([tc.nm, "-S", "--size-sort", str(binary)], timeout=10)
        for line in nm_result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[-1] == function:
                try:
                    estimates["code_size_bytes"] = int(parts[1], 16)
                except ValueError:
                    pass
    if tc.objdump:
        obj_result = run([tc.objdump, "-d", "--demangle", str(binary)], timeout=20)
        in_fn = False
        instructions = 0
        for line in obj_result.stdout.splitlines():
            if f"<{function}>:" in line:
                in_fn = True
                continue
            if in_fn and re.search(r"<[^>]+>:", line):
                break
            if in_fn and re.match(r"\s*[0-9a-f]+:\s+([0-9a-f]{2}\s+)+", line):
                instructions += 1
        if instructions:
            estimates["instruction_count"] = instructions
    if tc.llvm_mca and asm and asm.exists():
        mca_input = _extract_function_asm(asm, function)
        mca_path = asm.with_suffix(".mca.s")
        if mca_input.strip():
            mca_path.write_text(mca_input)
        else:
            mca_path = asm
        mca = run([tc.llvm_mca, str(mca_path)], timeout=30)
        if mca.returncode == 0:
            for line in mca.stdout.splitlines():
                if line.strip().startswith("Total Cycles:"):
                    estimates["llvm_mca_total_cycles"] = line.split(":", 1)[1].strip()
                elif line.strip().startswith("Block RThroughput:"):
                    estimates["llvm_mca_block_rthroughput"] = line.split(":", 1)[1].strip()
            estimates["llvm_mca_input"] = str(mca_path)
        else:
            estimates["llvm_mca_error"] = mca.stderr.strip()[:500]
    elif not tc.llvm_mca:
        estimates["llvm_mca"] = "not available"
    return estimates


def alive2_check(tc: Toolchain, ir: Path, out_dir: Path, name: str, timeout: int = 20) -> dict[str, object]:
    if not ir.exists():
        return {"status": "unavailable", "reason": "LLVM IR file not found"}
    out_dir.mkdir(parents=True, exist_ok=True)
    sanitized = out_dir / f"{name}.alive.ll"
    log = out_dir / f"{name}.alive2.txt"
    _sanitize_ir_for_alive2(ir, sanitized)
    identity = _canonical_ir_identity(sanitized, "transform_ref", "transform_candidate")
    if identity:
        log.write_text("Canonical LLVM IR identity proved before solver invocation.\n")
        return {
            "status": "correct",
            "method": "canonical-llvm-ir-identity",
            "alive2_invoked": False,
            "reason": "reference and candidate proof functions are alpha-identical after symbol normalization",
            "sanitized_ir": str(sanitized),
            "log": str(log),
        }
    if not tc.alive_tv:
        return {
            "status": "unavailable",
            "reason": "alive-tv not found and canonical LLVM IR identity did not close the proof",
            "sanitized_ir": str(sanitized),
        }
    try:
        result = run(
            [
                tc.alive_tv,
                "--smt-to=5000",
                "--src-fn=transform_ref",
                "--tgt-fn=transform_candidate",
                str(sanitized),
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log.write_text("Alive2 timed out\n")
        return {"status": "timeout", "sanitized_ir": str(sanitized), "log": str(log)}
    output = result.stdout + result.stderr
    log.write_text(output)
    status = "error"
    if "Transformation seems to be correct" in output:
        status = "correct"
    elif "Transformation doesn't verify" in output:
        status = "incorrect"
    elif "Out of memory" in output:
        status = "oom"
    elif "Unsupported" in output or "Could not translate" in output:
        status = "unsupported"
    elif result.returncode == 124:
        status = "timeout"
    return {
        "status": status,
        "method": "alive-tv",
        "alive2_invoked": True,
        "returncode": result.returncode,
        "sanitized_ir": str(sanitized),
        "log": str(log),
        "summary": output.strip()[-1000:],
    }


def alive2_refinement_check(
    tc: Toolchain,
    source_ir: Path,
    target_ir: Path,
    out_dir: Path,
    name: str,
    *,
    function: str,
    timeout: int = 60,
) -> dict[str, object]:
    """Validate one same-named function across complete LLVM modules.

    Real C++ functions commonly depend on named aggregate types, globals, personality
    functions, and declarations that cannot be represented by concatenating two isolated
    function bodies.  Alive2's two-module interface preserves that context while restricting
    validation to the selected function.
    """
    if not source_ir.is_file() or not target_ir.is_file():
        return {"status": "unavailable", "reason": "source or target LLVM module is absent"}
    out_dir.mkdir(parents=True, exist_ok=True)
    source = out_dir / f"{name}.source.alive.ll"
    target = out_dir / f"{name}.target.alive.ll"
    log = out_dir / f"{name}.alive2.txt"
    _sanitize_ir_for_alive2(source_ir, source)
    _sanitize_ir_for_alive2(target_ir, target)
    if source.read_bytes() == target.read_bytes():
        log.write_text("Canonical complete-module identity proved before solver invocation.\n")
        return {
            "status": "correct",
            "method": "canonical-llvm-module-identity",
            "alive2_invoked": False,
            "source_ir": str(source),
            "target_ir": str(target),
            "log": str(log),
        }
    if not tc.alive_tv:
        return {
            "status": "unavailable",
            "reason": "alive-tv is unavailable",
            "source_ir": str(source),
            "target_ir": str(target),
        }
    try:
        result = run(
            [
                tc.alive_tv,
                "--smt-to=10000",
                f"--func={function}",
                str(source),
                str(target),
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log.write_text("Alive2 timed out\n")
        return {
            "status": "timeout",
            "method": "alive-tv-two-module",
            "alive2_invoked": True,
            "source_ir": str(source),
            "target_ir": str(target),
            "log": str(log),
        }
    output = result.stdout + result.stderr
    log.write_text(output)
    status = "error"
    if "Transformation seems to be correct" in output:
        status = "correct"
    elif "Transformation doesn't verify" in output:
        status = "incorrect"
    elif "Out of memory" in output:
        status = "oom"
    elif "Unsupported" in output or "Could not translate" in output:
        status = "unsupported"
    return {
        "status": status,
        "method": "alive-tv-two-module",
        "alive2_invoked": True,
        "returncode": result.returncode,
        "source_ir": str(source),
        "target_ir": str(target),
        "log": str(log),
        "summary": output.strip()[-2000:],
    }


def _canonical_ir_identity(ir: Path, source_function: str, target_function: str) -> bool:
    text = ir.read_text(errors="replace")

    def extract(name: str) -> str | None:
        match = re.search(rf"^define\s+.*@{re.escape(name)}\(", text, re.MULTILINE)
        if not match:
            return None
        opening = text.find("{", match.start())
        if opening < 0:
            return None
        depth = 0
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    return text[match.start() : index + 1].replace(f"@{name}", "@proof_function", 1)
        return None

    source = extract(source_function)
    target = extract(target_function)
    return source is not None and source == target


def _extract_function_asm(asm: Path, function: str) -> str:
    lines = asm.read_text(errors="replace").splitlines()
    start = None
    end = None
    label = f"{function}:"
    for i, line in enumerate(lines):
        if line.startswith(label):
            start = i
            break
    if start is None:
        return ""
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("\t.size") and function in line:
            end = i
            break
        if re.match(r"^[A-Za-z_.$][\w.$]*:\s*(#.*)?$", line) and not line.startswith(".L"):
            end = i
            break
    selected = lines[start:end] if end is not None else lines[start:]
    filtered = []
    for line in selected:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith((".cfi_", ".loc", ".file", ".type", ".size", ".globl", ".p2align")):
            continue
        filtered.append(line)
    return "\n".join(filtered) + "\n"


def _sanitize_ir_for_alive2(source: Path, dest: Path) -> None:
    text = source.read_text(errors="replace")
    remove_words = [
        "nocapture",
        "noundef",
        "local_unnamed_addr",
        "unnamed_addr",
        "norecurse",
        "nofree",
        "nosync",
        "nounwind",
        "writeonly",
        "readonly",
        "willreturn",
        "mustprogress",
        "uwtable",
        "optnone",
    ]
    lines = []
    for line in text.splitlines():
        if line.startswith("attributes #"):
            continue
        if line.startswith("!"):
            continue
        # Remove instruction metadata before stripping attribute words.  Metadata
        # names such as ``!noundef`` otherwise become malformed ``!!42`` tokens.
        # Apply repeatedly because one instruction may carry several attachments.
        previous = None
        while previous != line:
            previous = line
            line = re.sub(r",\s*![A-Za-z0-9_.-]+\s+![0-9]+", "", line)
        for word in remove_words:
            line = line.replace(f" {word} ", " ").replace(f" {word}", "").replace(f"{word} ", "")
        line = re.sub(r"\s+#[0-9]+(?=\s*\{)", " ", line)
        line = re.sub(r"\s+#[0-9]+(?=\s*$)", "", line)
        if line.startswith(("define ", "declare ")):
            line = re.sub(r"\s+", " ", line)
        lines.append(line)
    dest.write_text("\n".join(lines) + "\n")
