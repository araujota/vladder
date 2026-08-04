from __future__ import annotations

from dataclasses import dataclass
import re

from .flow import FlowGraph


@dataclass(frozen=True)
class GraphAST:
    canonical: str
    expression: "CExpr"
    parameters: dict[str, str]
    exact_fp: bool = True


@dataclass(frozen=True)
class CExpr:
    op: str
    args: tuple["CExpr", ...] = ()
    value: str = ""

    def render(self, parent_precedence: int = 0) -> str:
        if self.op == "atom":
            return self.value
        if self.op == "neg":
            return "-" + self.args[0].render(90)
        if self.op == "select":
            text = f"{self.args[0].render()} ? {self.args[1].render()} : {self.args[2].render()}"
            return f"({text})" if parent_precedence > 10 else text
        precedence = {"<": 40, ">": 40, "<=": 40, ">=": 40, "+": 50, "-": 50, "*": 60, "/": 60}[self.op]
        text = f"{self.args[0].render(precedence)} {self.op} {self.args[1].render(precedence + (1 if self.op in {'-', '/'} else 0))}"
        return f"({text})" if precedence < parent_precedence else text


def graph_ast(graph: FlowGraph) -> GraphAST | None:
    p = graph.source_pattern
    if graph.canonical == "affine" and {"mul", "add"} <= p.keys():
        return GraphAST("affine", parse_c_expr(f"x * {p['mul']} + {p['add']}"), {"mul": p["mul"], "add": p["add"]})
    if graph.canonical == "div_const":
        return GraphAST("div_const", parse_c_expr(f"x / {p['divisor']}"), {"divisor": p["divisor"]})
    if graph.canonical == "saturating_projection":
        lo, hi = p["low"], p["high"]
        return GraphAST("saturating_projection", parse_c_expr(f"x < {lo} ? {lo} : (x > {hi} ? {hi} : x)"), {"low": lo, "high": hi})
    if p.get("expression") and graph.family in {"pointwise_map", "guarded_pointwise_map"}:
        try:
            expression = parse_c_expr(str(p["expression"]))
            if not _closed_over_x(expression):
                return None
            return GraphAST(graph.canonical, expression, {})
        except ValueError:
            return None
    return None


def lift_c(ast: GraphAST, realization: str, function: str = "transform_candidate") -> str:
    if realization in {"avx2", "avx512"}:
        return _lift_vector(ast, realization, function)
    unroll = 4 if realization in {"unroll4", "select_unroll4"} else 1
    expr = _scalar_expr(ast)
    qualifier = ""
    lines = [f"void {function}(float *dst, const float *src, size_t n) {{"]
    if unroll > 1:
        lines.append("    size_t i = 0;")
        lines.append(f"    for (; i + {unroll - 1} < n; i += {unroll}) {{")
        for lane in range(unroll):
            lines.append(f"        float x{lane} = src[i + {lane}];")
            lines.append(f"        dst[i + {lane}] = {expr.replace('x', f'x{lane}')};")
        lines.append("    }")
        lines.append("    for (; i < n; ++i) {")
    else:
        lines.append("    for (size_t i = 0; i < n; ++i) {")
    lines.append("        float x = src[i];")
    lines.append(f"        dst[i] = {expr};")
    lines.append("    }")
    lines.append("}")
    return qualifier + "\n".join(lines)


def _scalar_expr(ast: GraphAST) -> str:
    return ast.expression.render()


