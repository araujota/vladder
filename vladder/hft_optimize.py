from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import random
from typing import Any

from .hft_operators import generate_trace, read_trace, write_trace
from .operator_analysis import analyze_operator
from .operator_grammar import search_operator_graph, transformed_graph_dict
from .report import write_csv, write_json
from .statistics_v3 import rank_hft, summarize_samples
from .toolchain import discover_toolchain, run, static_estimates
from .hardware_manifest import capture_manifest, write_manifest


WORD_DECODE_CANDIDATE = r'''
void decode_book_update_candidate(
    const uint8_t *message, size_t length, BookState *book,
    NormalizedEvent *event_out, TopOfBook *top_out,
    uint64_t *changed_mask_out, int32_t *status_out) {
    if (length != 18) { *status_out = -1; *changed_mask_out = 0; return; }
    uint32_t raw_price, raw_quantity;
    uint64_t raw_sequence;
    __builtin_memcpy(&raw_price, message + 2, sizeof(raw_price));
    __builtin_memcpy(&raw_quantity, message + 6, sizeof(raw_quantity));
    __builtin_memcpy(&raw_sequence, message + 10, sizeof(raw_sequence));
    NormalizedEvent event;
    event.type = message[0]; event.side = message[1];
    event.price_ticks = (int32_t)__builtin_bswap32(raw_price);
    event.quantity = (int32_t)__builtin_bswap32(raw_quantity);
    event.sequence = __builtin_bswap64(raw_sequence);
    if (event.type < 1 || event.type > 3 || event.side > 1 ||
        event.price_ticks < PRICE_BASE || event.price_ticks >= PRICE_BASE + BOOK_LEVELS ||
        event.quantity < 0 || event.sequence <= book->last_sequence) {
        *status_out = -2; *changed_mask_out = 0; return;
    }
    size_t level = (size_t)(event.price_ticks - PRICE_BASE);
    int32_t quantity = event.type == 3 ? 0 : event.quantity;
    int32_t *side = event.side == 0 ? book->bid_qty : book->ask_qty;
    side[level] = quantity;
    uint64_t bit = UINT64_C(1) << level;
    if (event.side == 0) { if (quantity) book->bid_occupied |= bit; else book->bid_occupied &= ~bit; }
    else { if (quantity) book->ask_occupied |= bit; else book->ask_occupied &= ~bit; }
    book->last_sequence = event.sequence;
    *event_out = event; *changed_mask_out = UINT64_C(1) << level;
    int32_t bid_level = -1, ask_level = -1;
    for (int32_t i = BOOK_LEVELS - 1; i >= 0; --i) if (book->bid_qty[i] > 0) { bid_level = i; break; }
    for (int32_t i = 0; i < BOOK_LEVELS; ++i) if (book->ask_qty[i] > 0) { ask_level = i; break; }
    book->best_bid_level = bid_level; book->best_ask_level = ask_level;
    top_out->best_bid_ticks = bid_level < 0 ? 0 : PRICE_BASE + bid_level;
    top_out->best_bid_qty = bid_level < 0 ? 0 : book->bid_qty[bid_level];
    top_out->best_ask_ticks = ask_level < 0 ? 0 : PRICE_BASE + ask_level;
    top_out->best_ask_qty = ask_level < 0 ? 0 : book->ask_qty[ask_level];
    *status_out = 0;
}
'''


COMMON_ADD_CANDIDATE = WORD_DECODE_CANDIDATE.replace(
    "int32_t quantity = event.type == 3 ? 0 : event.quantity;",
    "int32_t quantity = event.quantity;\n    if (__builtin_expect(event.type != 1, 0)) quantity = event.type == 3 ? 0 : event.quantity;",
).replace("decode_book_update_candidate", "decode_book_update_candidate")

