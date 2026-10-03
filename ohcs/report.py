"""Build the static preliminary-results page from out/results.json + one sample .mfd."""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path

# Build the page from saved results; this module does not run extraction again.
ROOT = Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "out/results.json").read_text())
MFD = (ROOT / "out/medford/cbi-kleinrock-1990.mfd").read_text()
E = html.escape  # Display text safely when inserting it into HTML.

# Translate stored code names into readable labels for tables and filter buttons.
CODE_LABEL = {
    "first_encounter": "First encounter", "mentorship_lineage": "Mentors & lineage",
    "institution_building": "Building institutions", "funding_patronage": "Funding & patronage",
    "technical_breakthrough": "Technical breakthrough", "identity_belonging": "Identity & belonging",
    "profession_formation": "Becoming a profession", "teaching_students": "Teaching & students",
    "reflection_legacy": "Reflection & legacy", "serendipity": "Serendipity",
}
CODES = list(CODE_LABEL)
REL_LABEL = {"advisor_or_mentor": "mentor", "student_or_mentee": "student", "peer_colleague": "colleague",
             "funder_or_patron": "patron", "influence": "influence", "other": "other"}

src_by_id = {s["id"]: s for s in R["sources"]}  # Look up source details by passage source ID.

# The heatmap uses reference labels, not the stub's predicted themes.
per_src = defaultdict(Counter)
for p in R["passages"]:
    for c in p["gold"]:
        per_src[p["source_id"]][c] += 1


