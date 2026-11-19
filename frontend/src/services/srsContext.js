// Builds a compact, question-relevant SRS context for the local LLM.
// Large documents are retrieved by relevance so the prompt stays within budget.
const STOP = new Set("the a an and or to of in on for by with is are be as it this that shall must should will can may what which how why my our your me please explain about give show tell requirement requirements".split(" "));
const ID_RE = /\b([A-Z]{1,6}[-_]?\d+(?:\.\d+)*)\b/gi;
const GLOBAL_RE = /\b(summar|overview|overall|entire|whole|all|biggest|main|top|worst|first|priority|fix first|score|architecture|reviewer|functional|non.?functional|missing|risks?|report)\b/i;
const FOLLOW_UP_RE = /^(it|that|this|again|continue|more|why|and|also|what about|can you|improve it|another|same)\b|\b(it|that one|this one|again)\b/i;

const terms = (text) => String(text || "").toLowerCase().match(/[a-z0-9]+/g)?.filter((w) => w.length > 2 && !STOP.has(w)) || [];

function idsIn(text, known) {
  const found = [];
  for (const match of String(text || "").matchAll(ID_RE)) {
    const id = match[1].toUpperCase();
    if (known.has(id)) found.push(id);
  }
  const numbered = String(text || "").match(/\brequirement\s+(\d+)\b/i);
  if (numbered) {
    const candidate = [...known].find((id) => id.endsWith(numbered[1].padStart(3, "0")) || id.endsWith(`-${numbered[1]}`));
    if (candidate) found.push(candidate);
  }
  return [...new Set(found)];
}

function detailBlock(item) {
  const a = item.analysis || {};
  const findings = (a.detailed_findings || []).slice(0, 5).map((f) => `- [${f.severity}] ${f.message}`);
  const issues = findings.length ? findings : (a.issues || []).slice(0, 5).map((i) => `- ${i}`);
  return [
    `${item.requirement_id}: "${String(item.requirement || "").slice(0, 500)}"`,
    `  Score ${a.quality_score ?? "n/a"}/100 (${a.status || "n/a"}), type ${a.classification || "n/a"}, priority ${a.priority || "n/a"}`,
    issues.length ? `  Findings:\n  ${issues.join("\n  ")}` : "  Findings: none",
    a.improved_requirement || a.suggested_rewrite ? `  Suggested rewrite: ${String(a.improved_requirement || a.suggested_rewrite).slice(0, 400)}` : "",
  ].filter(Boolean).join("\n");
}

export function buildChatContext(items, history, question, project = {}, budget = 6500) {
  const list = (Array.isArray(items) ? items : []).filter((i) => i?.requirement);
  const known = new Set(list.map((i) => String(i.requirement_id || "").toUpperCase()));
  let focus = idsIn(question, known);
  if (!focus.length && FOLLOW_UP_RE.test(String(question || "").trim())) {
    for (const message of [...(history || [])].reverse()) {
      focus = idsIn(message.content, known);
      if (focus.length) break;
    }
  }
  const q = new Set(terms(question));
  const scored = list.map((item) => {
    const hay = terms(`${item.requirement} ${(item.analysis?.issues || []).join(" ")} ${(item.analysis?.categories || []).join(" ")}`);
    let score = hay.filter((w) => q.has(w)).length;
    if (focus.includes(String(item.requirement_id).toUpperCase())) score += 100;
    return { item, score };
  }).sort((a, b) => b.score - a.score || (a.item.analysis?.quality_score ?? 100) - (b.item.analysis?.quality_score ?? 100));

  const summary = project.summary || {};
  const header = [
    `Project: ${project.name || "[not provided]"}`,
    `Requirements: ${list.length}; average score ${summary.overall_score ?? project.score ?? "n/a"}/100; good ${summary.good ?? "n/a"}, needs improvement ${summary.needs_improvement ?? "n/a"}, poor ${summary.poor ?? "n/a"}.`,
    summary.narrative ? `Summary: ${summary.narrative}` : "",
    (summary.top_recommendations || []).length ? `Top recommendations:\n- ${summary.top_recommendations.slice(0, 4).join("\n- ")}` : "",
  ].filter(Boolean).join("\n");

  let used = header.length;
  const parts = [header, "DETAILED REQUIREMENTS:"];
  const detailed = [];
  const maxDetailed = focus.length ? Math.max(focus.length, 2) : GLOBAL_RE.test(question) ? 4 : 5;
  for (const { item, score } of scored) {
    if (detailed.length >= maxDetailed || (score === 0 && detailed.length >= 2 && !GLOBAL_RE.test(question))) break;
    const block = detailBlock(item);
    if (used + block.length > budget * 0.7) break;
    parts.push(block);
    detailed.push(item.requirement_id);
    used += block.length;
  }
  const brief = [];
  for (const { item } of scored) {
    if (detailed.includes(item.requirement_id)) continue;
    const line = `${item.requirement_id} (${item.analysis?.quality_score ?? "?"}): ${String(item.requirement).slice(0, 110)}`;
    if (used + line.length > budget) break;
    brief.push(line);
    used += line.length;
  }
  if (brief.length) parts.push("OTHER REQUIREMENTS (brief):", ...brief);
  const omitted = list.length - detailed.length - brief.length;
  const note = omitted > 0
    ? `Context included ${detailed.length + brief.length} of ${list.length} requirements (${omitted} omitted to fit the model's context). Mention a requirement ID to focus on it.`
    : "";
  if (note) parts.push(`NOTE: ${note}`);
  return { context: parts.join("\n"), note, focus: detailed };
}