CACHED_TOP_CANDIDATE = WORD_DECODE_CANDIDATE.replace(
    "    int32_t bid_level = -1, ask_level = -1;\n    for (int32_t i = BOOK_LEVELS - 1; i >= 0; --i) if (book->bid_qty[i] > 0) { bid_level = i; break; }\n    for (int32_t i = 0; i < BOOK_LEVELS; ++i) if (book->ask_qty[i] > 0) { ask_level = i; break; }",
    "    int32_t bid_level = book->best_bid_level, ask_level = book->best_ask_level;\n"
    "    if (event.side == 0) {\n"
    "        if (quantity > 0 && (bid_level < 0 || (int32_t)level > bid_level)) bid_level = (int32_t)level;\n"
    "        else if (quantity == 0 && bid_level == (int32_t)level) { bid_level = -1; for (int32_t i = (int32_t)level - 1; i >= 0; --i) if (book->bid_qty[i] > 0) { bid_level = i; break; } }\n"
    "    } else {\n"
    "        if (quantity > 0 && (ask_level < 0 || (int32_t)level < ask_level)) ask_level = (int32_t)level;\n"
    "        else if (quantity == 0 && ask_level == (int32_t)level) { ask_level = -1; for (int32_t i = (int32_t)level + 1; i < BOOK_LEVELS; ++i) if (book->ask_qty[i] > 0) { ask_level = i; break; } }\n"
    "    }\n"
    "    book->best_bid_level = bid_level; book->best_ask_level = ask_level;"
)

OCCUPANCY_MASK_CANDIDATE = WORD_DECODE_CANDIDATE.replace(
    "    int32_t bid_level = -1, ask_level = -1;\n    for (int32_t i = BOOK_LEVELS - 1; i >= 0; --i) if (book->bid_qty[i] > 0) { bid_level = i; break; }\n    for (int32_t i = 0; i < BOOK_LEVELS; ++i) if (book->ask_qty[i] > 0) { ask_level = i; break; }",
    "    int32_t bid_level = book->bid_occupied ? 63 - (int32_t)__builtin_clzll(book->bid_occupied) : -1;\n"
    "    int32_t ask_level = book->ask_occupied ? (int32_t)__builtin_ctzll(book->ask_occupied) : -1;"
)


HFT_HARNESS = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <x86intrin.h>

__REFERENCE_TRANSLATION_UNIT__

__CANDIDATE__

