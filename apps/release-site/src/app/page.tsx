import { ArrowDownToLine, BookOpen, Check, Code2, LockKeyhole, MessageSquareText, Route, ShieldCheck } from "lucide-react";
import { CopyCommand } from "../components/copy-command";

const github = "https://github.com/araujota/vladder";
const install = "python3 -m pip install --pre vladder==1.0.0rc16";

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
  ["01", "Capture", "Source, build flags, inputs, outputs, and observable behavior"],
  ["02", "Model", "Values, dependencies, state, placement, and valid lifetimes"],
  ["03", "Search", "Equivalent loops, layouts, fusion, compaction, reuse, and schedules"],
  ["04", "Verify", "Z3 and Alive2 where applicable, plus differential and stateful tests"],
  ["05", "Measure", "Paired candidates in the real executable on the target hardware"],
  ["06", "Rewrite", "A reviewable source patch only when proof and performance gates pass"],
];

export default async function Home() {
  const reviews = await approvedReviews();
  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="vLadder home">vLadder</a>
        <nav aria-label="Primary navigation">
          <a href="#what">What it does</a>
          <a href="#workflow">Workflow</a>
          <a href="#support">Support</a>
          <a href={`${github}/tree/main/docs`}><BookOpen size={17} />Docs</a>
          <a href={`${github}/discussions`}><MessageSquareText size={17} />Community</a>
          <a href={github}><Code2 size={17} />GitHub</a>
        </nav>
      </header>

      <section className="intro" id="top">
        <div className="intro-copy">
          <p className="eyebrow">Verified optimization for systems code</p>
          <h1>vLadder</h1>
          <p className="lede">Find a faster implementation without changing what the code means.</p>
          <p className="intro-detail">Point vLadder at a bounded hot path. It models the path as information flow, searches equivalent computation, layout, and data-lifetime choices, proves candidates, and measures them on your hardware. You get a source-level rewrite with the evidence needed to accept or reject it.</p>
          <p className="audience-note"><strong>For systems engineers:</strong> use the CLI. <strong>For coding agents:</strong> install the included <code>SKILL.md</code> workflow.</p>
          <div className="actions">
            <a className="primary-action" href={`${github}/releases`}><ArrowDownToLine size={19} />Get vLadder</a>
            <a className="secondary-action" href="#workflow"><Route size={19} />See how it works</a>
          </div>
          <CopyCommand command={install} />
        </div>
        <div className="release-status" aria-label="vLadder outputs">
          <div className="status-heading"><ShieldCheck size={22} /><span>What you get</span></div>
          <dl>
            <div><dt>Candidate</dt><dd><Check size={16} />Reviewable source patch</dd></div>
            <div><dt>Correctness</dt><dd><Check size={16} />Proof and parity report</dd></div>
            <div><dt>Performance</dt><dd><Check size={16} />Paired hardware result</dd></div>
            <div><dt>Decision</dt><dd><Check size={16} />Promote or reject</dd></div>
          </dl>
          <p>vLadder is not a replacement compiler. It chooses a better verified implementation graph; your existing compiler still generates the machine code.</p>
        </div>
      </section>

      <section className="capability-section" id="what">
        <div className="section-inner">
          <div className="section-heading capability-heading">
            <div>
              <p className="eyebrow">What it optimizes</p>
              <h2>More than instruction order</h2>
            </div>
            <p>vLadder asks which concrete realization of the required behavior should exist before LLVM or another compiler decides how to encode it.</p>
          </div>
          <div className="capability-list">
            <article><span>01</span><h3>Computation</h3><p>Expressions, loops, reductions, packing, codecs, masks, and stable compaction.</p></article>
            <article><span>02</span><h3>Information flow</h3><p>Fusion, traversal, data layout, intermediate materialization, and CPU/GPU placement.</p></article>
            <article><span>03</span><h3>Information lifetime</h3><p>Derive once, reuse while valid, invalidate exactly, or eliminate a representation entirely.</p></article>
          </div>
        </div>
      </section>

      <section className="flow-band" id="workflow">
        <div className="section-inner">
          <div className="section-heading">
            <p className="eyebrow">How it works</p>
            <h2>Model meaning first. Optimize realization second.</h2>
            <p className="section-intro">The workflow keeps semantic capture, candidate generation, proof, physical measurement, and source promotion separate, so a fast microbenchmark cannot masquerade as a production win.</p>
          </div>
          <div className="flow-visual" role="img" aria-label="Source through semantic flow, grammar search, proof, hardware, and source rewrite">
            {workflow.map(([number, label, detail], index) => (
              <div className="flow-step" key={number}>
                <span>{number}</span><strong>{label}</strong><small>{detail}</small>{index < 5 && <Route className="flow-arrow" size={19} />}
              </div>
            ))}
          </div>
          <p className="boundary-note"><strong>Fail closed:</strong> inspected, generated, proved, benchmarked, and retained are different states. vLadder reports each one explicitly.</p>
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
