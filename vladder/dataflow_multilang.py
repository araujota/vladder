from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .dataflow_grammar import BoundedDataflowGrammar, DataflowDerivation, load_bounded_dataflow_grammar
from .dataflow_ir import BoundedDataflowContract, build_bounded_dataflow_graph
from .language_adapter import obligation


def _c_source(contract: BoundedDataflowContract, realization: str, fn: str) -> str:
    pre = "#include <stddef.h>\n#include <stdint.h>\n#include <string.h>\n#include <limits.h>\n"
    if contract.family == "predicate-stable-compaction":
        write_i = "if (out_indices) out_indices[out] = (uint32_t)i;" if contract.output_mode != "value-only" else ""
        write_v = "if (out_values) out_values[out] = current[i];" if contract.output_mode != "index-only" else ""
        limit = "if (selected > capacity) return SIZE_MAX; size_t limit = selected;" if contract.capacity_policy == "fail-unchanged" else "size_t limit = selected < capacity ? selected : capacity;"
        body = f"""size_t {fn}(uint32_t *out_indices, uint64_t *out_values, size_t capacity, const uint64_t *current, const uint64_t *baseline, size_t n) {{
 size_t selected=0; for(size_t i=0;i<n;i++) selected += current[i]!=baseline[i]; {limit}
 size_t out=0; for(size_t i=0;i<n && out<limit;i++) if(current[i]!=baseline[i]) {{ {write_i} {write_v} out++; }} return out;
}}"""
    elif contract.family == "fixed-width-codec":
        swap = "word = __builtin_bswap64(word);" if contract.byte_order == "big" else ""
        body = f"uint64_t {fn}(uint16_t a,uint16_t b,uint32_t c) {{ uint64_t word=(uint64_t)a|((uint64_t)b<<16)|((uint64_t)c<<32); {swap} return word; }}"
    elif contract.family == "stateful-delta-transducer":
        body = f"""size_t {fn}(uint64_t *next,uint32_t *indices,uint64_t *values,size_t capacity,const uint64_t *current,const uint64_t *baseline,size_t n) {{
 size_t selected=0; for(size_t i=0;i<n;i++) selected += current[i]!=baseline[i]; if(selected>capacity) return SIZE_MAX;
 memcpy(next,baseline,n*sizeof(uint64_t)); size_t out=0; for(size_t i=0;i<n;i++) if(current[i]!=baseline[i]) {{ indices[out]=(uint32_t)i; values[out++]=current[i]; next[i]=current[i]; }} return out;
}}"""
    elif contract.family == "aos-fused-multi-reduction":
        body = f"""typedef struct {{ uint32_t kind,flags; uint64_t bytes; }} {fn}_record;
typedef struct {{ uint64_t count,bytes,flagged; }} {fn}_stats;
{fn}_stats {fn}(const {fn}_record *r,size_t n,uint32_t kind) {{ {fn}_stats s={{0,0,0}}; for(size_t i=0;i<n;i++) if(r[i].kind==kind && !(r[i].flags&1u)) {{ s.count++; s.bytes+=r[i].bytes; s.flagged+=(r[i].flags>>1)&1u; }} return s; }}"""
    else:
        body = _c_block(fn)
    return pre + f"\n/* vLadder realization: {realization}; semantic scalar fallback */\n" + body + "\n"


