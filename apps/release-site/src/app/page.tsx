import { ArrowDownToLine, BookOpen, Check, Code2, LockKeyhole, MessageSquareText, Route, ShieldCheck } from "lucide-react";
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
  ["01", "Find the cost", "Profile the real workload and select a load-bearing region"],
  ["02", "Capture meaning", "Record inputs, outputs, side effects, state, and valid lifetimes"],
  ["03", "Search alternatives", "Explore bounded equivalent computations, layouts, and lifetimes"],
  ["04", "Prove parity", "Use Z3, Alive2, differential tests, and protocol checks as applicable"],
  ["05", "Measure together", "Run baseline and candidate in the same executable and environment"],
  ["06", "Promote or reject", "Emit a source patch only when correctness and performance both hold"],
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
          <p className="eyebrow">A local superoptimizer for systems code</p>
          <h1>vLadder</h1>
          <p className="lede">Turn a measured hot path into a faster, verified source implementation.</p>
          <p className="intro-detail">vLadder analyzes how information is computed, moved, stored, and reused across a bounded C, C++, Rust, Zig, Julia, or GPU region. It searches a finite grammar of equivalent implementations, regenerates source, checks semantic parity, and benchmarks the candidate against the original on your hardware.</p>
          <p className="audience-note"><strong>You keep the compiler.</strong> vLadder changes the implementation you give it. Clang, LLVM, or your existing toolchain still lowers the accepted source to machine code. Coding agents can run the same proof-gated process through the included <code>SKILL.md</code>.</p>
          <div className="actions">
            <a className="primary-action" href={`${github}/releases`}><ArrowDownToLine size={19} />Get vLadder</a>
            <a className="secondary-action" href="#workflow"><Route size={19} />See how it works</a>
          </div>
          <CopyCommand command={install} />
        </div>
        <div className="release-status" aria-label="A vLadder optimization run">
          <div className="status-heading"><ShieldCheck size={22} /><span>A vLadder run</span></div>
          <dl>
            <div><dt>You provide</dt><dd>A profiled region, its build configuration, and a representative workload</dd></div>
            <div><dt>It searches</dt><dd>Equivalent code, dataflow, layout, schedule, placement, and lifetime choices</dd></div>
            <div><dt>It checks</dt><dd>Formal proof where tractable, behavioral parity, and paired hardware performance</dd></div>
            <div><dt>You receive</dt><dd><Check size={16} />A patch and evidence, or an explicit rejection with the reason</dd></div>
          </dl>
          <p><strong>No speedup is still a result.</strong> Candidates that fail proof, lose in the real workload, or cross an unmodeled system boundary are not promoted.</p>
        </div>
      </section>

      <section className="capability-section" id="what">
        <div className="section-inner">
          <div className="section-heading capability-heading">
            <div>
              <p className="eyebrow">The missing layer</p>
              <h2>Choose better code before compiling it</h2>
            </div>
            <p>A profiler tells you where time went. A compiler optimizes the implementation you wrote. vLadder searches for a different implementation with the same declared behavior, then proves and measures whether it is actually better.</p>
          </div>
          <div className="capability-list">
            <article><span>01</span><h3>Compute it differently</h3><p>Rewrite expressions, loops, reductions, packing, codecs, masks, and stable compaction.</p></article>
            <article><span>02</span><h3>Move less information</h3><p>Fuse stages, change traversal or layout, stream outputs, and remove unnecessary CPU/GPU transfers.</p></article>
            <article><span>03</span><h3>Realize it at the right lifetime</h3><p>Derive once and reuse while valid, invalidate at the true boundary, or eliminate a temporary entirely.</p></article>
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
            <h2>From production source to an evidence-backed decision</h2>
            <p className="section-intro">The workflow keeps inspection, candidate generation, proof, measurement, and promotion separate. A generated candidate is not called an optimization until it preserves the contract and improves the representative workload.</p>
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
            <h2>One semantic model, honest proof limits</h2>
            <p>Supported language frontends converge on the same information-flow graph. Bounded local computation can be transformed directly. Ownership, exceptions, drivers, concurrency, and external protocols receive explicit adapters or remain named boundaries rather than being treated as proved.</p>
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