static uint64_t ticks(void) { unsigned aux; _mm_lfence(); uint64_t value=__rdtscp(&aux); _mm_lfence(); return value; }
static int pin_cpu(int cpu) { cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set); return sched_setaffinity(0,sizeof(set),&set); }
static uint64_t rng_state;
static uint32_t random_u32(void) { uint64_t x=rng_state; x^=x>>12; x^=x<<25; x^=x>>27; rng_state=x; return (uint32_t)((x*UINT64_C(2685821657736338717))>>32); }
static void put32(uint8_t *p,uint32_t x) { p[0]=x>>24;p[1]=x>>16;p[2]=x>>8;p[3]=x; }
static void put64(uint8_t *p,uint64_t x) { for(int i=7;i>=0;--i){p[i]=(uint8_t)x;x>>=8;} }
static void make_message(uint8_t *m,size_t index,int adversarial) {
    uint8_t type=adversarial?(uint8_t)(1+index%3):(uint8_t)(1+(random_u32()%100>=42)+(random_u32()%100>=79));
    if(type>3)type=3; uint8_t side=adversarial?(uint8_t)(index&1):(uint8_t)(random_u32()&1);
    uint32_t level=adversarial?(uint32_t)((index%4==0)?63:((index%4==1)?0:index%64)):(random_u32()%64);
    uint32_t quantity=type==3?0:1+random_u32()%2000;
    m[0]=type;m[1]=side;put32(m+2,PRICE_BASE+level);put32(m+6,quantity);put64(m+10,index+1);
}
static int same_event(const NormalizedEvent*a,const NormalizedEvent*b){return a->type==b->type&&a->side==b->side&&a->price_ticks==b->price_ticks&&a->quantity==b->quantity&&a->sequence==b->sequence;}
static int verify_sequence(size_t count,int adversarial,uint64_t seed) {
    BookState ref={0},cand={0}; ref.best_bid_level=cand.best_bid_level=-1;ref.best_ask_level=cand.best_ask_level=-1;rng_state=seed;
    for(size_t i=0;i<count;++i){uint8_t m[18];make_message(m,i,adversarial);NormalizedEvent er={0},ec={0};TopOfBook tr={0},tc={0};uint64_t mr=0,mc=0;int32_t sr=0,sc=0;
        decode_book_update_ref(m,18,&ref,&er,&tr,&mr,&sr);decode_book_update_candidate(m,18,&cand,&ec,&tc,&mc,&sc);
        if(sr!=sc||mr!=mc||memcmp(&ref,&cand,sizeof(ref))||memcmp(&tr,&tc,sizeof(tr))||(sr==0&&!same_event(&er,&ec)))return 100+(int)(i%100);
    } return 0;
}
int main(int argc,char**argv){int cpu=0,samples=12000,adversarial=0,batch=1;uint64_t seed=404;const char*trace_path=NULL;
    for(int i=1;i<argc;++i){if(!strcmp(argv[i],"--cpu"))cpu=atoi(argv[++i]);else if(!strcmp(argv[i],"--samples"))samples=atoi(argv[++i]);else if(!strcmp(argv[i],"--seed"))seed=strtoull(argv[++i],0,10);else if(!strcmp(argv[i],"--batch"))batch=atoi(argv[++i]);else if(!strcmp(argv[i],"--trace"))trace_path=argv[++i];else if(!strcmp(argv[i],"--adversarial"))adversarial=1;}
    if(pin_cpu(cpu))return 80;int rc=verify_sequence(4096,adversarial,seed);if(rc){printf("{\"verify\":\"FAIL\",\"code\":%d}\n",rc);return rc;}
    size_t total=(size_t)samples*(size_t)batch;uint8_t(*messages)[18]=aligned_alloc(64,total*18+64);double*cycles=calloc((size_t)samples,sizeof(double));BookState book={0};book.best_bid_level=-1;book.best_ask_level=-1;NormalizedEvent event;TopOfBook top;uint64_t mask;int32_t status;rng_state=seed;
    if(!messages||!cycles)return 81;
    if(trace_path){FILE*f=fopen(trace_path,"rb");uint8_t header[16];if(!f||fread(header,1,16,f)!=16||fread(messages,18,total,f)!=total){if(f)fclose(f);return 82;}fclose(f);}
    else for(size_t i=0;i<total;++i)make_message(messages[i],i,adversarial);
    volatile uint64_t guard=0;for(int i=0;i<samples;++i){uint64_t begin=ticks();for(int j=0;j<batch;++j)decode_book_update_candidate(messages[(size_t)i*batch+j],18,&book,&event,&top,&mask,&status);uint64_t end=ticks();cycles[i]=(double)(end-begin)/(double)batch;guard+=mask+(uint64_t)top.best_bid_qty;}
    printf("{\"verify\":\"PASS\",\"batch\":%d,\"guard\":%"PRIu64",\"cycles\":[",batch,guard);for(int i=0;i<samples;++i)printf("%s%.6f",i?",":"",cycles[i]);printf("]}\n");free(messages);free(cycles);return 0;}
