import { ArrowDownToLine, BookOpen, Check, Code2, Cpu, LockKeyhole, MessageSquareText, Route, Workflow } from "lucide-react";
import { CopyCommand } from "../components/copy-command";

const github = "https://github.com/araujota/vladder";
const install = "python3 -m pip install --pre vladder==1.0.0rc18";

type Review = {
  review_id: string;
  project: { name: string; revision: string };
  assessment: { rating: number; outcome: string; claim: string };
  evidence: { proof_class: string };
};

async function approvedReviews(): Promise<Review[]> {
  const endpoint = process.env.NEXT_PUBLIC_REVIEW_LIST_URL;
  if (!endpoint) return [];
  try {
    const response = await fetch(`${endpoint}?limit=3`, { next: { revalidate: 300 } });
    if (!response.ok) return [];
    const payload = (await response.json()) as { reviews?: Review[] };
    return payload.reviews ?? [];
  } catch {
    return [];
  }
}

const support = [
  ["C", "Direct extraction and source regeneration for supported bounded regions"],
  ["C++", "Local region extraction plus generated proof units around ownership boundaries"],
  ["Rust", "Borrowed, monomorphic hot regions lowered into the shared model"],
  ["Zig / Julia", "Native bounded regions with explicit runtime and ABI assumptions"],
  ["GPU", "SPIR-V and PTX evidence with separate host-protocol verification"],
];

const workflow = [
  ["01", "Profile", "Find a function or data path that matters in the real workload"],
  ["02", "Extract", "Translate its observable behavior into a language-neutral information-flow graph"],
  ["03", "Search", "Generate bounded alternatives for computation, movement, layout, and lifetime"],
  ["04", "Regenerate", "Turn legal candidate graphs back into readable, reviewable source code"],
  ["05", "Verify", "Check semantic parity, then benchmark original and candidate on the target hardware"],
  ["06", "Decide", "Keep the patch only when both correctness and representative performance hold"],
];

const plainFlow = [
  ["1", "You provide", "A profiled source region, its real build command, and a representative benchmark"],
  ["2", "vLadder models", "The values produced, dependencies, memory traffic, state changes, and valid lifetimes"],
  ["3", "vLadder searches", "A finite grammar of equivalent loops, layouts, schedules, fusion, packing, and reuse"],
  ["4", "Tools verify", "Z3, Alive2, differential tests, and protocol checks cover their declared boundaries"],
  ["5", "Hardware decides", "You get a reviewable patch with evidence, or a recorded rejection when it does not win"],
];

