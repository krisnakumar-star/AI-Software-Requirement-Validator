import { useEffect, useRef, useState } from "react";
import { AlertTriangle, BrainCircuit, ChevronDown, LoaderCircle, Send, Square, Trash2, Zap } from "lucide-react";
import "./ResultsWorkspace.css";

const TABS = [
  ["overview", "Overview"],
  ["requirements", "Requirement Analysis"],
  ["quality", "Quality Assessment"],
  ["cross", "Cross-Requirement"],
  ["recommendations", "Recommendations"],
  ["guide", "Instant Guide"],
  ["chat", "Local AI Chat"],
  ["review", "Local AI Deep Review"],
];
const SUGGESTED = [
  "Summarize my SRS.",
  "What are the biggest issues?",
  "Explain my quality score.",
  "Improve the weakest requirement.",
  "Generate acceptance criteria for the weakest requirement.",
  "What questions might a project reviewer ask?",
];
const sevClass = (s) => `rw-sev rw-sev-${String(s || "low").toLowerCase()}`;
const statusClass = (s) => (s === "Good" ? "rw-good" : s === "Poor" ? "rw-poor" : "rw-warn");

function Bar({ label, value }) {
  return (
    <div className="rw-bar">
      <span>{label}</span>
      <div className="rw-bar-track"><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>
      <strong>{value}</strong>
    </div>
  );
}