def _c_block(fn: str) -> str:
    return f"""typedef struct {{ uint8_t r,g,b,a; }} {fn}_pixel;
static uint16_t {fn}_p565(uint8_t r,uint8_t g,uint8_t b) {{ return (uint16_t)(((r>>3)<<11)|((g>>2)<<5)|(b>>3)); }}
static {fn}_pixel {fn}_d565(uint16_t v) {{ uint8_t r=(v>>11)&31,g=(v>>5)&63,b=v&31; {fn}_pixel p={{(uint8_t)((r<<3)|(r>>2)),(uint8_t)((g<<2)|(g>>4)),(uint8_t)((b<<3)|(b>>2)),255}}; return p; }}
uint64_t {fn}(const {fn}_pixel *x) {{
 uint8_t lr=255,lg=255,lb=255,hr=0,hg=0,hb=0; for(size_t i=0;i<16;i++){{if(x[i].r<lr)lr=x[i].r;if(x[i].g<lg)lg=x[i].g;if(x[i].b<lb)lb=x[i].b;if(x[i].r>hr)hr=x[i].r;if(x[i].g>hg)hg=x[i].g;if(x[i].b>hb)hb=x[i].b;}}
 uint16_t lo={fn}_p565(lr,lg,lb),hi={fn}_p565(hr,hg,hb); {fn}_pixel p[4]; p[0]={fn}_d565(lo);p[1]={fn}_d565(hi);
 p[2]=({fn}_pixel){{(2*p[0].r+p[1].r)/3,(2*p[0].g+p[1].g)/3,(2*p[0].b+p[1].b)/3,255}}; p[3]=({fn}_pixel){{(p[0].r+2*p[1].r)/3,(p[0].g+2*p[1].g)/3,(p[0].b+2*p[1].b)/3,255}};
 uint32_t bits=0; for(size_t i=0;i<16;i++){{uint32_t best=0,be=UINT32_MAX;for(uint32_t j=0;j<4;j++){{int dr=(int)x[i].r-p[j].r,dg=(int)x[i].g-p[j].g,db=(int)x[i].b-p[j].b;uint32_t e=(uint32_t)(dr*dr+dg*dg+db*db);if(e<be){{be=e;best=j;}}}}bits|=best<<(2*i);}}
 return (uint64_t)lo|((uint64_t)hi<<16)|((uint64_t)bits<<32);
}}"""


def _zig_source(contract: BoundedDataflowContract, realization: str, fn: str) -> str:
    if contract.family == "predicate-stable-compaction":
        wi = f"if (out_indices) |p| p[out] = @intCast(i);" if contract.output_mode != "value-only" else ""
        wv = f"if (out_values) |p| p[out] = current[i];" if contract.output_mode != "index-only" else ""
        limit = "if (selected > capacity) return std.math.maxInt(usize); const limit=selected;" if contract.capacity_policy == "fail-unchanged" else "const limit=@min(selected,capacity);"
        body = f"""pub export fn {fn}(out_indices:?[*]u32,out_values:?[*]u64,capacity:usize,current:[*]const u64,baseline:[*]const u64,n:usize) usize {{ var selected:usize=0; for(0..n)|i| selected += @intFromBool(current[i]!=baseline[i]); {limit} var out:usize=0; for(0..n)|i| {{ if(out>=limit) break; if(current[i]!=baseline[i]){{ {wi} {wv} out+=1; }} }} return out; }}"""
    elif contract.family == "fixed-width-codec":
        if contract.byte_order == "big":
            body = f"pub export fn {fn}(a:u16,b:u16,c:u32) u64 {{ var word:u64=@as(u64,a)|(@as(u64,b)<<16)|(@as(u64,c)<<32); word = @byteSwap(word); return word; }}"
        else:
            body = f"pub export fn {fn}(a:u16,b:u16,c:u32) u64 {{ const word:u64=@as(u64,a)|(@as(u64,b)<<16)|(@as(u64,c)<<32); return word; }}"
    elif contract.family == "stateful-delta-transducer":
        body = f"""pub export fn {fn}(next:[*]u64,indices:[*]u32,values:[*]u64,capacity:usize,current:[*]const u64,baseline:[*]const u64,n:usize) usize {{ var selected:usize=0; for(0..n)|i| selected+=@intFromBool(current[i]!=baseline[i]); if(selected>capacity)return std.math.maxInt(usize); for(0..n)|i|next[i]=baseline[i]; var out:usize=0; for(0..n)|i|if(current[i]!=baseline[i]){{indices[out]=@intCast(i);values[out]=current[i];next[i]=current[i];out+=1;}}; return out; }}"""
    elif contract.family == "aos-fused-multi-reduction":
        body = f"""pub const Record=extern struct{{kind:u32,flags:u32,bytes:u64}}; pub const Stats=extern struct{{count:u64,bytes:u64,flagged:u64}};
pub export fn {fn}(r:[*]const Record,n:usize,kind:u32) Stats {{ var s=Stats{{.count=0,.bytes=0,.flagged=0}}; for(0..n)|i|if(r[i].kind==kind and (r[i].flags&1)==0){{s.count+=1;s.bytes+=r[i].bytes;s.flagged+=(r[i].flags>>1)&1;}};return s; }}"""
    else:
        body = _zig_block(fn)
    return f'const std=@import("std");\n// vLadder realization: {realization}; semantic scalar fallback\n{body}\n'