export default async function Home() {
  const reviews = await approvedReviews();
  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="vLadder home">vLadder</a>
        <nav aria-label="Primary navigation">
          <a href="#what">What it does</a>
          <a href="#example">Example</a>
          <a href="#workflow">Workflow</a>
          <a href="#support">Support</a>
          <a href={`${github}/tree/main/docs`}><BookOpen size={17} />Docs</a>
          <a href={`${github}/discussions`}><MessageSquareText size={17} />Community</a>
          <a href={github}><Code2 size={17} />GitHub</a>
        </nav>
      </header>

      <section className="intro" id="top">
        <div className="intro-copy">
          <p className="eyebrow">Verified superoptimization for systems software</p>
          <h1>vLadder</h1>
          <p className="lede">vLadder rewrites performance-critical systems code into a faster source implementation, then proves and benchmarks the result before you keep it.</p>
          <p className="intro-detail">Point it at a measured C, C++, Rust, Zig, Julia, or GPU hot path. vLadder extracts what the code must do into a shared information-flow graph, searches a bounded set of equivalent implementations, and regenerates the best candidates as readable source.</p>
          <p className="audience-note"><strong>It complements rather than replaces your compiler.</strong> vLadder chooses the computation and dataflow that should exist; Clang, LLVM, or your normal toolchain still generates machine code. Engineers can drive the CLI directly. Coding agents get the same fail-closed workflow through the included <code>SKILL.md</code>.</p>
          <div className="actions">
            <a className="primary-action" href={`${github}/releases`}><ArrowDownToLine size={19} />Get vLadder</a>
            <a className="secondary-action" href="#workflow"><Route size={19} />See how it works</a>
          </div>
          <CopyCommand command={install} />
        </div>
        <div className="release-status" aria-label="An optimization run at a glance">
          <div className="status-heading"><Workflow size={22} /><span>One optimization run</span></div>
          <dl>
            <div><dt>Input</dt><dd>A hot source region, exact compiler settings, semantic contract, and benchmark</dd></div>
            <div><dt>Translate</dt><dd>Source and compiled IR become a graph of computation, memory, state, and lifetime</dd></div>
            <div><dt>Optimize</dt><dd>The grammar changes how information is computed, moved, represented, reused, or eliminated</dd></div>
            <div><dt>Check</dt><dd>Formal and differential verification reject behavior changes; paired measurements reject slow code</dd></div>
            <div><dt>Output</dt><dd><Check size={16} />A source patch with proof and benchmark evidence, or a precise rejection</dd></div>
          </dl>
          <p><strong>“Workflow completed” does not mean “optimization accepted.”</strong> Capture, candidate generation, proof, benchmark win, and production promotion remain separate reported outcomes.</p>
        </div>
      </section>

      <section className="plain-flow-section" aria-labelledby="plain-flow-title">
        <div className="section-inner">
          <div className="plain-flow-heading">
            <p className="eyebrow">What it actually does</p>
            <h2 id="plain-flow-title">Keep the behavior fixed. Search how the work is physically realized.</h2>
          </div>
          <ol className="plain-flow">
            {plainFlow.map(([number, label, detail]) => (
              <li key={number}>
                <span>{number}</span>
                <div><strong>{label}</strong><small>{detail}</small></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="capability-section" id="what">
        <div className="section-inner">
          <div className="section-heading capability-heading">
            <div>
              <p className="eyebrow">What makes it different</p>
              <h2>It changes choices a normal compiler usually treats as fixed</h2>
            </div>
            <p>A profiler identifies expensive code. A compiler improves the code shape you supplied. vLadder works between them: it searches for a different source-level way to produce the same observable result, then sends each candidate through your compiler and measures the result.</p>
          </div>
          <div className="capability-list">
            <article><span>01</span><h3>Compute it another way</h3><p>Change a loop, reduction, codec, branch, mask, scan, compaction pipeline, or fixed-width kernel while preserving its contract.</p></article>
            <article><span>02</span><h3>Move and store less</h3><p>Fuse stages, change traversal or layout, stream directly to a consumer, or remove an unnecessary temporary and copy.</p></article>
            <article><span>03</span><h3>Realize data at the right lifetime</h3><p>Compute once and reuse while valid, invalidate at the real mutation boundary, retire after final use, or never materialize it.</p></article>
          </div>
        </div>
      </section>

      <section className="audience-section">
        <div className="section-inner audience-grid">
          <div className="audience-heading">
            <p className="eyebrow">Who it is for</p>
            <h2>A performance workflow humans and agents can both audit</h2>
          </div>
          <div className="audience-lanes">
            <article>
              <Cpu size={24} />
              <div><h3>For systems engineers</h3><p>Use vLadder as a local CLI and evidence pipeline. Inspect every assumption, candidate, proof boundary, counterexample, confidence interval, and final source diff.</p></div>
            </article>
            <article>
              <Code2 size={24} />
              <div><h3>For coding agents</h3><p>Install the vLadder skill and give the agent a target workload. The skill drives profiling, extraction, search, proof, benchmarking, source realization, and honest reporting through explicit gates.</p></div>
            </article>
          </div>
        </div>
      </section>

      <section className="example-section" id="example">
        <div className="section-inner example-grid">
          <div className="example-copy">
            <p className="eyebrow">A concrete example</p>
            <h2>Stop rebuilding information that has not changed</h2>
            <p>Suppose a network record is split into eight packets. The original code validates and serializes the same record body for every packet. The body is identical until the record changes.</p>
            <p>vLadder can model that validity interval, propose one record-lifetime realization, generate the ownership and invalidation obligations, and measure the complete packet path rather than only the serialization helper.</p>
          </div>
          <div className="example-flow" aria-label="Repeated per-fragment serialization changed to one record-lifetime serialization">
            <div>
              <span>Before</span>
              <code>8 fragments × (validate + serialize + emit)</code>
              <small>The same information is rebuilt eight times.</small>
            </div>
            <Route size={24} />
            <div>
              <span>Candidate</span>
              <code>validate once → serialize once → emit 8 fragments</code>
              <small>Reuse remains legal only until record mutation.</small>
            </div>
          </div>
        </div>
      </section>

      <section className="flow-band" id="workflow">
        <div className="section-inner">
          <div className="section-heading">
            <p className="eyebrow">How it works</p>
            <h2>Source → information flow → candidate source → proof → hardware</h2>
            <p className="section-intro">The semantic graph is the stable middle layer. Frontends describe what each supported region means; the grammar changes its physical realization; emitters rebuild source; proof tools and the real machine decide whether it can ship.</p>
          </div>
          <div className="flow-visual" role="img" aria-label="Source through semantic flow, grammar search, proof, hardware, and source rewrite">
            {workflow.map(([number, label, detail], index) => (
              <div className="flow-step" key={number}>
                <span>{number}</span><strong>{label}</strong><small>{detail}</small>{index < 5 && <Route className="flow-arrow" size={19} />}
              </div>
            ))}
          </div>
          <p className="boundary-note"><strong>Fail closed:</strong> “inspected,” “candidate generated,” “proved,” “benchmark win,” and “source patch retained” are separate outcomes. vLadder reports the highest level actually reached.</p>
        </div>
      </section>

      <section className="support-section" id="support">
        <div className="section-inner support-grid">
          <div>
            <p className="eyebrow">Languages and boundaries</p>
            <h2>Automatic where bounded. Explicit where the system boundary matters.</h2>
            <p>Supported language frontends converge on one information-flow vocabulary. vLadder can directly extract, transform, regenerate, and prove supported bounded regions. Ownership-heavy application code, exceptions, drivers, concurrency, and external protocols use generated proof units plus explicit adapters and application-level checks. Those boundaries remain named in the report, never silently treated as proved.</p>
          </div>
          <div className="support-list">
            {support.map(([name, detail]) => <div key={name}><strong>{name}</strong><span>{detail}</span></div>)}
          </div>
        </div>
      </section>

      <section className="privacy-section">
        <div className="section-inner privacy-grid">
          <LockKeyhole size={34} />
          <div>
            <p className="eyebrow">Privacy posture</p>
            <h2>Your code stays local</h2>
            <p>Optimization commands do not upload source, traces, proofs, or measurements. Optional source-free contributions require independent durable opt-in, schema validation, and explicit record and command consent.</p>
          </div>
          <a href={`${github}/blob/main/docs/privacy.md`}>Read the policy</a>
        </div>
      </section>

      {reviews.length > 0 && (
        <section className="reviews-section">
          <div className="section-inner">
            <div className="section-heading"><p className="eyebrow">Approved agent reviews</p><h2>Evidence-bound field reports</h2></div>
            <div className="review-list">
              {reviews.map((review) => (
                <article key={review.review_id}>
                  <div><strong>{review.project.name}</strong><span>{review.assessment.rating.toFixed(1)} / 10</span></div>
                  <p>{review.assessment.claim}</p>
                  <small>{review.evidence.proof_class} · {review.assessment.outcome}</small>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}

      <footer>
        <span>vLadder · MIT licensed</span>
        <div><a href={`${github}/discussions`}>Community</a><a href={`${github}/blob/main/ROADMAP.md`}>Roadmap</a><a href={`${github}/blob/main/CONTRIBUTING.md`}>Contribute</a><a href={`${github}/releases`}>Downloads</a></div>
      </footer>
    </main>
  );
}
