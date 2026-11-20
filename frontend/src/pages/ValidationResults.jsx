
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  FileText,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock3,
  RefreshCw,
  LoaderCircle,
  Lightbulb,
  Target,
  Search,
  ClipboardCheck,
} from "lucide-react";
import { apiUrl } from "../config/api";
import ResultsWorkspace from "../components/ResultsWorkspace";

function isValidAnalysisResponse(data) {
  if (
    !data ||
    !Array.isArray(data.results) ||
    data.results.length < 1 ||
    data.total_requirements !== data.results.length
  ) {
    return false;
  }

  return data.results.every((result) => {
    const analysis = result?.analysis;
    return (
      typeof result?.requirement === "string" &&
      typeof analysis?.quality_score === "number" &&
      Number.isInteger(analysis.quality_score) &&
      analysis.quality_score >= 0 &&
      analysis.quality_score <= 100 &&
      [
        "classification",
        "clarity",
        "completeness",
        "testability",
        "suggested_rewrite",
        "explanation",
      ].every((field) => typeof analysis[field] === "string") &&
      ["ambiguities", "missing_information", "issues"].every(
        (field) =>
          Array.isArray(analysis[field]) &&
          analysis[field].every((item) => typeof item === "string")
      )
    );
  });
}

function buildOfflineSrsAnswer(question, items, metrics) {
  const q = String(question || '').toLowerCase();
  const records = Array.isArray(items) ? items : [];
  const flagged = records.filter((item) => {
    const a = item.analysis || {};
    return (a.issues || []).length || (a.ambiguities || []).length || (a.missing_information || []).length || Number(a.quality_score) < 60;
  });
  const detailLines = (entries) => entries.slice(0, 6).map((item, index) => {
    const a = item.analysis || {};
    const id = item.requirement_id || `Requirement ${index + 1}`;
    const notes = [...(a.issues || []), ...(a.ambiguities || []), ...(a.missing_information || [])].slice(0, 3);
    return `• ${id}: ${notes.length ? notes.join('; ') : (a.explanation || 'Review clarity and testability.')}`;
  }).join('\n');
  if (/^(hi|hello|hey)[!. ]*$/.test(q)) return 'Hello! I am the offline ReqValidator guide. Ask me to explain your score, summarize findings, identify issues, improve a requirement, or write acceptance criteria.';
  if (/summar|overview|brief|explain report/.test(q)) return `Validation summary\n• Requirements: ${metrics.totalRequirements}\n• Quality score: ${metrics.score}/100 (${metrics.scoreStatus})\n• Good: ${metrics.goodRequirements}\n• Needs improvement: ${metrics.needsImprovement}\n• Poor: ${metrics.poorRequirements}\n• Duplicates: ${metrics.duplicateRequirements}\n• Inconsistencies: ${metrics.inconsistentRequirements}\n\nStart with poor and needs-improvement requirements. Resolve unclear behavior, missing details, and add measurable acceptance criteria.`;
  if (/score|rating|quality|percentage/.test(q)) return `Your quality score is ${metrics.score}/100 (${metrics.scoreStatus}). There are ${metrics.goodRequirements} good, ${metrics.needsImprovement} needing improvement, and ${metrics.poorRequirements} poor requirements. Treat this as a screening indicator and review individual findings before approval.`;
  if (/duplicate|repeat/.test(q)) return `The validation summary reports ${metrics.duplicateRequirements} duplicate requirement(s). Compare requirements describing the same user goal or behavior. Merge only when they truly express the same rule; preserve distinct conditions.`;
  if (/inconsisten|conflict|contradict/.test(q)) return `The validation summary reports ${metrics.inconsistentRequirements} inconsistent requirement(s). Check for conflicting rules, limits, roles, terminology, or system behavior. Confirm the intended rule with the product owner before editing.`;
  if (/poor|risk|problem|issue|important|priority|fix first|attention/.test(q)) return `Requirements needing attention:\n${detailLines(flagged) || 'No detailed flagged requirements are available.'}\n\nRecommended order: clarify behavior, specify actors and inputs, define failure and boundary cases, then add testable acceptance criteria.`;
  if (/missing|ambigu|unclear|vague|incomplete/.test(q)) {
    const details = records.flatMap((item, index) => [...(item.analysis?.ambiguities || []), ...(item.analysis?.missing_information || [])].map((note) => `• ${item.requirement_id || `Requirement ${index + 1}`}: ${note}`));
    return details.length ? `Potential gaps from the analysis:\n${details.slice(0, 10).join('\n')}\n\nConfirm unknown details with the product owner instead of guessing.` : 'Check that each requirement states its actor, trigger, inputs, expected outcome, constraints, permissions, and exception behavior.';
  }
  if (/test|acceptance|given|when|then|verif/.test(q)) return 'Use Given–When–Then acceptance criteria:\n• Given: the starting condition and relevant user/system state.\n• When: the action or event occurs.\n• Then: the observable expected result.\nAlso cover valid input, invalid input, boundary values, permissions, and failure behavior. Use only confirmed measurable values.';
  if (/rewrite|improv|better|correct|requirement/.test(q)) {
    const target = records.find((item) => item.analysis?.suggested_rewrite);
    return target ? `Suggested rewrite for ${target.requirement_id || 'the requirement'}:\n${target.analysis.suggested_rewrite}\n\nConfirm all unknown details with the product owner.` : 'Paste the exact requirement text or include its ID. A good rewrite identifies the actor, action, conditions, expected outcome, and measurable acceptance criteria without inventing details.';
  }
  if (/functional|non.?functional|classification|type/.test(q)) return 'Functional requirements describe what the system must do. Non-functional requirements describe quality or constraints such as performance, security, usability, reliability, and availability. Both should be specific and verifiable.';
  if (/actor|user|stakeholder|who use/.test(q)) return 'Identify each actor that interacts with the system: end users, administrators, external services, or other systems. Describe each actor’s goal, permitted actions, and access restrictions. Do not assume roles that are not stated.';
  return 'I can help without loading a model. Try: “Summarize my SRS”, “Explain my score”, “What should I fix first?”, “What information is missing?”, or “How do I write acceptance criteria?”. For a specific rewrite, paste the requirement text.';
}
function ValidationResults() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId");

  const [summary, setSummary] = useState(null);
  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState(false);
  const [llmAnalysis, setLlmAnalysis] = useState(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [error, setError] = useState("");
  const [llmError, setLlmError] = useState("");
  const [llmFallbackNotice, setLlmFallbackNotice] = useState("");
  const [showAiAnalysis, setShowAiAnalysis] = useState(false);
  const [projectInfo, setProjectInfo] = useState(null);
  const autoAnalysisStarted = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const runValidation = async () => {
      if (!projectId) {
        navigate("/dashboard");
        return;
      }

      const token = localStorage.getItem("token");

      if (!token) {
        navigate("/login");
        return;
      }

      setLoading(true);
      setValidating(true);
      setError("");

      try {
        const validationResponse = await fetch(
          apiUrl(`/api/validation/project/${encodeURIComponent(projectId)}`),
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!validationResponse.ok) {
          const message = await validationResponse.text();
          throw new Error(
            message || "Unable to validate requirements."
          );
        }

        const summaryResponse = await fetch(
          apiUrl(`/api/validation/project/${encodeURIComponent(projectId)}/summary`),
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!summaryResponse.ok) {
          throw new Error("Failed to load the validation summary.");
        }

        const summaryData = await summaryResponse.json();

        const requirementsResponse = await fetch(
          apiUrl(`/api/requirements/project/${encodeURIComponent(projectId)}`),
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!requirementsResponse.ok) {
          throw new Error("Failed to load the requirements.");
        }

        const requirementsData = await requirementsResponse.json();

        try {
          const projectResponse = await fetch(apiUrl(`/api/projects/${encodeURIComponent(projectId)}`), {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (projectResponse.ok && !cancelled) {
            setProjectInfo(await projectResponse.json());
          }
        } catch {
          // Project metadata is optional for this page.
        }

        if (!cancelled) {
          setSummary(summaryData);
          setRequirements(
            Array.isArray(requirementsData) ? requirementsData : []
          );
          const savedAnalyses = Array.isArray(requirementsData)
            ? requirementsData.filter((item) => item.aiAnalysis)
            : [];
          if (savedAnalyses.length > 0) {
            setLlmAnalysis({
              total_requirements: savedAnalyses.length,
              results: savedAnalyses.map((item) => ({
                requirement_id: item.requirementId,
                requirement: item.requirementText,
                analysis: item.aiAnalysis,
              })),
            });
          }
        }
      } catch (err) {
        console.error("Validation error:", err);

        if (!cancelled) {
          setError(
            err.message === "Failed to fetch"
              ? "Cannot connect to the backend. Make sure Spring Boot is running."
              : err.message || "Unable to load validation results."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setValidating(false);
        }
      }
    };

    runValidation();

    return () => {
      cancelled = true;
    };
  }, [projectId, navigate]);

  // Build the detailed workspace from the validation data already stored by
  // Spring Boot. This removes the fragile Render-to-FastAPI dependency from
  // the results page; no remote AI provider is called here.
  const runLlmAnalysis = async () => {
    setLlmLoading(true);
    setLlmError("");
    setLlmFallbackNotice("");

    try {
      const records = requirements
        .filter((item) => item.requirementText)
        .map((item, index) => {
          const score = Number(item.qualityScore);
          const issues = Array.isArray(item.issues)
            ? item.issues.filter((entry) => typeof entry === "string")
            : [];
          const suggestions = Array.isArray(item.suggestions)
            ? item.suggestions.filter((entry) => typeof entry === "string")
            : [];
          const textValue = (value, fallback = "Not assessed") =>
            typeof value === "string" && value.trim() ? value : fallback;

          return {
            requirement_id: item.requirementId || `REQ-${String(index + 1).padStart(3, "0")}`,
            requirement: item.requirementText,
            analysis: {
              quality_score: Number.isFinite(score)
                ? Math.max(0, Math.min(100, Math.round(score)))
                : Math.max(0, Math.min(100, Math.round(Number(summary?.averageScore) || 0))),
              classification: textValue(item.classification, "Requirement"),
              clarity: textValue(item.clarity),
              completeness: textValue(item.completeness),
              testability: textValue(item.testability),
              suggested_rewrite: suggestions[0] || "",
              explanation: issues.length
                ? `The existing validation engine flagged: ${issues.join("; ")}`
                : "No issue details were recorded by the existing validation engine. Review the requirement against its stated business rules.",
              ambiguities: [],
              missing_information: [],
              issues,
            },
          };
        });

      if (!records.length) {
        throw new Error("No requirement records are available for detailed review.");
      }

      setLlmAnalysis({
        status: "existing-validation-data",
        provider: "ReqValidator validation engine",
        total_requirements: records.length,
        results: records,
      });
      setLlmFallbackNotice(
        "Showing the existing requirement validation results. The separate hosted AI service is not required for this workspace."
      );
    } catch (err) {
      setLlmError(err.message || "Unable to prepare the analysis workspace.");
    } finally {
      setLlmLoading(false);
    }
  };

  // Prepare the workspace locally once the validation data has loaded.
  useEffect(() => {
    if (summary && requirements.length > 0 && !autoAnalysisStarted.current) {
      autoAnalysisStarted.current = true;
      runLlmAnalysis();
    }
  }, [summary, requirements]); // eslint-disable-line react-hooks/exhaustive-deps

  const getStatusClass = (status) => {
    const normalized = (status || "").toUpperCase();

    if (["PASS", "GOOD", "CONSISTENT", "UNIQUE"].includes(normalized)) {
      return "vr-status-good";
    }

    if (["FAIL", "POOR", "INCONSISTENT", "DUPLICATE"].includes(normalized)) {
      return "vr-status-bad";
    }

    return "vr-status-review";
  };

  const getStatusIcon = (status) => {
    const normalized = (status || "").toUpperCase();

    if (["PASS", "GOOD", "CONSISTENT", "UNIQUE"].includes(normalized)) {
      return <CheckCircle2 size={15} />;
    }

    if (["FAIL", "POOR", "INCONSISTENT", "DUPLICATE"].includes(normalized)) {
      return <XCircle size={15} />;
    }

    return <AlertTriangle size={15} />;
  };

  if (loading || validating) {
    return (
      <div className="vr-page">
        <header className="vr-header">
          <Link to="/dashboard" className="vr-brand">
            <span className="vr-brand-icon">
              <ShieldCheck size={22} />
            </span>
            <span>
              Req<span>Validator</span>
            </span>
          </Link>
        </header>

        <main className="vr-container">
          <section className="vr-state-card">
            <div className="vr-loading-icon">
              <LoaderCircle size={34} />
            </div>
            <span className="vr-eyebrow">VALIDATION IN PROGRESS</span>
            <h1>Analyzing your requirements</h1>
            <p>
              The validation engine is checking your requirements.
              Please wait while the results are prepared.
            </p>
            <div className="vr-loading-track">
              <span />
            </div>
            <small>
              <Clock3 size={14} />
              This may take a little while.
            </small>
          </section>
        </main>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="vr-page">
        <header className="vr-header">
          <Link to="/dashboard" className="vr-brand">
            <span className="vr-brand-icon">
              <ShieldCheck size={22} />
            </span>
            <span>
              Req<span>Validator</span>
            </span>
          </Link>
        </header>

        <main className="vr-container">
          <section className="vr-state-card">
            <div className="vr-error-icon">
              <AlertTriangle size={29} />
            </div>
            <h1>Results unavailable</h1>
            <p>
              {error ||
                "A validation summary could not be loaded for this project."}
            </p>
            <div className="vr-state-actions">
              <Link
                to={`/project/${projectId}`}
                className="vr-secondary-button"
              >
                <ArrowLeft size={16} />
                Back to Project
              </Link>
              <button
                type="button"
                className="vr-primary-button"
                onClick={() => window.location.reload()}
              >
                <RefreshCw size={16} />
                Try Again
              </button>
            </div>
          </section>
        </main>
      </div>
    );
  }

  const totalRequirements = Number(summary.totalRequirements) || 0;
  const duplicateRequirements = Number(summary.duplicateRequirements) || 0;
  const inconsistentRequirements =
    Number(summary.inconsistentRequirements) || 0;
  const averageScore = Number(summary.averageScore) || 0;
  const goodRequirements = Number(summary.goodRequirements) || 0;
  const needsImprovement = Number(summary.needsImprovement) || 0;
  const poorRequirements = Number(summary.poorRequirements) || 0;

  const score = Math.max(0, Math.min(100, Math.round(averageScore)));

  const scoreStatus =
    score >= 80 ? "Good" : score >= 60 ? "Needs Improvement" : "Poor";

  const issueCount =
    duplicateRequirements +
    inconsistentRequirements +
    needsImprovement +
    poorRequirements;

  const completenessPercentage =
    totalRequirements > 0
      ? Math.round(
          ((goodRequirements + needsImprovement) / totalRequirements) * 100
        )
      : 0;

  const consistencyPercentage =
    totalRequirements > 0
      ? Math.round(
          ((totalRequirements - inconsistentRequirements) /
            totalRequirements) *
            100
        )
      : 0;

  const ambiguityPercentage =
    totalRequirements > 0
      ? Math.round(
          ((totalRequirements - needsImprovement - poorRequirements) /
            totalRequirements) *
            100
        )
      : 0;

  const testabilityPercentage = score;

  const issueRequirements = requirements.filter((req) => {
    const hasIssues = Array.isArray(req.issues) && req.issues.length > 0;
    const isDuplicate =
      req.duplicateStatus && req.duplicateStatus !== "Unique";
    const isInconsistent =
      req.consistency && req.consistency !== "Consistent";
    const needsAttention = req.status && req.status !== "Good";

    return hasIssues || isDuplicate || isInconsistent || needsAttention;
  });

  const llmResults = Array.isArray(llmAnalysis?.results)
    ? llmAnalysis.results
    : [];

  const metrics = [
    {
      label: "Ambiguity",
      value: ambiguityPercentage,
      description:
        ambiguityPercentage >= 80 ? "Good" : "Needs attention",
      icon: Search,
      tone: "violet",
      suffix: "%",
    },
    {
      label: "Completeness",
      value: completenessPercentage,
      description:
        completenessPercentage >= 80 ? "Good" : "Needs improvement",
      icon: ClipboardCheck,
      tone: "teal",
      suffix: "%",
    },
    {
      label: "Consistency",
      value: consistencyPercentage,
      description:
        consistencyPercentage >= 80 ? "Good" : "Needs attention",
      icon: CheckCircle2,
      tone: "blue",
      suffix: "%",
    },
    {
      label: "Testability",
      value: testabilityPercentage,
      description:
        testabilityPercentage >= 80 ? "Good" : "Needs improvement",
      icon: Target,
      tone: "orange",
      suffix: "%",
    },
  ];

  return (
    <div className="vr-page">
      <header className="vr-header">
        <Link to="/dashboard" className="vr-brand">
          <span className="vr-brand-icon">
            <ShieldCheck size={22} />
          </span>
          <span>
            Req<span>Validator</span>
          </span>
        </Link>

        <Link to={`/project/${projectId}`} className="vr-header-link">
          <ArrowLeft size={16} />
          Back to Project
        </Link>
      </header>

      <main className="vr-container">
        {/* Page heading */}
        <section className="vr-page-heading">
          <span className="vr-eyebrow">
            <Sparkles size={15} />
            VALIDATION REPORT
          </span>
          <h1>Requirement Validation Results</h1>
          <p>
            Review requirement quality, identify potential issues, and
            explore AI-powered explanations.
          </p>
        </section>

        {/* Overall score */}
        <section className="vr-score-panel">
          <div className="vr-score-copy">
            <span className="vr-score-label">OVERALL QUALITY SCORE</span>
            <div className="vr-score-number">
              {score}
              <span>/100</span>
            </div>
            <span className={`vr-score-status ${getStatusClass(scoreStatus)}`}>
              {getStatusIcon(scoreStatus)}
              {scoreStatus}
            </span>
            <p>
              {totalRequirements}{" "}
              {totalRequirements === 1 ? "requirement" : "requirements"}{" "}
              analyzed.
              {issueCount > 0
                ? ` ${issueCount} issue categories need attention.`
                : " Review the details below for your validation summary."}
            </p>
          </div>

          <div className="vr-score-visual">
            <div
              className="vr-score-ring"
              style={{ "--score": `${score * 3.6}deg` }}
            >
              <div className="vr-score-ring-inner">
                <strong>{score}%</strong>
                <span>Quality</span>
              </div>
            </div>
          </div>

          <div className="vr-score-footnote">
            <ShieldCheck size={16} />
            Score based on the validation summary returned by your backend.
          </div>
        </section>

        {/* Summary cards */}
        <section className="vr-overview-grid">
          <div className="vr-overview-card">
            <span className="vr-overview-icon teal">
              <FileText size={20} />
            </span>
            <span className="vr-overview-label">Total Requirements</span>
            <strong>{totalRequirements}</strong>
            <small>Analyzed by the validator</small>
          </div>

          <div className="vr-overview-card">
            <span className="vr-overview-icon violet">
              <CheckCircle2 size={20} />
            </span>
            <span className="vr-overview-label">Good Requirements</span>
            <strong>{goodRequirements}</strong>
            <small>Marked as good</small>
          </div>

          <div className="vr-overview-card">
            <span className="vr-overview-icon orange">
              <AlertTriangle size={20} />
            </span>
            <span className="vr-overview-label">Needs Improvement</span>
            <strong>{needsImprovement}</strong>
            <small>May need refinement</small>
          </div>

          <div className="vr-overview-card">
            <span className="vr-overview-icon red">
              <XCircle size={20} />
            </span>
            <span className="vr-overview-label">Poor Requirements</span>
            <strong>{poorRequirements}</strong>
            <small>Require closer review</small>
          </div>
        </section>

        <details className="vr-disclosure vr-section">
          <summary><span><small>OPTIONAL DETAIL</small><strong>Quality attribute breakdown</strong><em>Clarity, completeness, consistency and testability indicators</em></span><span className="vr-disclosure-count">View details</span></summary>
          <div className="vr-disclosure-body">
        {/* Quality metrics */}
        <section className="vr-section">
          <div className="vr-section-heading">
            <div>
              <span className="vr-eyebrow">QUALITY BREAKDOWN</span>
              <h2>Requirement quality attributes</h2>
              <p>Review the calculated indicators from your validation summary.</p>
            </div>
          </div>

          <div className="vr-metrics-grid">
            {metrics.map((metric) => {
              const Icon = metric.icon;

              return (
                <article className="vr-metric-card" key={metric.label}>
                  <div className="vr-metric-top">
                    <span className={`vr-metric-icon ${metric.tone}`}>
                      <Icon size={19} />
                    </span>
                    <span className="vr-metric-value">
                      {metric.value}
                      {metric.suffix}
                    </span>
                  </div>

                  <h3>{metric.label}</h3>
                  <p>{metric.description}</p>

                  <div
                    className="vr-progress-track"
                    role="progressbar"
                    aria-label={metric.label}
                    aria-valuenow={metric.value}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <span
                      className={`vr-progress-fill ${metric.tone}`}
                      style={{
                        width: `${Math.max(
                          0,
                          Math.min(100, metric.value)
                        )}%`,
                      }}
                    />
                  </div>
                </article>
              );
            })}
          </div>
        </section>

          </div>
        </details>

        {/* Detected issues */}
        <section className="vr-section">
          <div className="vr-section-heading vr-issue-heading">
            <div>
              <span className="vr-eyebrow">DETECTED ISSUES</span>
              <h2>Requirements that need attention</h2>
              <p>Review flagged requirements and any available suggestions.</p>
            </div>

            <span className="vr-count-badge">
              {issueRequirements.length} flagged
            </span>
          </div>

          {issueRequirements.length === 0 ? (
            <div className="vr-empty-card">
              <span className="vr-empty-icon">
                <CheckCircle2 size={27} />
              </span>
              <h3>No flagged requirements</h3>
              <p>
                No requirements were flagged by the current issue-filtering
                rules. Review the quality summary and AI analysis as needed.
              </p>
            </div>
          ) : (
            <div className="vr-issues-list">
              {issueRequirements.map((req, index) => (
                <article
                  className="vr-issue-card"
                  key={req.id ?? req.requirementId ?? index}
                >
                  <div className="vr-issue-top">
                    <div className="vr-issue-heading-copy">
                      <span className="vr-issue-alert-icon">
                        <AlertTriangle size={18} />
                      </span>
                      <div>
                        <span className="vr-issue-id">
                          {req.requirementId || `REQ-${index + 1}`}
                        </span>
                        <h3>Requirement needs review</h3>
                      </div>
                    </div>

                    <span className={`vr-status ${getStatusClass(req.status)}`}>
                      {getStatusIcon(req.status)}
                      {req.status || "Review"}
                    </span>
                  </div>

                  <div className="vr-original-requirement">
                    <span>ORIGINAL REQUIREMENT</span>
                    <p>{req.requirementText || "No requirement text available."}</p>
                  </div>

                  {Array.isArray(req.issues) && req.issues.length > 0 && (
                    <div className="vr-detail-block">
                      <h4>
                        <AlertTriangle size={16} />
                        Detected issues
                      </h4>
                      <ul>
                        {req.issues.map((issue, issueIndex) => (
                          <li key={issueIndex}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(req.suggestions) &&
                    req.suggestions.length > 0 && (
                      <div className="vr-suggestion-block">
                        <h4>
                          <Lightbulb size={16} />
                          Suggested improvements
                        </h4>
                        <ul>
                          {req.suggestions.map((suggestion, suggestionIndex) => (
                            <li key={suggestionIndex}>{suggestion}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                  <div className="vr-issue-metadata">
                    <span>
                      Quality score:{" "}
                      {req.qualityScore !== null &&
                      req.qualityScore !== undefined
                        ? `${req.qualityScore}/100`
                        : "Not scored"}
                    </span>
                    <span>Clarity: {req.clarity || "—"}</span>
                    <span>Testability: {req.testability || "—"}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <details className="vr-disclosure vr-section">
          <summary><span><small>VALIDATION DETAILS</small><strong>More analysis statistics</strong><em>Duplicates, inconsistencies and requirement status counts</em></span><span className="vr-disclosure-count">View details</span></summary>
          <div className="vr-disclosure-body">
        {/* Detailed counts */}
        <section className="vr-section">
          <div className="vr-section-heading">
            <div>
              <span className="vr-eyebrow">VALIDATION SUMMARY</span>
              <h2>Analysis statistics</h2>
              <p>Counts reported by the backend validation summary.</p>
            </div>
          </div>

          <div className="vr-statistics-grid">
            {[
              { label: "Duplicate requirements", value: duplicateRequirements },
              {
                label: "Inconsistent requirements",
                value: inconsistentRequirements,
              },
              { label: "Needs improvement", value: needsImprovement },
              { label: "Poor requirements", value: poorRequirements },
            ].map((item) => (
              <div className="vr-statistic-row" key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </section>

          </div>
        </details>

        <section className="vr-section vr-ai-entry">
          <div className="vr-section-heading">
            <div>
              <span className="vr-eyebrow">DETAILED SRS REVIEW</span>
              <h2>AI Analysis</h2>
              <p>Open the complete analysis workspace to explore the report, requirement-level findings, quality assessment, cross-requirement checks, recommendations, offline guide and on-device Qwen tools.</p>
            </div>
            <button
              type="button"
              className="vr-primary-button"
              onClick={() => setShowAiAnalysis((open) => !open)}
              aria-expanded={showAiAnalysis}
              aria-controls="ai-analysis-workspace"
            >
              <Sparkles size={16} />
              {showAiAnalysis ? "Hide AI Analysis" : "Open AI Analysis"}
              <ArrowRight size={16} />
            </button>
          </div>
        </section>

        {showAiAnalysis && (
          <div id="ai-analysis-workspace">
            <ResultsWorkspace
              projectName={projectInfo?.name}
              items={llmResults}
              report={llmAnalysis?.document_report || projectInfo?.analysisReport || null}
              engineState={{ loading: llmLoading, error: llmError || llmFallbackNotice }}
              onRerun={runLlmAnalysis}
              offlineAnswer={(question) => buildOfflineSrsAnswer(question, llmResults.length ? llmResults : requirements.map((item) => ({
                requirement_id: item.requirementId,
                requirement: item.requirementText || "",
                analysis: { quality_score: item.qualityScore, issues: item.issues || [], suggested_rewrite: "" },
              })), { totalRequirements, score, scoreStatus, goodRequirements, needsImprovement, poorRequirements, duplicateRequirements, inconsistentRequirements })}
            />
          </div>
        )}

        {/* Footer actions */}
        <div className="vr-bottom-actions">
          <Link
            to={`/project/${projectId}`}
            className="vr-secondary-button"
          >
            <ArrowLeft size={16} />
            Back to Project
          </Link>

          <Link
            to={`/upload?projectId=${encodeURIComponent(projectId)}`}
            className="vr-primary-button"
          >
            Analyze Another
            <ArrowRight size={16} />
          </Link>
        </div>

        <footer className="vr-footer">
          <span>
            <ShieldCheck size={15} />
            ReqValidator
          </span>
          <span>AI Software Requirement Validator · Capstone Project</span>
        </footer>
      </main>
    </div>
  );
}

export default ValidationResults;