def heat_table() -> str:
    # Make one table row per source and one column per theme.
    rows = []
    mx = max(v for c in per_src.values() for v in c.values())
    head = "".join(f'<th scope="col"><span>{E(CODE_LABEL[c])}</span></th>' for c in CODES)
    for s in R["sources"]:
        cells = []
        for c in CODES:
            v = per_src[s["id"]][c]
            lvl = 0 if v == 0 else min(4, 1 + round(3 * v / mx))  # Larger counts get darker cells.
            cells.append(f'<td class="h{lvl}" title="{E(CODE_LABEL[c])}: {v}">{v or ""}</td>')
        yr = s["date"][:4]
        rows.append(f'<tr><th scope="row">{E(s["narrator"])} <small>{yr}</small></th>{"".join(cells)}</tr>')
    return f'<div class="scroll"><table class="heat"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def sources_table() -> str:
    # Show source citations beside any matching faculty-frame information.
    rows = []
    for s in R["sources"]:
        d = s.get("_drafty")
        drafty = "not in frame" if not d else f'{E(d["university"])} · {d["join_year"]}'
        flag = ""
        # Highlight disagreements instead of silently replacing either affiliation.
        if d and s.get("affiliation") and d["university"] != s["affiliation"]:
            flag = f' <span class="pill warn">conflict: source says {E(s["affiliation"])}</span>'
        rows.append(
            f'<tr><td>{E(s["narrator"])}</td><td>{E(s.get("interviewer") or "(self-written)")}</td>'
            f'<td class="num">{E(s["date"])}</td><td><a href="{E(s["uri"])}" target="_blank" rel="noopener">{E(s["repository"])}</a>'
            f'<br><small>{E(s.get("catalog") or "")}</small></td><td class="num">{s["n_excerpts"]}</td>'
            f'<td>{drafty}{flag}</td></tr>')
    return ('<div class="scroll"><table class="data"><thead><tr><th>Narrator</th><th>Interviewer</th><th>Date</th>'
            '<th>Repository</th><th>Excerpts</th><th>Drafty frame row</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def lineage() -> str:
    # Group mentioned people under the narrator who talked about them.
    by = defaultdict(list)
    for l in R["lineage"]:
        by[l["narrator"]].append(l)
    out = []
    for n, ls in by.items():
        items = ""
        for l in ls:
            # Display the reference relationship and note when the stub disagreed.
            ref = REL_LABEL.get(l["reference"] or "other")
            miss = "" if l["relation"] == l["reference"] else f'<span class="miss">stub said {REL_LABEL[l["relation"]]}</span>'
            items += f'<li><b>{E(l["person"])}</b> <span class="rel">{ref}</span>{miss}</li>'
        out.append(f'<div class="lin"><h4>{E(n)}</h4><ul>{items}</ul></div>')
    return '<div class="lingrid">' + "".join(out) + "</div>"


def agreement_rows() -> str:
    # Format the saved per-theme precision, recall, and F1 values as table rows.
    a = R["agreement_vs_reference"]["per_code"]
    return "".join(
        f'<tr><td>{E(CODE_LABEL[c])}</td><td class="num">{a[c]["support"]}</td><td class="num">{a[c]["precision"]:.2f}</td>'
        f'<td class="num">{a[c]["recall"]:.2f}</td><td class="num">{a[c]["f1"]:.2f}</td></tr>' for c in CODES)


# Count relationship matches for the report's comparison with reference labels.
rel_ok = sum(l["relation"] == l["reference"] for l in R["lineage"])
rel_n = len(R["lineage"])
# Embed passage data as JSON so the browser can filter without a server request.
# The JavaScript filter uses "g" (reference themes); "m" holds model predictions.
passages_js = json.dumps([{
    "n": p["narrator"], "s": p["source_id"], "y": src_by_id[p["source_id"]]["date"][:4], "t": p["text"],
    "pg": p["page"], "yr": p["years"], "g": p["gold"], "m": sorted(p["accepted_themes"]), "r": p["route"]}
    for p in R["passages"]], ensure_ascii=False)
# Each button carries the code that the browser adds to its active filter set.
chips = "".join(f'<button type="button" class="chip" data-code="{c}" id="chip-{c}">{E(CODE_LABEL[c])}</button>' for c in CODES)
frame = R["frame"]
susp = ", ".join(f'{E(f["name"])} ({f["join_year"]})' for f in frame["suspicious_join_years"])
agg = R["agreement_vs_reference"]

# Assemble the page: CSS styles first, report sections next, and filter JavaScript last.
# Doubled braces keep CSS/JavaScript braces literal inside this Python f-string.
# The browser shows passages matching every selected theme and updates the count.
page = f"""<title>Oral History of CS</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:ital,opsz,wght@1,8..60,400;1,8..60,500&display=swap">
<style>
:root{{--bg:#F2F4F6;--surface:#FFFFFF;--ink:#16202B;--muted:#56626F;--line:#D5DBE1;--accent:#0E6A73;--accent-soft:#D6ECEE;
--warn:#9A6212;--warn-soft:#F6E9D3;--h1:#E3F0F1;--h2:#B9DDE0;--h3:#7FC0C6;--h4:#2F8C95;--h4ink:#FFFFFF;
--display:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;--body:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;--voice:"Source Serif 4",Georgia,serif}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--bg:#0F151B;--surface:#17202A;--ink:#E2E8EE;--muted:#98A5B2;--line:#2A3642;
--accent:#5CC0C9;--accent-soft:#16363A;--warn:#E3A652;--warn-soft:#3A2C17;--h1:#16302F;--h2:#1D4A4D;--h3:#27707A;--h4:#4FB2BB;--h4ink:#0F151B}}}}
:root[data-theme="dark"]{{color-scheme:dark;--bg:#0F151B;--surface:#17202A;--ink:#E2E8EE;--muted:#98A5B2;--line:#2A3642;
--accent:#5CC0C9;--accent-soft:#16363A;--warn:#E3A652;--warn-soft:#3A2C17;--h1:#16302F;--h2:#1D4A4D;--h3:#27707A;--h4:#4FB2BB;--h4ink:#0F151B}}
body{{background:var(--bg);color:var(--ink);font:15px/1.6 var(--body);padding-inline:20px;padding-block:0 64px}}
main{{max-width:960px;margin:0 auto;display:grid;gap:56px}}
header{{padding-top:48px;display:grid;gap:14px;max-width:760px}}
.eyebrow{{font:500 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}}
h1{{font:600 clamp(34px,6vw,52px)/1.05 var(--display);letter-spacing:-.01em;margin:0;text-wrap:balance}}
h2{{font:600 26px/1.15 var(--display);margin:0 0 6px;text-wrap:balance}}
h3{{font:600 17px/1.3 var(--body);margin:0}}
h4{{font:600 15px/1.3 var(--display);margin:0 0 6px}}
p{{margin:0;max-width:68ch}}
.lede{{font-size:17px;color:var(--muted)}}
section{{display:grid;gap:16px}}
a{{color:var(--accent)}}
a:focus-visible,button:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.facts{{display:flex;flex-wrap:wrap;gap:8px 28px;font:13px/1.4 var(--mono);color:var(--muted)}}
.facts b{{color:var(--ink);font-weight:500}}
.notice{{background:var(--warn-soft);border-left:3px solid var(--warn);padding:12px 16px;max-width:760px}}
.notice p{{max-width:none}}
.flow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;counter-reset:s}}
.step{{background:var(--surface);border:1px solid var(--line);padding:12px 14px;display:grid;gap:4px;align-content:start}}
.step::before{{counter-increment:s;content:"stage " counter(s);font:500 11px/1 var(--mono);color:var(--accent);letter-spacing:.06em;text-transform:uppercase}}
.step p{{font-size:13px;color:var(--muted)}}
.obs{{display:grid;gap:22px;max-width:760px}}
.ob{{display:grid;gap:6px}}
blockquote{{margin:0;font:italic 400 17px/1.5 var(--voice);border-left:2px solid var(--accent);padding-left:14px;max-width:62ch}}
blockquote cite{{display:block;font:12px/1.4 var(--mono);font-style:normal;color:var(--muted);margin-top:4px}}
.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:13.5px;width:100%}}
.data th,.data td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
.data th{{font:500 11px/1.2 var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
.num{{font-variant-numeric:tabular-nums;white-space:nowrap}}
small{{color:var(--muted)}}
.heat{{min-width:720px}}
.heat th[scope=col]{{font:500 11px/1.2 var(--mono);color:var(--muted);height:120px;vertical-align:bottom;padding:0 2px 6px}}
.heat th[scope=col] span{{writing-mode:vertical-rl;transform:rotate(180deg);display:inline-block}}
.heat th[scope=row]{{text-align:left;font-weight:600;padding:6px 10px 6px 0;white-space:nowrap;font-size:13px}}
.heat td{{text-align:center;width:52px;height:34px;font:500 13px var(--mono);border:2px solid var(--bg)}}
.h0{{background:var(--surface)}}.h1{{background:var(--h1)}}.h2{{background:var(--h2)}}.h3{{background:var(--h3)}}.h4{{background:var(--h4);color:var(--h4ink)}}
.pill{{display:inline-block;font:500 11px/1.5 var(--mono);padding:1px 7px;border-radius:3px;background:var(--accent-soft);color:var(--accent)}}
.pill.warn{{background:var(--warn-soft);color:var(--warn)}}
.lingrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:18px}}
.lin ul{{list-style:none;margin:0;padding:0;display:grid;gap:4px;font-size:14px}}
.rel{{font:12px var(--mono);color:var(--accent);margin-left:4px}}
.miss{{font:11px var(--mono);color:var(--warn);margin-left:6px}}
.twocol{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}}
pre{{background:var(--surface);border:1px solid var(--line);padding:14px;overflow-x:auto;font:12.5px/1.55 var(--mono);margin:0;max-height:420px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font:500 12px/1 var(--mono);padding:7px 10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer;border-radius:3px}}
.chip[aria-pressed=true]{{background:var(--accent);border-color:var(--accent);color:var(--bg)}}
.list{{display:grid;gap:14px;max-height:680px;overflow-y:auto;padding-right:8px;border-top:1px solid var(--line);padding-top:14px}}
.ex{{display:grid;gap:6px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.ex .meta{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font:12px var(--mono);color:var(--muted)}}
.ex blockquote{{font-size:16px}}
.plan{{display:grid;gap:12px;max-width:760px;padding-left:22px;margin:0}}
.plan li{{padding-left:4px}}
.count{{font:12px var(--mono);color:var(--muted)}}
footer{{font-size:13px;color:var(--muted);display:grid;gap:6px;max-width:760px}}
footer ul{{margin:0;padding-left:18px}}
@media (prefers-reduced-motion:no-preference){{.ex{{transition:opacity .2s}}}}
</style>
<main>
<header>
  <div class="eyebrow">Preliminary results · sample run {E(R["generated"])}</div>
  <h1>An oral history of computer science, told by its elders</h1>
  <p class="lede">A first pass at gathering computing's first-person memory from the web, coding it with typed decisions, and recording every source in MEDFORD. Seven sources, six narrators, {len(R["passages"])} passages.</p>
  <div class="facts"><span>frame <b>{frame["n"]:,} faculty</b> (Drafty)</span><span>sources <b>{len(R["sources"])}</b></span><span>MEDFORD files <b>{sum(1 for v in R["medford_validation"].values() if v.startswith("passed"))}/{len(R["medford_validation"])} valid</b></span><span>coder <b>{E(R["model"])}</b></span></div>
</header>

<div class="notice"><p><b>Read this before the numbers.</b> No TypeSafe API key was available, so the coder in this run is a keyword stub that answers in Jev's exact response format. The findings below come from reference codes I assigned by hand to each excerpt (one coder, still needs human review). The stub's scores only show that the pipeline runs end to end. Excerpts were pulled through a web reader. A spot check of 8 against the full Liskov (ACM) and Kleinrock (CBI) transcripts found all 8 present; the other 40 still have to be checked word for word.</p></div>

<section>
  <h2>How the pipeline works</h2>
  <p>A Greek rhapsode didn't invent the epic; he chose, arranged and passed on what earlier singers had said. The pipeline does the same with software. It finds where the elders' memories already live, cuts them into passages, asks typed questions about each passage, and writes the answers down in a durable, validated form.</p>
  <div class="flow">
    <div class="step"><h3>Sample the elders</h3><p>Drafty's ~5,000 CS faculty, stratified by join decade and subfield, earliest cohorts first.</p></div>
    <div class="step"><h3>Harvest</h3><p>Oral-history archives (CHM, CBI, IEEE, ACM), Wayback snapshots of faculty pages, Reddit, video transcripts, memoirs.</p></div>
    <div class="step"><h3>Generate candidates</h3><p>Split the text into passages and spot names and years with rules. Jev can't write text, so it never has to invent a span.</p></div>
    <div class="step"><h3>Ask Jev</h3><p>One call per passage: 10 theme Nouls, plus era, narrative role, specificity and affect. Every answer comes with a probability.</p></div>
    <div class="step"><h3>Route by confidence</h3><p>p ≥ 0.80 is accepted, 0.30–0.80 goes to review, and anything lower is dropped. Choice answers are accepted at confidence ≥ 0.60.</p></div>
    <div class="step"><h3>Record in MEDFORD</h3><p>One .mfd per source, checked by the Tufts parser. Every label keeps the model and thresholds that produced it.</p></div>
  </div>
</section>

<section>
  <h2>The sample</h2>
  <p>Six narrators from Drafty's earliest cohorts, plus Dijkstra, who isn't in the frame, as a control. Liskov appears twice, 25 years apart, on purpose.</p>
  {sources_table()}
</section>

<section>
  <h2>What the first 48 passages suggest</h2>
  <div class="obs">
    <div class="ob"><h3>The interviewer's frame shapes the retelling</h3>
      <p>Liskov's 1991 IEEE interview was part of an NSF-history project. Half of its excerpts are about grants, and none about how she started. Her 2016 Turing interview covers her first job, being the only girl in class, and an idea that "came out of nowhere." The same life is sung two ways for two audiences. Future sources should record who commissioned the interview as metadata, and the analysis should control for it.</p>
      <blockquote>What you can get out of the NSF is one or maybe two graduate students...<cite>Liskov, IEEE 1991</cite></blockquote>
      <blockquote>I got the idea of data abstraction. And it was this marvelous idea. It came out of nowhere.<cite>Liskov, ACM 2016, pp. 15–16</cite></blockquote></div>
    <div class="ob"><h3>The stories keep meeting at one place and time</h3>
      <p>Two separate narrators land at Stanford in 1963 with John McCarthy: Liskov as a PhD student, and Reddy on McCarthy's DARPA-funded AI computer. Cross-narrator convergence like this is the oral-history version of corroboration, and a lineage graph built at scale will surface it automatically.</p></div>
    <div class="ob"><h3>Patronage is how the pioneers remember the past</h3>
      <p>Kleinrock ("lots of money, lots of freedom"), Liskov (DARPA versus NSF) and Reddy (McCarthy's DARPA grant) all explain their careers through who paid for the work. Among the ten codes, funding comes up in half the sources, while identity comes up only in single asides.</p>
      <blockquote>lots of money, lots of freedom in terms of what we were doing, really advanced technology. It was a great, great experiment.<cite>Kleinrock, CBI OH 190, p. 29</cite></blockquote></div>
    <div class="ob"><h3>Origin stories follow a formula</h3>
      <p>Each narrator has a moment of first sight: a Time magazine article about the Harvard Mark I (Brooks), images moving on a screen (van Dam), a FORTRAN manual on day one (Liskov), a 1951 summer school (Dijkstra). "First encounter" is the most consistent code across narrators. That makes it a good anchor question for the full run.</p></div>
    <div class="ob"><h3>The sampling frame needs its own audit</h3>
      <p>Drafty lists Kleinrock at UC San Diego, but his own interview says "here at UCLA." Nine rows have join years before 1960: {susp}. Minsky's 1958 is correct. Most of the others look like data errors. These are good jobs for a Jev Noul (<code>join_year_plausible</code>) followed by human review before sampling.</p></div>
    <div class="ob"><h3>The record has gaps where the voices are missing</h3>
      <p>For Mary Shaw (CMU, 1972) I found no oral history in the archives I searched, only a biography. Gaps like this are findings in their own right. The project should log every narrator with no retrievable first-person source, broken down by gender and subfield.</p></div>
  </div>
</section>

<section>
  <h2>Themes by source</h2>
  <p>Reference codes, counted per source. Darker cells mean more passages carry that theme.</p>
  {heat_table()}
</section>

<section>
  <h2>Lineage: who the narrators name</h2>
  <p>Rule-based candidate extraction found every person in the reference set ({rel_n} mentions). The relation shown is the reference type. Where the stub disagreed, its answer appears in amber. The stub got {rel_ok} of {rel_n} right, which is why typing relations is a job for Jev.</p>
  {lineage()}
</section>

<section>
  <h2>Pipeline check: stub against the reference codes</h2>
  <div class="twocol">
    <div class="scroll"><table class="data"><thead><tr><th>Code</th><th>n</th><th>P</th><th>R</th><th>F1</th></tr></thead><tbody>{agreement_rows()}</tbody></table></div>
    <div style="display:grid;gap:10px;align-content:start">
      <p>Micro-F1 is <b>{agg["micro_f1"]:.2f}</b> (P {agg["micro_precision"]:.2f}, R {agg["micro_recall"]:.2f}). Don't read this as accuracy. I wrote the stub's keyword cues after reading these same excerpts, so the score is inflated.</p>
      <p>What it does show is that the scoring harness works. When the API key is set, the same run reports Jev's precision and recall against these codes, plus expected calibration error. Calibration is the property TypeSafe trains for with RLCD: answers given p = 0.9 should be right about 90% of the time. The stub's ECE is {R["calibration"]["ece"]:.2f}, and it sends {R["routing"].get("review",0)} of {len(R["passages"])} passages to review.</p>
    </div>
  </div>
</section>

<section>
  <h2>A MEDFORD record</h2>
  <p>Core tags (<code>@Contributor</code>, <code>@Date</code>, <code>@Data</code>, <code>@Keyword</code>, <code>@Institution</code>) are used as the spec defines them. Oral-history tags (<code>@OralHistory</code>, <code>@Passage</code>, <code>@Relation</code>, <code>@Extraction</code>) are extensions, type-checked through a custom rules file. All seven files pass the Tufts parser.</p>
  <pre>{E(MFD[:5200])}…</pre>
</section>

<section>
  <h2>Browse the passages</h2>
  <div class="chips" role="group" aria-label="Filter by theme">{chips}</div>
  <div class="count" id="count" aria-live="polite"></div>
  <div class="list" id="list"></div>
</section>

<section>
  <h2>Plan for the full run</h2>
  <ol class="plan">
    <li><b>Clean the frame.</b> Run a Jev join-year check over all ~5,000 Drafty rows, review the flagged ones, and draw about 150 narrators stratified by cohort × subfield, oversampling pre-1980 cohorts and women.</li>
    <li><b>Harvest from an open network.</b> Pull oral-history PDFs from CHM, CBI, ETHW, ACM and the Smithsonian, the yearly Wayback history of each narrator's faculty page, Reddit AMA and AskHistorians threads, YouTube transcripts, and memoir papers found through OpenAlex. Cache every raw document with its retrieval date.</li>
    <li><b>Verify quotes.</b> Fuzzy-match every excerpt against the cached full text and store page numbers. Nothing enters MEDFORD as verbatim until it matches.</li>
    <li><b>Run Jev.</b> Use one batched call per passage (15 questions) and per candidate person. Triage crawled pages first with the source-kind and usefulness questions.</li>
    <li><b>Calibrate and code.</b> Two humans double-code a 10% stratified subset. Report κ between them, Jev's F1 and ECE against them, and tune the routing thresholds per code by the cost of a mistake.</li>
    <li><b>Find new themes.</b> Cluster review-queue passages that fit no code (embeddings plus HDBSCAN or NMF), name new codes, and add them to the codebook as new Nouls.</li>
    <li><b>Publish.</b> Release the MEDFORD corpus, a lineage graph, per-cohort theme trends, and a "missing voices" table.</li>
  </ol>
</section>

<footer>
  <b>Sources</b>
  <ul>
    <li><a href="https://drafty.cs.brown.edu/" target="_blank" rel="noopener">Drafty</a> CS professors dataset (<a href="https://github.com/brownhci/drafty" target="_blank" rel="noopener">brownhci/drafty</a>, finalProfs.csv)</li>
    <li><a href="https://github.com/TuftsBCB/medford" target="_blank" rel="noopener">MEDFORD parser</a> (Tufts BCB) · <a href="https://docs.typesafe.ai/introduction/quickstart" target="_blank" rel="noopener">TypeSafe Jev docs</a></li>
    <li>Transcripts: CHM (van Dam, Reddy, Brooks), CBI OH 190 (Kleinrock), IEEE History Center No. 127 and ACM Turing Award interview (Liskov), EWD1308 (Dijkstra). Links are in the sample table.</li>
  </ul>
</footer>
</main>
<script>
const P={passages_js};
const L={json.dumps(CODE_LABEL)};
const on=new Set();
const list=document.getElementById('list'),count=document.getElementById('count');
function esc(s){{return s.replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function render(){{
  const rows=P.filter(p=>[...on].every(c=>p.g.includes(c)));
  count.textContent=rows.length+' of '+P.length+' passages'+(on.size?' with '+[...on].map(c=>L[c]).join(' + '):'');
  list.innerHTML=rows.map(p=>`<div class="ex"><blockquote>${{esc(p.t)}}<cite>${{esc(p.n)}}, ${{p.y}}${{p.pg?', p. '+esc(p.pg):''}} · about ${{esc(p.yr)}}</cite></blockquote>
  <div class="meta">${{p.g.map(c=>`<span class="pill">${{L[c]}}</span>`).join('')}}${{p.r==='review'?'<span class="pill warn">stub: review</span>':''}}</div></div>`).join('');
}}
document.querySelectorAll('.chip').forEach(b=>{{b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>{{
  const c=b.dataset.code; on.has(c)?on.delete(c):on.add(c); b.setAttribute('aria-pressed',on.has(c)); render();}})}});
render();
</script>
"""
# Save the assembled page at the same location each time the report is regenerated.
(ROOT / "out/report.html").write_text(page)
print("wrote out/report.html", len(page))
