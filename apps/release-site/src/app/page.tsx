import { ArrowDownToLine, BookOpen, Check, Code2, Cpu, LockKeyhole, MessageSquareText, Route, Workflow } from "lucide-react";
import { CopyCommand } from "../components/copy-command";

const github = "https://github.com/araujota/vladder";
const install = "python3 -m pip install --pre vladder==1.0.0rc30";

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
  ["01", "Find the cost", "Profile the real workload and select a function or data path that matters"],
  ["02", "Capture behavior", "Record its outputs, memory effects, state, ordering, and valid assumptions"],
  ["03", "Search unique states", "Collapse redundant transformation orders, then try bounded alternatives for computation, movement, layout, and data lifetime"],
  ["04", "Rebuild source", "Emit legal candidate graphs as readable C, C++, Rust, Zig, or Julia code"],
  ["05", "Prove and measure", "Check the covered semantics, then benchmark in the real build on the target hardware"],
  ["06", "Keep or reject", "Retain the patch only when correctness and representative performance both hold"],
];

const toolchainPosition = [
  ["1", "Profiler", "Finds code consuming meaningful time, bandwidth, memory, or synchronization"],
  ["2", "vLadder", "Searches for a different implementation of the same required behavior"],
  ["3", "Production toolchain", "Builds every candidate with the real flags, dependencies, and target ISA"],
  ["4", "Proof + benchmark", "Rejects semantic changes and speedups that disappear in the real workload"],
];