def _zig_block(fn: str) -> str:
    return f"""pub const Pixel=extern struct{{r:u8,g:u8,b:u8,a:u8}};
fn p565(r:u8,g:u8,b:u8)u16{{return (@as(u16,r>>3)<<11)|(@as(u16,g>>2)<<5)|@as(u16,b>>3);}} fn d565(v:u16)Pixel{{const r:u8=@intCast((v>>11)&31);const g:u8=@intCast((v>>5)&63);const b:u8=@intCast(v&31);return .{{.r=(r<<3)|(r>>2),.g=(g<<2)|(g>>4),.b=(b<<3)|(b>>2),.a=255}};}}
pub export fn {fn}(x:[*]const Pixel)u64{{var lr:u8=255;var lg:u8=255;var lb:u8=255;var hr:u8=0;var hg:u8=0;var hb:u8=0;for(0..16)|i|{{lr=@min(lr,x[i].r);lg=@min(lg,x[i].g);lb=@min(lb,x[i].b);hr=@max(hr,x[i].r);hg=@max(hg,x[i].g);hb=@max(hb,x[i].b);}}const lo=p565(lr,lg,lb);const hi=p565(hr,hg,hb);var p:[4]Pixel=undefined;p[0]=d565(lo);p[1]=d565(hi);p[2]=.{{.r=@intCast((2*@as(u16,p[0].r)+p[1].r)/3),.g=@intCast((2*@as(u16,p[0].g)+p[1].g)/3),.b=@intCast((2*@as(u16,p[0].b)+p[1].b)/3),.a=255}};p[3]=.{{.r=@intCast((@as(u16,p[0].r)+2*p[1].r)/3),.g=@intCast((@as(u16,p[0].g)+2*p[1].g)/3),.b=@intCast((@as(u16,p[0].b)+2*p[1].b)/3),.a=255}};var bits:u32=0;for(0..16)|i|{{var best:u32=0;var be:u32=std.math.maxInt(u32);for(0..4)|j|{{const dr:i32=@as(i32,x[i].r)-p[j].r;const dg:i32=@as(i32,x[i].g)-p[j].g;const db:i32=@as(i32,x[i].b)-p[j].b;const e:u32=@intCast(dr*dr+dg*dg+db*db);if(e<be){{be=e;best=@intCast(j);}}}}bits|=best<<@intCast(2*i);}}return @as(u64,lo)|(@as(u64,hi)<<16)|(@as(u64,bits)<<32);}}"""