function MiniMarkdown({ text }) {
  return (
    <div className="rw-md">
      {String(text || "").split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <br key={i} />;
        if (/^#{1,4}\s/.test(t)) return <h4 key={i}>{t.replace(/^#+\s/, "")}</h4>;
        if (/^[-*•]\s/.test(t)) return <li key={i}>{t.replace(/^[-*•]\s/, "").replace(/\*\*/g, "")}</li>;
        return <p key={i}>{t.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}

function RequirementCard({ item }) {
  const [open, setOpen] = useState(false);
  const a = item.analysis || {};
  const top = (a.detailed_findings || [])[0] || (a.issues || []).slice(0, 1).map((message) => ({ message, recommendation: (a.suggestions || [])[0] || "Clarify the actor, expected behaviour and measurable acceptance criteria." }))[0];
  return (
    <article className="rw-card">
      <header className="rw-card-head">
        <div>
          <span className="rw-id">{item.requirement_id}</span>
          <span className={`rw-pill ${statusClass(a.status)}`}>{a.status || "—"}</span>
          <span className="rw-pill">{a.classification}</span>
          {a.priority && <span className={sevClass(a.priority === "Critical" ? "critical" : a.priority === "High" ? "high" : a.priority === "Medium" ? "medium" : "low")}>{a.priority}</span>}
        </div>
        <strong className="rw-score">{a.quality_score}<small>/100</small></strong>
      </header>
      <p className="rw-req-text">{item.requirement}</p>
      {top ? <p className="rw-main-issue"><AlertTriangle size={14} /> {top.message}</p> : <p className="rw-main-issue rw-good-text">No issues detected by the engine.</p>}
      {top && <p className="rw-muted">Fix: {top.recommendation}</p>}
      <button type="button" className="rw-link" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide detailed analysis" : "View detailed analysis"} <ChevronDown size={14} className={open ? "rw-rot" : ""} />
      </button>
      {open && (
        <div className="rw-detail">
          {a.dimension_scores && (
            <section><h5>Quality dimensions</h5>{Object.entries(a.dimension_scores).map(([k, v]) => <Bar key={k} label={k} value={v} />)}</section>
          )}
          {(a.strengths || []).length > 0 && (
            <section><h5>Strengths</h5><ul>{a.strengths.map((s, i) => <li key={i}>{s.strength} <em>“{s.evidence}”</em></li>)}</ul></section>
          )}
          {((a.detailed_findings || []).length > 0 || (a.issues || []).length > 0) && (
            <section><h5>Problems identified</h5>
              {(a.detailed_findings || (a.issues || []).map((message) => ({ severity: "medium", title: "Validation finding", message, recommendation: (a.suggestions || [])[0] || "Clarify expected behaviour and add measurable acceptance criteria." }))).map((f, i) => (
                <div key={i} className="rw-finding">
                  <div><span className={sevClass(f.severity)}>{f.severity}</span> <strong>{f.title}</strong> {f.evidence && f.evidence !== "—" && <code>{f.evidence}</code>}</div>
                  <p>{f.message}</p>
                  {f.why_it_matters && <p className="rw-muted">Why it matters: {f.why_it_matters}</p>}
                  <p className="rw-muted">Recommendation: {f.recommendation}</p>
                </div>
              ))}
            </section>
          )}
          {a.improved_requirement && <section><h5>Improved requirement draft</h5><p className="rw-draft">{a.improved_requirement}</p></section>}
          {(a.clarification_questions || []).length > 0 && <section><h5>Clarification questions</h5><ul>{a.clarification_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></section>}
          {(a.acceptance_criteria || []).length > 0 && (
            <section><h5>Acceptance criteria</h5>
              {a.acceptance_criteria.map((c) => <p key={c.id} className="rw-ac"><b>{c.id}</b> Given {c.given}, when {c.when}, then {c.then}.</p>)}
            </section>
          )}
          {a.test_scenarios && (
            <section><h5>Test scenarios</h5>
              {["positive", "negative", "boundary"].map((k) => (a.test_scenarios[k] || []).length > 0 && (
                <div key={k}><b className="rw-cap">{k}</b><ul>{a.test_scenarios[k].map((t, i) => <li key={i}>{t}</li>)}</ul></div>
              ))}
            </section>
          )}
          {a.priority_reason && <p className="rw-muted">{a.priority_reason}</p>}
          {a.explanation && <p className="rw-muted">{a.explanation}</p>}
        </div>
      )}
    </article>
  );
}

function ChatPanel({ title, badge, intro, messages, onSend, onClear, busy, error, onRetry, onStop, suggestions, footer, disabled }) {
  const [input, setInput] = useState("");
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "nearest" }); }, [messages]);
  const send = (text) => {
    const q = String(text ?? input).trim();
    if (!q || busy || disabled) return;
    setInput("");
    onSend(q);
  };
  return (
    <div className="rw-chat">
      <div className="rw-chat-head"><strong>{title}</strong><span className="rw-pill">{badge}</span>
        {messages.length > 0 && <button type="button" className="rw-icon-btn" onClick={onClear} title="Clear chat"><Trash2 size={15} /> Clear</button>}
      </div>
      <div className="rw-chat-log" aria-live="polite">
        {messages.length === 0 && <div className="rw-msg rw-assistant">{intro}</div>}
        {messages.map((m, i) => (
          <div key={i} className={`rw-msg ${m.role === "user" ? "rw-user" : "rw-assistant"}`}>
            {m.role === "assistant" ? <MiniMarkdown text={m.content || "…"} /> : m.content}
            {m.note && <small className="rw-muted">{m.note}</small>}
          </div>
        ))}
        {busy && <div className="rw-typing"><span /><span /><span /></div>}
        <div ref={endRef} />
      </div>
      {error && <div className="rw-error"><AlertTriangle size={15} /> {error} {onRetry && <button type="button" className="rw-link" onClick={onRetry}>Retry</button>}</div>}
      <div className="rw-suggest">
        {suggestions.map((s) => <button key={s} type="button" disabled={busy || disabled} onClick={() => send(s)}>{s}</button>)}
      </div>
      <form className="rw-input" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea rows={2} value={input} placeholder="Ask anything about your SRS… (Enter to send, Shift+Enter for a new line)"
          onChange={(e) => setInput(e.target.value)} disabled={disabled}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} aria-label="Chat message" />
        {busy && onStop ? <button type="button" className="rw-btn" onClick={onStop}><Square size={15} /> Stop</button>
          : <button type="submit" className="rw-btn rw-primary" disabled={!input.trim() || busy || disabled}><Send size={15} /> Send</button>}
      </form>
      {footer}
    </div>
  );
}