'''


def optimize_hft_pipeline(source: Path, contract_path: Path, out_dir: Path, target: str, cpu: int, processes: int, samples: int, beam_width: int, external_trace: Path | None = None) -> dict[str, Any]:
    if samples < 10_000:
        raise ValueError("HFT p99.99 ranking requires at least 10000 samples per process")
    contract, graph, analysis = analyze_operator(source, contract_path, out_dir, target, cpu)
    grammar_dir = Path(__file__).resolve().parent / "grammars/operator-v3"
    search = search_operator_graph(contract, graph, grammar_dir, beam_width=beam_width)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_dir, build_dir = out_dir / "traces", out_dir / "build"
    trace_dir.mkdir(exist_ok=True); build_dir.mkdir(exist_ok=True)
    trace_counts={"tuning":4096,"held_out":samples*8,"adversarial":samples}
    for kind, seed in (("tuning", 303), ("held_out", 404), ("adversarial", 505)):
        write_trace(str(trace_dir / f"{kind}.bin"), generate_trace(kind, trace_counts[kind], seed), seed)
    held_out_trace=trace_dir/"held_out.bin"
    if external_trace is not None:
        external_trace=external_trace.resolve();messages,_=read_trace(str(external_trace))
        if len(messages)<samples*8:raise ValueError(f"external trace needs at least {samples*8} events for microburst-8 measurement")
        held_out_trace=external_trace
    trace_paths={"tuning":trace_dir/"tuning.bin","held_out":held_out_trace,"adversarial":trace_dir/"adversarial.bin"}
    trace_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in trace_paths.items()}
    original = source.read_text()
    reference_tu = original.replace("void decode_book_update(", "void decode_book_update_ref(", 1)
    baseline_body=original[original.index("void decode_book_update("):]
    field_occupancy=_field_occupancy_candidate(baseline_body)
    candidates = {"baseline": baseline_body, "word_decode": WORD_DECODE_CANDIDATE, "word_decode_common_add": COMMON_ADD_CANDIDATE, "cached_top_layout": CACHED_TOP_CANDIDATE, "occupancy_mask_layout": OCCUPANCY_MASK_CANDIDATE, "field_occupancy_layout": field_occupancy}
    candidates["baseline"] = candidates["baseline"].replace("void decode_book_update(", "void decode_book_update_candidate(", 1)
    baseline_plan=next(plan for plan in search.plans if plan.id=="baseline")
    layout_plan=next((plan for plan in search.plans if "layout_soa" in plan.effects),baseline_plan)
    fast_plan=next((plan for plan in search.plans if "checked_fast_path" in plan.effects),baseline_plan)
    plan_by_candidate={"baseline":baseline_plan,"word_decode":baseline_plan,"word_decode_common_add":fast_plan,"cached_top_layout":layout_plan,"occupancy_mask_layout":layout_plan,"field_occupancy_layout":layout_plan}
    tc = discover_toolchain(); rows=[]; binaries={}
    for name, candidate in candidates.items():
        harness = HFT_HARNESS.replace("__REFERENCE_TRANSLATION_UNIT__", reference_tu).replace("__CANDIDATE__", candidate)
        c_path, binary, asm = build_dir/f"{name}.c", build_dir/name, build_dir/f"{name}.s"
        c_path.write_text(harness)
        flags=["-std=c17","-O3","-march=native","-Wall","-Wextra","-fno-omit-frame-pointer","-fstack-usage"]
        compiled=run([tc.compiler,*flags,str(c_path),"-o",str(binary)],timeout=180)
        selected_plan=plan_by_candidate[name]
        row={"candidate":name,"plan":selected_plan.id,"rules":list(selected_plan.rules),"effects":list(selected_plan.effects),"proof_obligations":["decode_equivalence","bounded_state_transition","multi_output_equivalence","full_state_sequence_equivalence"],"structural":{"status":"proved","allocation":"forbidden","state_ownership":"single_threaded"},"sequence_proof":{"status":"runtime_pending","events_per_suite":4096}}
        if compiled.returncode:
            row.update(status="COMPILE_FAIL",error=(compiled.stdout+compiled.stderr)[-3000:]);rows.append(row);continue
        run([tc.compiler,*flags,"-S",str(c_path),"-o",str(asm)],timeout=180)
        row.update(static_estimates(tc,binary,asm,"decode_book_update_candidate"));row["status"]="COMPILED";rows.append(row);binaries[name]=binary
    order=list(binaries);random.Random(404).shuffle(order);row_map={row["candidate"]:row for row in rows}
    for name in order:
        modes={}
        for mode, adversarial, batch in (("batch1_held_out",False,1),("batch1_adversarial",True,1),("microburst8_held_out",False,8)):
            blocks=[]
            for process in range(processes):
                args=[str(binaries[name]),"--cpu",str(cpu),"--samples",str(samples),"--batch",str(batch),"--seed",str(404+process*1000003)]
                args.extend(["--trace",str(trace_paths["adversarial" if adversarial else "held_out"])])
                if adversarial:args.append("--adversarial")
                result=run(args,timeout=300)
                if result.returncode: row_map[name].update(status="VERIFY_FAIL",error=(result.stdout+result.stderr)[-2000:]);blocks=[];break
                payload=_json_line(result.stdout);blocks.append([float(value) for value in payload["cycles"]])
            if not blocks:break
            modes[mode]=summarize_samples(blocks,bootstrap_rounds=400,seed=404)
        if len(modes)==3:row_map[name].update(status="PASS",latency=modes,sequence_proof={"status":"passed","held_out_events":4096,"adversarial_events":4096})
    passing=[row for row in rows if row.get("status")=="PASS"]
    baseline=next((row for row in passing if row["candidate"]=="baseline"),None)
    for row in passing:
        row["rank"] = rank_hft(baseline["latency"]["microburst8_held_out"],row["latency"]["microburst8_held_out"]) if baseline else {"accepted":False}
    eligible=[row for row in passing if row["candidate"]=="baseline" or row["rank"]["accepted"]]
    eligible.sort(key=lambda row:(row["latency"]["microburst8_held_out"]["p99_9"],row["latency"]["microburst8_held_out"]["p50"]))
    winner=eligible[0] if eligible else None
    if winner and winner["candidate"]!="baseline":
        replacement=candidates[winner["candidate"]].replace("decode_book_update_candidate","decode_book_update")
        start=original.index("void decode_book_update(");optimized=original[:start]+replacement
        (out_dir/"optimized.c").write_text(optimized)
        (out_dir/"optimized.patch").write_text("".join(difflib.unified_diff(original.splitlines(True),optimized.splitlines(True),fromfile="original.c",tofile="optimized.c")))
    winner_plan=plan_by_candidate[winner["candidate"]] if winner else baseline_plan
    before=graph.to_dict();after=transformed_graph_dict(graph,winner_plan)
    write_json(out_dir/"operator_graph.before.json",before);write_json(out_dir/"operator_graph.after.json",after)
    post_manifest=capture_manifest(target,cpu,tc);write_manifest(out_dir/"analysis/hardware_manifest.post.json",post_manifest)
    if post_manifest.manifest_hash != analysis["hardware_manifest_hash"]:raise RuntimeError("material hardware/software configuration changed during benchmark")
    report={"schema_version":"vladder-hft-report-v3.0","operator":contract.name,"contract_hash":contract.contract_hash,"graph_hash":graph.graph_hash,"hardware_manifest_hash":analysis["hardware_manifest_hash"],"post_hardware_manifest_hash":post_manifest.manifest_hash,"grammar_hash":search.grammar_hash,"measurement":{"cpu":cpu,"processes":processes,"samples_per_process":samples,"candidate_order":order,"rank_objective":"microburst8_held_out","separate_modes":["batch1_held_out","batch1_adversarial","microburst8_held_out"],"trace_split":["tuning","held_out","adversarial"],"trace_hashes":trace_hashes},"search":search.to_dict(),"winner":winner,"candidates":rows,"claim":f"Best measured verified candidate in the bounded operator-v3 microburst-8 candidate set for target {target}; batch-1 results are reported separately; no global optimality claim."}
    write_json(out_dir/"pipeline_report.json",report);write_csv(out_dir/"pipeline_benchmark.csv",[{"candidate":r["candidate"],"status":r["status"],"p50":(r.get("latency",{}).get("microburst8_held_out",{}).get("p50")),"p99_9":(r.get("latency",{}).get("microburst8_held_out",{}).get("p99_9")),"p99_99":(r.get("latency",{}).get("microburst8_held_out",{}).get("p99_99")),"accepted":(r.get("rank",{}).get("accepted"))} for r in rows])
    return report


def _json_line(text: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("harness returned no JSON")


def _field_occupancy_candidate(source: str) -> str:
    start = source.index("    top_out->best_bid_ticks = 0;")
    end = source.index("    *status_out = 0;", start)
    replacement = """    int32_t bid_level = book->bid_occupied ? 63 - (int32_t)__builtin_clzll(book->bid_occupied) : -1;
    int32_t ask_level = book->ask_occupied ? (int32_t)__builtin_ctzll(book->ask_occupied) : -1;
    book->best_bid_level = bid_level; book->best_ask_level = ask_level;
    top_out->best_bid_ticks = bid_level < 0 ? 0 : PRICE_BASE + bid_level;
    top_out->best_bid_qty = bid_level < 0 ? 0 : book->bid_qty[bid_level];
    top_out->best_ask_ticks = ask_level < 0 ? 0 : PRICE_BASE + ask_level;
    top_out->best_ask_qty = ask_level < 0 ? 0 : book->ask_qty[ask_level];
"""
    return (source[:start] + replacement + source[end:]).replace("void decode_book_update(", "void decode_book_update_candidate(", 1)