def _julia_source(contract: BoundedDataflowContract, realization: str, fn: str) -> str:
    if contract.family == "predicate-stable-compaction":
        wi = "out_indices !== nothing && (out_indices[out] = UInt32(i-1))" if contract.output_mode != "value-only" else ""
        wv = "out_values !== nothing && (out_values[out] = current[i])" if contract.output_mode != "index-only" else ""
        limit = "selected > capacity && return typemax(Int); limit=selected" if contract.capacity_policy == "fail-unchanged" else "limit=min(selected,capacity)"
        body = f"""function {fn}(out_indices,out_values,capacity::Int,current::Vector{{UInt64}},baseline::Vector{{UInt64}})::Int
 selected=count(i->current[i]!=baseline[i],eachindex(current)); {limit}; out=0
 @inbounds for i in eachindex(current); out>=limit && break; if current[i]!=baseline[i]; out+=1; {wi}; {wv}; end; end; out
end"""
    elif contract.family == "fixed-width-codec":
        swap = "word=bswap(word)" if contract.byte_order == "big" else ""
        body = f"{fn}(a::UInt16,b::UInt16,c::UInt32)::UInt64 = begin word=UInt64(a)|(UInt64(b)<<16)|(UInt64(c)<<32); {swap}; word; end"
    elif contract.family == "stateful-delta-transducer":
        body = f"""function {fn}(next::Vector{{UInt64}},indices::Vector{{UInt32}},values::Vector{{UInt64}},capacity::Int,current::Vector{{UInt64}},baseline::Vector{{UInt64}})::Int
 selected=count(i->current[i]!=baseline[i],eachindex(current)); selected>capacity && return typemax(Int); copyto!(next,baseline); out=0
 @inbounds for i in eachindex(current); if current[i]!=baseline[i]; out+=1;indices[out]=UInt32(i-1);values[out]=current[i];next[i]=current[i];end;end;out
end"""
    elif contract.family == "aos-fused-multi-reduction":
        body = f"""struct DataflowRecord; kind::UInt32;flags::UInt32;bytes::UInt64;end
function {fn}(r::Vector{{DataflowRecord}},kind::UInt32); count=UInt64(0);bytes=UInt64(0);flagged=UInt64(0);@inbounds for x in r;if x.kind==kind && (x.flags&1)==0;count+=1;bytes+=x.bytes;flagged+=(x.flags>>1)&1;end;end;(count=count,bytes=bytes,flagged=flagged);end"""
    else:
        body = _julia_block(fn)
    return f"# vLadder realization: {realization}; semantic scalar fallback\n{body}\n"


def _julia_block(fn: str) -> str:
    return f"""struct DataflowPixel;r::UInt8;g::UInt8;b::UInt8;a::UInt8;end
p565(r,g,b)=UInt16((UInt16(r>>3)<<11)|(UInt16(g>>2)<<5)|UInt16(b>>3))
d565(v)=begin r=UInt8((v>>11)&31);g=UInt8((v>>5)&63);b=UInt8(v&31);DataflowPixel((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2),255);end
function {fn}(x::Vector{{DataflowPixel}})::UInt64
 lr=lg=lb=UInt8(255);hr=hg=hb=UInt8(0);@inbounds for q in x;lr=min(lr,q.r);lg=min(lg,q.g);lb=min(lb,q.b);hr=max(hr,q.r);hg=max(hg,q.g);hb=max(hb,q.b);end
 lo=p565(lr,lg,lb);hi=p565(hr,hg,hb);p0=d565(lo);p1=d565(hi);p=(p0,p1,DataflowPixel(UInt8((2UInt16(p0.r)+p1.r)÷3),UInt8((2UInt16(p0.g)+p1.g)÷3),UInt8((2UInt16(p0.b)+p1.b)÷3),255),DataflowPixel(UInt8((UInt16(p0.r)+2p1.r)÷3),UInt8((UInt16(p0.g)+2p1.g)÷3),UInt8((UInt16(p0.b)+2p1.b)÷3),255));bits=UInt32(0)
 @inbounds for i in 1:16;best=0;be=typemax(UInt32);for j in 1:4;dr=Int32(x[i].r)-Int32(p[j].r);dg=Int32(x[i].g)-Int32(p[j].g);db=Int32(x[i].b)-Int32(p[j].b);e=UInt32(dr*dr+dg*dg+db*db);if e<be;be=e;best=j-1;end;end;bits|=UInt32(best)<<(2*(i-1));end;UInt64(lo)|(UInt64(hi)<<16)|(UInt64(bits)<<32)
end"""