export default function ResultsWorkspace({ projectName, items, report, engineState, onRerun, offlineAnswer }) {
  const [tab, setTab] = useState("overview");
  const [filter, setFilter] = useState("All");
  const [guideMessages, setGuideMessages] = useState([]);
  const [chat, setChat] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [model, setModel] = useState({ status: "idle", message: "", percent: 0, device: null });
  const [review, setReview] = useState({ busy: false, text: "", error: "", selected: [] });

  const sorted = [...items].sort((x, y) => (x.analysis?.quality_score ?? 0) - (y.analysis?.quality_score ?? 0));
  const shown = sorted.filter((i) => filter === "All" || i.analysis?.status === filter || (filter === "Critical" && i.analysis?.priority === "Critical"));
  const scoreOf = (item) => Math.max(0, Math.min(100, Number(item.analysis?.quality_score) || 0));
  const averageScore = items.length ? Math.round(items.reduce((sum, item) => sum + scoreOf(item), 0) / items.length) : 0;
  const weakItems = sorted.filter((item) => scoreOf(item) < 70);
  const issueTotal = items.reduce((sum, item) => sum + (item.analysis?.issues?.length || 0), 0);
  const fallbackSummary = {
    overall_score: averageScore,
    risk_verdict: { level: averageScore >= 80 ? "Low" : averageScore >= 60 ? "Moderate" : "High", reason: "Calculated from the saved requirement quality scores." },
    narrative: `The validation engine reviewed ${items.length} requirements and calculated an average quality score of ${averageScore}/100. It recorded ${issueTotal} issue(s). ${weakItems.length} requirement(s) scored below 70 and should be reviewed first.`,
    critical_requirements: weakItems.slice(0, 5).map((item) => item.requirement_id),
    main_risk_areas: [...new Set(weakItems.flatMap((item) => item.analysis?.issues || []))].slice(0, 5),
    main_weaknesses: [...new Set(items.flatMap((item) => item.analysis?.issues || []))].slice(0, 5).map((issue) => ({ issue, percent: Math.round(items.filter((item) => (item.analysis?.issues || []).includes(issue)).length / Math.max(1, items.length) * 100) })),
    top_recommendations: [
      "Rewrite vague requirements with a clear actor, action, trigger and observable outcome.",
      "Add measurable acceptance criteria and boundary conditions.",
      "Specify permissions, error handling and expected behaviour for invalid inputs.",
      "Review low-scoring requirements with the relevant stakeholder before approval."
    ]
  };
  const summary = report?.executive_summary || fallbackSummary;
  const fallbackFindings = {
    contradictions: [], duplicates: [], dependencies: [], terminology: [],
    missing_requirements: [], missing_information: [], security_gaps: [], performance_gaps: [],
    coverage: { gaps: [] },
    traceability: { generated_ids: items.map((item) => item.requirement_id), duplicate_ids: [], broken_references: [], matrix: [] }
  };
  const findings = report?.project_findings || fallbackFindings;
  const dimensionAverages = ["clarity", "completeness", "testability"].reduce((acc, key) => {
    const values = items.map((item) => item.analysis?.[key]).filter((value) => typeof value === "number");
    acc[key] = values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : averageScore;
    return acc;
  }, {});

  const loadModel = async () => {
    setModel({ status: "loading", message: "Preparing the local AI runtime…", percent: 0, device: null });
    try {
      const { loadLocalModel } = await import("../services/localSrsModel.js");
      const device = await loadLocalModel((p) => setModel((m) => ({ ...m, message: p.message, percent: p.percent ?? m.percent })));
      setModel({ status: "ready", message: `Qwen2.5-0.5B is running locally (${device === "webgpu" ? "WebGPU" : "CPU/WASM"}).`, percent: 100, device });
    } catch (err) {
      setModel({ status: "error", message: err.message || "The local model could not be loaded.", percent: 0, device: null });
    }
  };

  const askLocal = async (question) => {
    setLastQuestion(question);
    setChatError("");
    const history = chat;
    setChat([...history, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setChatBusy(true);
    try {
      const { generateSrsChatReply } = await import("../services/localSrsModel.js");
      const { reply, note } = await generateSrsChatReply(items, history, question, (p) => setModel((m) => ({ ...m, message: p.message })), {
        project: { name: projectName, summary },
        onToken: (text) => setChat((c) => [...c.slice(0, -1), { role: "assistant", content: text }]),
      });
      setChat((c) => [...c.slice(0, -1), { role: "assistant", content: reply, note }]);
    } catch (err) {
      setChat((c) => c.slice(0, -2));
      setChatError(err.message || "The local model could not answer.");
    } finally {
      setChatBusy(false);
    }
  };

  const stopLocal = async () => (await import("../services/localSrsModel.js")).cancelLocalGeneration();

  const runReview = async () => {
    const chosen = review.selected.length ? items.filter((i) => review.selected.includes(i.requirement_id)) : sorted.slice(0, 3);
    setReview((r) => ({ ...r, busy: true, text: "", error: "" }));
    try {
      const { generateSrsReview } = await import("../services/localSrsModel.js");
      const text = await generateSrsReview(chosen, (p) => setModel((m) => ({ ...m, message: p.message })), {
        onToken: (t) => setReview((r) => ({ ...r, text: t })),
      });
      setReview((r) => ({ ...r, busy: false, text }));
    } catch (err) {
      setReview((r) => ({ ...r, busy: false, error: err.message || "The review failed." }));
    }
  };

  const modelGate = model.status !== "ready" && (
    <div className="rw-model-gate">
      <BrainCircuit size={22} />
      <div>
        <strong>Load the local Qwen2.5-0.5B model</strong>
        <p className="rw-muted">Runs entirely in your browser (WebGPU, or CPU/WASM fallback). No API key and no cloud inference. The first download is a few hundred MB and needs internet; later the browser cache is reused.</p>
        {model.status === "loading" && <><div className="rw-bar-track"><i style={{ width: `${model.percent || 3}%` }} /></div><small>{model.message}</small></>}
        {model.status === "error" && <div className="rw-error"><AlertTriangle size={15} /> {model.message}</div>}
      </div>
      <button type="button" className="rw-btn rw-primary" onClick={loadModel} disabled={model.status === "loading"}>
        {model.status === "loading" ? <><LoaderCircle size={15} className="rw-spin" /> Loading…</> : model.status === "error" ? "Retry" : "Start local AI"}
      </button>
    </div>
  );

  return (
    <section className="rw">
      <nav className="rw-tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "rw-tab rw-active" : "rw-tab"} onClick={() => setTab(key)}>{label}</button>
        ))}
      </nav>

      {engineState.loading && <div className="rw-info"><LoaderCircle size={15} className="rw-spin" /> Running the local SRS analysis engine…</div>}
      {engineState.error && <div className="rw-error"><AlertTriangle size={15} /> {engineState.error} <button type="button" className="rw-link" onClick={onRerun}>Retry</button></div>}
      {engineState.notice && <div className="rw-info"><Zap size={15} /> {engineState.notice}</div>}

      {tab === "overview" && (
        summary ? (
          <div className="rw-grid">
            <div className="rw-panel rw-span2">
              <h3>Executive summary</h3>
              <p>{summary.narrative}</p>
              <p><span className={`rw-pill ${summary.risk_verdict.level === "Low" ? "rw-good" : summary.risk_verdict.level === "High" ? "rw-poor" : "rw-warn"}`}>Risk: {summary.risk_verdict.level}</span> <span className="rw-muted">{summary.risk_verdict.reason}</span></p>
            </div>
            <div className="rw-panel"><h3>Critical requirements</h3>{summary.critical_requirements.length ? <p>{summary.critical_requirements.join(", ")}</p> : <p className="rw-muted">None</p>}
              <h3>Main risk areas</h3><p>{summary.main_risk_areas.join(", ") || "None identified"}</p></div>
            <div className="rw-panel"><h3>Main weaknesses</h3><ul>{summary.main_weaknesses.slice(0, 5).map((w) => <li key={w.issue}>{w.issue} — {w.percent}% of requirements</li>)}</ul></div>
            <div className="rw-panel rw-span2"><h3>Top recommendations</h3><ol>{summary.top_recommendations.map((r) => <li key={r}>{r}</li>)}</ol></div>
          </div>
        ) : !engineState.loading && <p className="rw-muted">Detailed engine analysis is not available yet. <button type="button" className="rw-link" onClick={onRerun}>Run analysis</button></p>
      )}

      {tab === "requirements" && (
        <div>
          <div className="rw-filters">{["All", "Poor", "Needs Improvement", "Good", "Critical"].map((f) => <button key={f} type="button" className={filter === f ? "rw-chip rw-active" : "rw-chip"} onClick={() => setFilter(f)}>{f}</button>)}</div>
          {shown.length === 0 && <p className="rw-muted">No requirements match this filter.</p>}
          {shown.map((item) => <RequirementCard key={item.requirement_id} item={item} />)}
        </div>
      )}

      {tab === "quality" && (
        <div className="rw-grid">
          <div className="rw-panel"><h3>Average dimension scores</h3>{Object.entries(report?.quality_assessment?.average_dimension_scores || dimensionAverages).map(([k, v]) => <Bar key={k} label={k} value={v} />)}</div>
          <div className="rw-panel"><h3>Findings by severity</h3>{Object.entries(report?.quality_assessment?.severity_distribution || { high: weakItems.length, medium: issueTotal, low: Math.max(0, items.length - weakItems.length) }).map(([k, v]) => <p key={k}><span className={sevClass(k)}>{k}</span> {v}</p>)}
            <h3>Requirement types</h3>{Object.entries(report?.quality_assessment?.type_distribution || { "Classified requirements": items.length }).map(([k, v]) => <p key={k}>{k}: <b>{v}</b></p>)}</div>
          <div className="rw-panel rw-span2"><h3>Categories covered</h3><div className="rw-filters">{Object.entries(report?.quality_assessment?.category_distribution || { "Requirements reviewed": items.length }).map(([k, v]) => <span key={k} className="rw-chip">{k} · {v}</span>)}</div>
            {findings.coverage.gaps.length > 0 && <><h3>Coverage gaps</h3><ul>{findings.coverage.gaps.map((g) => <li key={g}>{g}</li>)}</ul></>}</div>
        </div>
      )}

      {tab === "cross" && findings && (
        <div className="rw-stack">
          {[["Possible contradictions", findings.contradictions, "explanation"], ["Duplicates / overlaps", findings.duplicates, "explanation"]].map(([title, list, key]) => (
            <details key={title} className="rw-panel" open={list.length > 0}><summary>{title} ({list.length})</summary>
              {list.length === 0 ? <p className="rw-muted">None detected.</p> : list.map((x, i) => (
                <div key={i} className="rw-finding"><div><b>{x.requirements.join(" ↔ ")}</b> {x.severity && <span className={sevClass(x.severity)}>{x.severity}</span>}</div><p>{x[key]}</p><p className="rw-muted">{x.recommendation}</p></div>
              ))}</details>
          ))}
          <details className="rw-panel"><summary>Dependencies ({findings.dependencies.length})</summary>{findings.dependencies.map((d, i) => <p key={i}><b>{d.from} → {d.to}</b> <span className="rw-muted">({d.type})</span> {d.explanation}</p>)}</details>
          <details className="rw-panel"><summary>Terminology ({findings.terminology.length})</summary>{findings.terminology.map((t) => <p key={t.concept}>{t.explanation} <span className="rw-muted">{t.recommendation}</span></p>)}</details>
          <details className="rw-panel"><summary>Missing requirements ({findings.missing_requirements.length})</summary>{findings.missing_requirements.map((m) => <p key={m.missing}><b>{m.missing}</b>: {m.reason} <span className="rw-muted">Related: {m.related_requirements.join(", ")}</span></p>)}</details>
          <details className="rw-panel"><summary>Missing information ({findings.missing_information.length})</summary>{findings.missing_information.map((m) => <p key={m.type}><b>{m.type}</b>: {m.requirements.join(", ")}</p>)}</details>
          <details className="rw-panel"><summary>Security gaps ({findings.security_gaps.length}) · Performance gaps ({findings.performance_gaps.length})</summary>{[...findings.security_gaps, ...findings.performance_gaps].map((g, i) => <p key={i}><b>{g.requirement}</b>: {g.issue}</p>)}</details>
          <details className="rw-panel"><summary>Traceability</summary>
            <p>Generated IDs: {findings.traceability.generated_ids.length} · Duplicate IDs: {findings.traceability.duplicate_ids.join(", ") || "none"} · Broken references: {findings.traceability.broken_references.map((b) => `${b.requirement}→${b.reference}`).join(", ") || "none"}</p>
            <div className="rw-table-wrap"><table className="rw-table"><thead><tr><th>ID</th><th>Type</th><th>Priority</th><th>Score</th><th>Depends on</th><th>Related</th></tr></thead>
              <tbody>{findings.traceability.matrix.map((r) => <tr key={r.id}><td>{r.id}</td><td>{r.type}</td><td>{r.priority}</td><td>{r.score}</td><td>{r.depends_on.join(", ")}</td><td>{r.related.join(", ")}</td></tr>)}</tbody></table></div>
          </details>
        </div>
      )}

      {tab === "recommendations" && (
        <div className="rw-stack">
          <div className="rw-panel"><h3>Prioritised improvement plan</h3>
            {(report?.improvement_plan || summary.top_recommendations.map((action, index) => ({ step: index + 1, title: ["Clarify requirement behaviour", "Define measurable acceptance criteria", "Cover edge cases and failures", "Review low-scoring requirements"][index] || "Refine requirements", action, requirement_ids: weakItems.slice(0, 4).map((item) => item.requirement_id), rationale: "Recommended based on the saved validation scores and findings." }))).map((s) => <div key={s.step} className="rw-finding"><b>{s.step}. {s.title}</b><p>{s.action}</p>{s.requirement_ids?.length > 0 && <p className="rw-muted">Requirements: {s.requirement_ids.join(", ")}</p>}<p className="rw-muted">{s.rationale}</p></div>)}
          </div>
          <div className="rw-panel"><h3>Risks</h3>{(report?.risks || (weakItems.length ? [{ level: "medium", risk: "Requirements may be ambiguous or insufficiently testable", impact: `${weakItems.length} requirement(s) scored below 70.`, mitigation: "Clarify behaviour and add verifiable acceptance criteria.", affected_requirements: weakItems.slice(0, 5).map((item) => item.requirement_id) }] : [])).map((r, i) => <div key={i} className="rw-finding"><span className={sevClass(r.level)}>{r.level}</span> <b>{r.risk}</b><p className="rw-muted">{r.impact} Mitigation: {r.mitigation}</p>{r.affected_requirements?.length > 0 && <p className="rw-muted">{r.affected_requirements.join(", ")}</p>}</div>)}</div>
        </div>
      )}

      {tab === "guide" && (
        <ChatPanel title="Instant Offline Guide" badge="No model · No API · Instant" disabled={false}
          intro="Hi! I'm the instant guide. I give rule-based answers from your validation results — no AI model involved. For free-form questions, use Local AI Chat."
          messages={guideMessages} busy={false} onClear={() => setGuideMessages([])}
          onSend={(q) => setGuideMessages((m) => [...m, { role: "user", content: q }, { role: "assistant", content: offlineAnswer(q) }])}
          suggestions={["Summarize my SRS", "What should I fix first?", "What information is missing?", "How do I write acceptance criteria?"]} />
      )}

      {tab === "chat" && (
        <>
          {modelGate}
          {model.status === "ready" && <div className="rw-info"><Zap size={15} /> {model.message}</div>}
          <ChatPanel title="Local AI Chat" badge="Qwen2.5-0.5B · on-device" disabled={model.status !== "ready"}
            intro="Hello! I'm ReqValidator Local, running on your device. Ask me anything about your SRS — summaries, specific requirement IDs, scores, rewrites, acceptance criteria, tests, or follow-ups."
            messages={chat} busy={chatBusy} error={chatError} onRetry={lastQuestion ? () => askLocal(lastQuestion) : null}
            onClear={() => { setChat([]); setChatError(""); }} onSend={askLocal} onStop={stopLocal} suggestions={SUGGESTED}
            footer={<small className="rw-muted">Answers are generated by a small local model and can be wrong; verify against the analysis.</small>} />
        </>
      )}

      {tab === "review" && (
        <div className="rw-stack">
          {modelGate}
          <div className="rw-panel">
            <h3>Local AI Deep Review</h3>
            <p className="rw-muted">Select up to 4 requirements (default: the 3 weakest). Qwen writes an additional narrative review on your device.</p>
            <div className="rw-filters">{sorted.slice(0, 20).map((i) => {
              const on = review.selected.includes(i.requirement_id);
              return <button key={i.requirement_id} type="button" className={on ? "rw-chip rw-active" : "rw-chip"}
                onClick={() => setReview((r) => ({ ...r, selected: on ? r.selected.filter((x) => x !== i.requirement_id) : [...r.selected, i.requirement_id].slice(-4) }))}>{i.requirement_id} · {i.analysis?.quality_score}</button>;
            })}</div>
            <button type="button" className="rw-btn rw-primary" disabled={model.status !== "ready" || review.busy} onClick={runReview}>
              {review.busy ? <><LoaderCircle size={15} className="rw-spin" /> Reviewing…</> : "Run deep review"}</button>
            {review.busy && <button type="button" className="rw-btn" onClick={stopLocal}><Square size={15} /> Stop</button>}
            {review.error && <div className="rw-error"><AlertTriangle size={15} /> {review.error}</div>}
            {review.text && <MiniMarkdown text={review.text} />}
          </div>
        </div>
      )}
    </section>
  );
}
