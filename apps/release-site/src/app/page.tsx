import { ArrowDownToLine, BookOpen, Check, Code2, LockKeyhole, MessageSquareText, Route, ShieldCheck, Terminal } from "lucide-react";
import { CopyCommand } from "../components/copy-command";

const github = "https://github.com/araujota/vladder";
const install = "git clone https://github.com/araujota/vladder.git && cd vladder && ./scripts/install.sh";

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
  ["C", "Automatic bounded regions"],
  ["C++", "Compiled closure + proof units"],
  ["Rust", "Borrowed monomorphic regions"],
  ["Zig / Julia", "Native bounded adapters"],
  ["GPU", "SPIR-V / PTX + protocol evidence"],
];

export default async function Home() {
  const reviews = await approvedReviews();
  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="vLadder home">vLadder</a>
        <nav aria-label="Primary navigation">
          <a href="#workflow">Workflow</a>
          <a href="#support">Support</a>
          <a href={`${github}/tree/main/docs`}><BookOpen size={17} />Docs</a>
          <a href={`${github}/discussions`}><MessageSquareText size={17} />Community</a>
          <a href={github}><Code2 size={17} />GitHub</a>
        </nav>
      </header>

      <section className="intro" id="top">
        <div className="intro-copy">
          <p className="eyebrow">Velocity Ladder · Release candidate</p>
          <h1>vLadder</h1>
          <p className="lede">Select the verified information-flow graph that should exist, then let the compiler lower it.</p>
          <div className="actions">
            <a className="primary-action" href={`${github}/releases`}><ArrowDownToLine size={19} />Releases</a>
            <a className="secondary-action" href={`${github}#install`}><Terminal size={19} />Install guide</a>
          </div>
          <CopyCommand command={install} />
        </div>
        <div className="release-status" aria-label="Release evidence status">
          <div className="status-heading"><ShieldCheck size={22} /><span>Evidence chain</span></div>
          <dl>
            <div><dt>Semantic IR</dt><dd><Check size={16} />Shared v2 graph</dd></div>
            <div><dt>Proof gates</dt><dd><Check size={16} />Z3 + Alive2</dd></div>
            <div><dt>Physical oracle</dt><dd><Check size={16} />Paired hardware</dd></div>
            <div><dt>Privacy</dt><dd><LockKeyhole size={16} />Local by default</dd></div>
          </dl>
        </div>
      </section>

      <section className="flow-band" id="workflow">
        <div className="section-inner">
          <div className="section-heading">
            <p className="eyebrow">Actual optimization path</p>
            <h2>Evidence before promotion</h2>
          </div>
          <div className="flow-visual" role="img" aria-label="Source through semantic flow, grammar search, proof, hardware, and source rewrite">
            {[
              ["01", "Source + contract"],
              ["02", "Semantic flow"],
              ["03", "Bounded grammar"],
              ["04", "Proof gates"],
              ["05", "Hardware rank"],
              ["06", "Source rewrite"],
            ].map(([number, label], index) => (
              <div className="flow-step" key={number}>
                <span>{number}</span><strong>{label}</strong>{index < 5 && <Route className="flow-arrow" size={19} />}
              </div>
            ))}
          </div>
          <p className="boundary-note">A completed workflow is not automatically a proved or retained optimization. Every state is reported independently.</p>
        </div>
      </section>

      <section className="support-section" id="support">
        <div className="section-inner support-grid">
          <div>
            <p className="eyebrow">Supported boundaries</p>
            <h2>One vocabulary, explicit adapters</h2>
            <p>Frontends converge on the same information-flow model. Ownership, exceptions, drivers, and external protocols remain named proof boundaries when their state is absent.</p>
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