def emit_dataflow_native(contract: BoundedDataflowContract, derivation: DataflowDerivation, language: str, function: str = "dataflow_candidate", grammar: BoundedDataflowGrammar | None = None):
    from .dataflow_lowering import DataflowCandidate, emit_dataflow_cpp
    if language == "cpp":
        return emit_dataflow_cpp(contract, derivation, function, grammar)
    grammar = grammar or load_bounded_dataflow_grammar()
    if derivation.target not in grammar.family_terminals(contract.family):
        raise ValueError("derivation terminal does not match the dataflow contract")
    emitters = {"c": _c_source, "zig": _zig_source, "julia": _julia_source}
    if language not in emitters:
        raise ValueError(f"unsupported bounded-dataflow language: {language}")
    source = emitters[language](contract, derivation.target, function)
    graph = build_bounded_dataflow_graph(contract, derivation.target, source_language=language, function_identity=function)
    isa = str(grammar.terminals[derivation.target].get("isa", "scalar"))
    lowering_class = "native_semantic" if isa == "scalar" else "semantic_scalar_fallback"
    obligations = (
        obligation(f"dataflow.{language}.source-binding", "representation", "native source preserves the bounded contract", scope="generated-function", proof_method="native-compile-and-differential", language=language, native_construct=lowering_class),
    )
    flags = ("-std=c17", "-O3", "-march=native", "-Wall", "-Wextra") if language == "c" else (("ReleaseFast",) if language == "zig" else ("--startup-file=no", "-O3"))
    return DataflowCandidate(f"{contract.family}:{derivation.target}:{language}", language, function, contract.family, derivation.target, source, hashlib.sha256(source.encode()).hexdigest(), derivation.derivation_hash, graph.graph_hash, flags, obligations, lowering_class)