const runContract = [
  ["You provide", "Hot code + correctness contract + benchmark", "The real build command, a measured source region, the behavior that must not change, and a workload that represents production."],
  ["vLadder does", "Extract → search → regenerate → verify", "It models the region's information flow, searches a finite implementation grammar, emits candidate source, and runs the strongest applicable proof and test stack."],
  ["You receive", "A faster verified patch, or an auditable rejection", "The result includes source, assumptions, proof coverage, counterexamples, benchmark confidence, unresolved boundaries, and a keep-or-reject disposition."],
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
          <p className="eyebrow">Verified source-to-source optimization for systems code</p>
          <h1>vLadder</h1>
          <p className="lede">vLadder turns measured hot code into faster, reviewable source without treating correctness as a guess.</p>
          <p className="intro-detail">Give it a bounded C, C++, Rust, Zig, Julia, or GPU region, the behavior that must stay unchanged, and a representative benchmark. It searches unique semantic realizations, rebuilds the best candidates as source, checks semantic parity, and measures them on your hardware.</p>
          <p className="audience-note"><strong>It is a local CLI and coding-agent workflow, not a replacement compiler.</strong> Profilers find where the cost is. vLadder searches what implementation should exist. Your production compiler still generates the executable.</p>
          <div className="actions">
            <a className="primary-action" href={`${github}/releases`}><ArrowDownToLine size={19} />Get vLadder</a>
            <a className="secondary-action" href="#workflow"><Route size={19} />Follow one run</a>
          </div>
        </div>
        <div className="release-status" role="group" aria-label="Example of a vLadder information-flow rewrite">
          <div className="status-heading"><Workflow size={22} /><span>What vLadder changes</span></div>
          <div className="hero-rewrite">
            <div>
              <span>Current source: two passes + temporary</span>
              <pre><code>{`for (i = 0; i < n; ++i)
  decoded[i] = decode(src[i]);

for (i = 0; i < n; ++i)
  sum += decoded[i];`}</code></pre>
            </div>
            <Route size={19} aria-hidden="true" />
            <div>
              <span>Generated candidate: one streaming pass</span>
              <pre><code>{`for (i = 0; i < n; ++i)
  sum += decode(src[i]);`}</code></pre>
            </div>
          </div>
          <p className="rewrite-explanation">Both versions must produce the same required <code>sum</code>. The candidate removes a temporary buffer, one traversal, and the associated memory traffic. vLadder checks whether this is legal for the real aliases, side effects, numeric rules, and callers.</p>
          <div className="run-output">
            <span>Promotion rule</span>
            <strong><Check size={17} />Same required behavior, measurably faster where it matters</strong>
            <small>Canonical identity and qualified exact reductions remove redundant search work. ML may reorder exploration, never delete a semantic possibility. If proof or performance fails, the source stays unchanged.</small>
          </div>
        </div>
      </section>

      <section className="plain-flow-section" aria-labelledby="plain-flow-title">
        <div className="section-inner">
          <div className="plain-flow-heading">
            <p className="eyebrow">Where it fits</p>
            <div>
              <h2 id="plain-flow-title">A search layer between profiling and compilation</h2>
              <p>A compiler improves the implementation you wrote. vLadder searches other implementations you could have written: fewer passes, different reductions, compacted output, retained derived state, direct CPU/GPU placement, or no intermediate at all. The declared behavior remains the boundary.</p>
            </div>
          </div>
          <div className="where-install">
            <span>Install the release candidate</span>
            <CopyCommand command={install} />
          </div>
          <ol className="plain-flow">
            {toolchainPosition.map(([number, label, detail]) => (
              <li key={number}>
                <span>{number}</span>
                <div><strong>{label}</strong><small>{detail}</small></div>
              </li>
            ))}
          </ol>
          <div className="run-contract" aria-label="What a vLadder run requires and produces">
            {runContract.map(([label, title, detail]) => (
              <div className="contract-step" key={label}>
                <span>{label}</span>
                <strong>{title}</strong>
                <p>{detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="capability-section" id="what">
        <div className="section-inner">
          <div className="section-heading capability-heading">
            <div>
              <p className="eyebrow">The core idea</p>
              <h2>Preserve what the program means. Search how the work is realized.</h2>
            </div>
            <p>vLadder represents where outputs come from, what memory and state are observable, what ordering is required, and how long each derived value remains valid. That information-flow graph separates the required semantics from one particular source implementation.</p>
          </div>
          <div className="capability-list">
            <article><span>01</span><h3>Compute differently</h3><p>Fuse loops, change a reduction tree, turn predicates into masks and compacted output, or specialize a proven bounded case.</p></article>
            <article><span>02</span><h3>Move and store less</h3><p>Traverse data once, write directly to a consumer, change a packed layout, retain a useful tile, or remove a copy.</p></article>
            <article><span>03</span><h3>Keep data for the right lifetime</h3><p>Derive information once and reuse it until invalidation, retire it after final use, move it nearer its consumer, or never materialize it.</p></article>
          </div>
        </div>
      </section>

      <section className="audience-section">
        <div className="section-inner audience-grid">
          <div className="audience-heading">
            <p className="eyebrow">Who it is for</p>
            <h2>The same evidence chain for engineers and coding agents</h2>
          </div>
          <div className="audience-lanes">
            <article>
              <Cpu size={24} />
              <div><h3>For systems engineers</h3><p>Point the local CLI at a profiled region, its real build command, and a representative workload. Inspect every assumption, candidate, proof boundary, confidence interval, and final source diff.</p></div>
            </article>
            <article>
              <Code2 size={24} />
              <div><h3>For coding agents</h3><p>The included <code>SKILL.md</code> is an executable runbook: inspect the real build, state the contract, run search and proof, build a paired benchmark, and report the highest evidence level actually reached.</p></div>
            </article>
          </div>
        </div>
      </section>

      <section className="example-section" id="example">
        <div className="section-inner example-grid">
          <div className="example-copy">
            <p className="eyebrow">Beyond local loops</p>
            <h2>It can also change when data is built and how long it lives</h2>
            <p>Suppose a network record is split into eight packets. The original code validates and serializes the same record body for every packet. The body is identical until the record changes.</p>
            <p>vLadder can model that validity interval, propose one record-lifetime realization, generate the ownership and invalidation obligations, and measure the complete packet path rather than only the serialization helper.</p>
          </div>
          <div className="example-flow" role="group" aria-label="Repeated per-fragment serialization changed to one record-lifetime serialization">
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
            <p className="eyebrow">The actual workflow</p>
            <h2>Production source → candidate source → defensible decision</h2>
            <p className="section-intro">Language frontends capture a bounded region in one shared semantic graph. Search operates on a quotient DAG of unique semantic states, so independent action orders converge before proof and compilation. Language emitters rebuild source. Proof tools establish the semantics they cover; application tests and the target machine establish whether the rewrite can ship.</p>
          </div>
          <div className="flow-visual" role="img" aria-label="Source through semantic flow, grammar search, proof, hardware, and source rewrite">
            {workflow.map(([number, label, detail], index) => (
              <div className="flow-step" key={number}>
                <span>{number}</span><strong>{label}</strong><small>{detail}</small>{index < 5 && <Route className="flow-arrow" size={19} />}
              </div>
            ))}
          </div>
          <p className="boundary-note"><strong>Five different outcomes:</strong> inspected, candidate generated, candidate proved, benchmark won, and source patch retained. A completed workflow is not automatically a successful optimization. vLadder reports the highest level actually reached.</p>
        </div>
      </section>

      <section className="support-section" id="support">
        <div className="section-inner support-grid">
          <div>
            <p className="eyebrow">Languages and boundaries</p>
            <h2>Automatic where semantics close. Explicit where they do not.</h2>
            <p>A bounded region has known inputs, outputs, memory bounds, side effects, and failure behavior. vLadder can directly extract, transform, regenerate, and prove supported regions. Ownership-heavy wrappers, drivers, concurrency, callbacks, and external protocols require explicit adapters and system-level oracles. The report never silently upgrades local proof into whole-application equivalence.</p>
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
            <h2>Your source stays local</h2>
            <p>Optimization commands do not upload source or raw artifacts. Optional model-training contribution sends bounded normalized graph topology, actions, and outcomes only after a separate informed opt-in. Before upload, the client verifies the service schema and route contract without storing a record. Submitted structural data removes source identifiers and literals, but remains pseudonymized because distinctive topology can fingerprint an algorithm.</p>
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