def _lift_vector(ast: GraphAST, realization: str, function: str) -> str:
    width = 8 if realization == "avx2" else 16
    prefix = "_mm256" if realization == "avx2" else "_mm512"
    vec = "__m256" if realization == "avx2" else "__m512"
    scalar = _scalar_expr(ast)
    lines = [f"void {function}(float * restrict dst, const float * restrict src, size_t n) {{", "    size_t i = 0;", f"    for (; i + {width - 1} < n; i += {width}) {{", f"        {vec} x = {prefix}_loadu_ps(src + i);"]
    if ast.canonical == "affine":
        mul, add = ast.parameters["mul"], ast.parameters["add"]
        lines.extend([f"        {vec} m = {prefix}_set1_ps({mul});", f"        {vec} a = {prefix}_set1_ps({add});", f"        {vec} y = {prefix}_add_ps({prefix}_mul_ps(x, m), a);"])
    elif ast.canonical == "div_const":
        div = ast.parameters["divisor"]
        lines.extend([f"        {vec} d = {prefix}_set1_ps({div});", f"        {vec} y = {prefix}_div_ps(x, d);"])
    elif realization == "avx2":
        lo, hi = ast.parameters["low"], ast.parameters["high"]
        lines.extend([f"        {vec} vlo = {prefix}_set1_ps({lo});", f"        {vec} vhi = {prefix}_set1_ps({hi});", f"        {vec} below = {prefix}_cmp_ps(x, vlo, _CMP_LT_OQ);", f"        {vec} above = {prefix}_cmp_ps(x, vhi, _CMP_GT_OQ);", f"        {vec} y = {prefix}_blendv_ps(x, vhi, above);", f"        y = {prefix}_blendv_ps(y, vlo, below);"])
    else:
        lo, hi = ast.parameters["low"], ast.parameters["high"]
        lines.extend([f"        {vec} vlo = {prefix}_set1_ps({lo});", f"        {vec} vhi = {prefix}_set1_ps({hi});", "        __mmask16 below = _mm512_cmp_ps_mask(x, vlo, _CMP_LT_OQ);", "        __mmask16 above = _mm512_cmp_ps_mask(x, vhi, _CMP_GT_OQ);", "        __m512 y = _mm512_mask_mov_ps(x, above, vhi);", "        y = _mm512_mask_mov_ps(y, below, vlo);"])
    lines.extend([f"        {prefix}_storeu_ps(dst + i, y);", "    }", "    for (; i < n; ++i) {", "        float x = src[i];", f"        dst[i] = {scalar};", "    }", "}"])
    return "\n".join(lines)


TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fF]?)|([A-Za-z_]\w*)|(<=|>=|==|!=|[+\-*/()?:<>]))")


def parse_c_expr(text: str) -> CExpr:
    tokens: list[str] = []
    position = 0
    while position < len(text):
        match = TOKEN.match(text, position)
        if not match:
            raise ValueError(f"unsupported C expression near {text[position:position + 20]!r}")
        tokens.append(next(group for group in match.groups() if group is not None))
        position = match.end()
    index = 0

    def parse(min_precedence: int = 0) -> CExpr:
        nonlocal index
        if index >= len(tokens):
            raise ValueError("unexpected end of expression")
        token = tokens[index]
        index += 1
        if token == "(":
            left = parse()
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError("missing closing parenthesis")
            index += 1
        elif token == "-":
            left = CExpr("neg", (parse(80),))
        elif re.match(r"[A-Za-z_]\w*|\d", token):
            left = CExpr("atom", value=token)
        else:
            raise ValueError(f"unexpected token {token}")
        precedence = {"?": 10, "<": 40, ">": 40, "<=": 40, ">=": 40, "+": 50, "-": 50, "*": 60, "/": 60}
        while index < len(tokens) and tokens[index] in precedence and precedence[tokens[index]] >= min_precedence:
            op = tokens[index]
            index += 1
            if op == "?":
                yes = parse()
                if index >= len(tokens) or tokens[index] != ":":
                    raise ValueError("missing ternary colon")
                index += 1
                no = parse(10)
                left = CExpr("select", (left, yes, no))
            else:
                right = parse(precedence[op] + 1)
                left = CExpr(op, (left, right))
        return left

    result = parse()
    if index != len(tokens):
        raise ValueError(f"unconsumed token {tokens[index]}")
    return result


def _closed_over_x(expr: CExpr) -> bool:
    if expr.op == "atom":
        return expr.value == "x" or bool(re.fullmatch(r"\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fF]?", expr.value))
    return all(_closed_over_x(arg) for arg in expr.args)