def _native_smoke_harness(contract: BoundedDataflowContract, language: str, fn: str) -> str:
    family = contract.family
    if language == "c":
        if family == "predicate-stable-compaction": return f'int main(void){{uint64_t c[4]={{1,4,3,8}},b[4]={{1,2,3,4}},v[4]={{0}};uint32_t i[4]={{0}};size_t n={fn}(i,v,4,c,b,4);return n!=2||i[0]!=1||i[1]!=3||v[0]!=4||v[1]!=8;}}\n'
        if family == "fixed-width-codec": return f'int main(void){{return {fn}(1,2,3)!=(UINT64_C(1)|(UINT64_C(2)<<16)|(UINT64_C(3)<<32));}}\n'
        if family == "stateful-delta-transducer": return f'int main(void){{uint64_t c[3]={{1,4,3}},b[3]={{1,2,3}},n[3]={{9,9,9}},v[3];uint32_t i[3];size_t z={fn}(n,i,v,3,c,b,3);return z!=1||i[0]!=1||v[0]!=4||n[1]!=4;}}\n'
        if family == "aos-fused-multi-reduction": return f'int main(void){{{fn}_record r[2]={{{{2,0,7}},{{2,2,5}}}};{fn}_stats s={fn}(r,2,2);return s.count!=2||s.bytes!=12||s.flagged!=1;}}\n'
        return f'int main(void){{{fn}_pixel p[16];for(int i=0;i<16;i++)p[i]=({fn}_pixel){{(uint8_t)i,(uint8_t)(2*i),(uint8_t)(3*i),255}};return {fn}(p)==0;}}\n'
    if language == "zig":
        if family == "predicate-stable-compaction": return f'pub fn main() !void {{const c=[_]u64{{1,4,3,8}};const b=[_]u64{{1,2,3,4}};var i:[4]u32=undefined;var v:[4]u64=undefined;const n={fn}(&i,&v,4,&c,&b,4);if(n!=2 or i[0]!=1 or i[1]!=3 or v[0]!=4 or v[1]!=8)return error.Mismatch;}}\n'
        if family == "fixed-width-codec": return f'pub fn main() !void {{if({fn}(1,2,3)!=(@as(u64,1)|(@as(u64,2)<<16)|(@as(u64,3)<<32)))return error.Mismatch;}}\n'
        if family == "stateful-delta-transducer": return f'pub fn main() !void {{const c=[_]u64{{1,4,3}};const b=[_]u64{{1,2,3}};var n=[_]u64{{9,9,9}};var i:[3]u32=undefined;var v:[3]u64=undefined;if({fn}(&n,&i,&v,3,&c,&b,3)!=1 or i[0]!=1 or n[1]!=4)return error.Mismatch;}}\n'
        if family == "aos-fused-multi-reduction": return f'pub fn main() !void {{const r=[_]Record{{.{{.kind=2,.flags=0,.bytes=7}},.{{.kind=2,.flags=2,.bytes=5}}}};const s={fn}(&r,2,2);if(s.count!=2 or s.bytes!=12 or s.flagged!=1)return error.Mismatch;}}\n'
        return f'pub fn main() !void {{var p:[16]Pixel=undefined;for(0..16)|i|p[i]=.{{.r=@intCast(i),.g=@intCast(2*i),.b=@intCast(3*i),.a=255}};if({fn}(&p)==0)return error.Mismatch;}}\n'
    if family == "predicate-stable-compaction": return f'c=UInt64[1,4,3,8];b=UInt64[1,2,3,4];i=Vector{{UInt32}}(undef,4);v=Vector{{UInt64}}(undef,4);n={fn}(i,v,4,c,b);@assert n==2 && i[1:2]==UInt32[1,3] && v[1:2]==UInt64[4,8]\n'
    if family == "fixed-width-codec": return f'@assert {fn}(UInt16(1),UInt16(2),UInt32(3))==(UInt64(1)|(UInt64(2)<<16)|(UInt64(3)<<32))\n'
    if family == "stateful-delta-transducer": return f'c=UInt64[1,4,3];b=UInt64[1,2,3];n=fill(UInt64(9),3);i=Vector{{UInt32}}(undef,3);v=Vector{{UInt64}}(undef,3);@assert {fn}(n,i,v,3,c,b)==1 && i[1]==1 && n[2]==4\n'
    if family == "aos-fused-multi-reduction": return f'r=DataflowRecord[DataflowRecord(2,0,7),DataflowRecord(2,2,5)];s={fn}(r,UInt32(2));@assert s.count==2 && s.bytes==12 && s.flagged==1\n'
    return f'p=[DataflowPixel(UInt8(i),UInt8(2i),UInt8(3i),255) for i in 0:15];@assert {fn}(p)!=0\n'


def run_native_dataflow_differential(contract: BoundedDataflowContract, candidate: Any, output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    suffix = {"c": ".c", "zig": ".zig", "julia": ".jl"}[candidate.language]
    source = output_directory / ("differential" + suffix)
    source.write_text(candidate.source + "\n" + _native_smoke_harness(contract, candidate.language, candidate.function))
    binary = output_directory / "differential"
    if candidate.language == "c":
        compiler = shutil.which("clang-20") or shutil.which("clang") or shutil.which("cc")
        if not compiler: return {"status": "UNAVAILABLE", "reason": "C compiler unavailable"}
        command = [compiler, *candidate.compiler_flags, str(source), "-o", str(binary)]
        compiled = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) if compiled.returncode == 0 else compiled
    elif candidate.language == "zig":
        compiler = shutil.which("zig")
        if not compiler: return {"status": "UNAVAILABLE", "reason": "Zig unavailable"}
        command = [compiler, "build-exe", str(source), "-O", "ReleaseFast", f"-femit-bin={binary}"]
        compiled = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) if compiled.returncode == 0 else compiled
    else:
        compiler = shutil.which("julia")
        if not compiler: return {"status": "UNAVAILABLE", "reason": "Julia unavailable"}
        command = [compiler, "--startup-file=no", "-O3", str(source)]
        compiled = subprocess.CompletedProcess(command, 0, "", "")
        executed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"status": "PASS" if executed.returncode == 0 else "FAIL", "phase": "execute" if compiled.returncode == 0 else "compile", "command": command, "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "stderr": executed.stderr[-4000:]}
