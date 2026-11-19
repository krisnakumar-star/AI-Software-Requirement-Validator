
import { useEffect, useState } from "react";
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
  BrainCircuit,
  Lightbulb,
  Target,
  Search,
  ClipboardCheck,
} from "lucide-react";
import { apiUrl } from "../config/api";

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
  const [localModelLoading, setLocalModelLoading] = useState(false);
  const [localModelProgress, setLocalModelProgress] = useState("");
  const [localModelError, setLocalModelError] = useState("");
  const [localModelReport, setLocalModelReport] = useState("");
  const [expandedInsightIds, setExpandedInsightIds] = useState({});
  const [reviewAction, setReviewAction] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");

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

  const runLlmAnalysis = async () => {
    const token = localStorage.getItem("token");

    if (!token) {
      navigate("/login");
      return;
    }

    setLlmLoading(true);
    setLlmError("");
    setLlmFallbackNotice("");

    try {
      const response = await fetch(
        apiUrl(`/api/llm/analyze/project/${encodeURIComponent(projectId)}`),
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const responseText = await response.text();
      let data = {};

      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch {
        data = { message: responseText };
      }

      if (!response.ok) {
        throw new Error(
          data.message || "Unable to run AI analysis."
        );
      }

      if (!isValidAnalysisResponse(data)) {
        throw new Error(
          "The AI service returned an incomplete or invalid analysis response. Please retry."
        );
      }

      setLlmAnalysis(data);
    } catch (err) {
      console.error("AI analysis error:", err);

      // Keep the results page useful when the hosted FastAPI service is sleeping
      // or temporarily unavailable. Reuse only analysis already saved by the backend.
      const savedResults = requirements
        .filter((item) => item.requirementText && item.aiAnalysis)
        .map((item) => {
          const saved = item.aiAnalysis || {};
          const asText = (value) => typeof value === "string" ? value : "";
          const asList = (value) => Array.isArray(value)
            ? value.filter((entry) => typeof entry === "string")
            : [];
          return {
            requirement_id: item.requirementId,
            requirement: item.requirementText,
            analysis: {
              quality_score: Number.isInteger(saved.quality_score)
                ? saved.quality_score
                : Math.max(0, Math.min(100, Number(item.qualityScore) || 0)),
              classification: asText(saved.classification) || asText(item.classification) || "Previously saved analysis",
              clarity: asText(saved.clarity) || asText(item.clarity),
              completeness: asText(saved.completeness) || asText(item.completeness),
              testability: asText(saved.testability) || asText(item.testability),
              suggested_rewrite: asText(saved.suggested_rewrite),
              explanation: asText(saved.explanation) || "Showing the analysis previously saved for this requirement. The live analysis service could not be reached.",
              ambiguities: asList(saved.ambiguities),
              missing_information: asList(saved.missing_information),
              issues: asList(saved.issues).length ? asList(saved.issues) : asList(item.issues),
            },
          };
        });

      if (savedResults.length > 0) {
        setLlmAnalysis({
          status: "saved-fallback",
          total_requirements: savedResults.length,
          results: savedResults,
        });
        setLlmFallbackNotice(
          "Live cloud analysis is temporarily unavailable (HTTP 502/upstream error). Showing previously saved analysis instead. You can still run the free local Qwen review below."
        );
        setLlmError("");
      } else {
        setLlmError(
          err.message === "Failed to fetch"
            ? "Cannot connect to the backend AI service. Check the Render AI service and backend configuration."
            : err.message || "Cloud AI analysis could not be completed. Try the free local LLM review below."
        );
      }
    } finally {
      setLlmLoading(false);
    }
  };

  const runFreeLocalModelReview = async () => {
    setLocalModelLoading(true);
    setLocalModelError("");
    setLocalModelReport("");
    setLocalModelProgress("Loading the open-weight Qwen model into your browser. The first download may take a few minutes.");

    try {
      // Keep model code out of the initial bundle; this module exists on the current main branch.
      const { generateSrsReview } = await import("../services/localSrsModel.js");
      const items = llmResults.length > 0
        ? llmResults
        : requirements.map((item) => ({
            requirement: item.requirementText || "",
            analysis: {
              issues: item.issues || [],
              suggestions: item.suggestions || [],
              quality_score: item.qualityScore,
              classification: item.classification || "Not classified",
            },
          })).filter((item) => item.requirement.trim());

      if (items.length === 0) {
        throw new Error("No requirement text is available for review.");
      }

      const selected = items.slice(0, 8);
      setLocalModelProgress("The local model is reviewing requirement meaning, gaps, risks, and test ideas...");
      const report = await generateSrsReview(selected, (message) => setLocalModelProgress(message));
      setLocalModelReport(report);
      if (items.length > selected.length) {
        setLocalModelProgress(`Reviewed the first ${selected.length} requirements. Run additional batches for the remaining requirements.`);
      } else {
        setLocalModelProgress("Review completed locally in your browser. No API key was used.");
      }
    } catch (err) {
      console.error("Local open model review failed:", err);
      setLocalModelError(err.message || "The local model could not be loaded. Try a modern Chrome or Edge browser with WebGPU support.");
      setLocalModelProgress("");
    } finally {
      setLocalModelLoading(false);
    }
  };


  const sendChatMessage = async (promptText = chatInput) => {
    const question = String(promptText || "").trim();
    if (!question || chatLoading) return;
    const userMessage = { role: "user", content: question };
    const nextHistory = [...chatMessages, userMessage];
    setChatMessages(nextHistory);
    setChatInput("");
    setChatLoading(true);
    setChatError("");
    try {
      const { generateSrsChatReply } = await import("../services/localSrsModel.js");
      const items = llmResults.length > 0 ? llmResults : requirements.map((item) => ({
        requirement: item.requirementText || "",
        analysis: {
          quality_score: item.qualityScore,
          classification: item.classification,
          issues: item.issues || [],
          suggestions: item.suggestions || [],
        },
      })).filter((item) => item.requirement.trim());
      if (!items.length) throw new Error("No project requirements are available to discuss.");
      const reply = await generateSrsChatReply(items, chatMessages, question, setLocalModelProgress);
      setChatMessages((current) => [...current, { role: "assistant", content: reply }]);
    } catch (err) {
      setChatMessages((current) => current.filter((message, index) => !(index === current.length - 1 && message === userMessage)));
      setChatInput(question);
      setChatError(err.message || "The local assistant could not answer. Please try again.");
    } finally {
      setChatLoading(false);
      setLocalModelProgress("");
    }
  };

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

  const quickReviewSummary = [
    `Project validation checked ${totalRequirements} requirements and produced an average quality score of ${score}/100 (${scoreStatus}).`,
    `${goodRequirements} requirements are marked good, ${needsImprovement} need improvement, and ${poorRequirements} are poor.`,
    `${duplicateRequirements} duplicate and ${inconsistentRequirements} inconsistent requirements were detected.`,
    issueRequirements.length
      ? `Prioritize the ${issueRequirements.length} flagged requirements and resolve their listed issues before finalizing the SRS.`
      : "No requirements were flagged by the current issue-filtering rules. Review the detailed findings before sign-off.",
  ].join(" ");

  const basicReviewQuestions = [
    { question: "What is this project expected to do?", answer: requirements[0]?.requirementText ? `Start with this requirement: “${requirements[0].requirementText}”. Explain the user need and expected outcome in simple terms.` : "Describe the main purpose of the system, its users, and the problem it solves." },
    { question: "Who will use the system?", answer: "Identify each user role or external system that interacts with the product, and state what each one is allowed to do." },
    { question: "What are the main functions?", answer: `There are ${requirements.length} requirements in this project. Review each one as a distinct function or system constraint and group related requirements into features.` },
    { question: "How can we test a requirement?", answer: "Write a test with a clear starting condition, user action or input, and an observable expected result. Avoid vague words unless they have measurable criteria." },
  ];

  const importantReviewQuestions = [
    { question: "Which requirements are most at risk?", answer: issueRequirements.length ? issueRequirements.slice(0, 5).map((req, i) => `${req.requirementId || `REQ-${i + 1}`}: ${(req.issues || []).join("; ") || req.status || "Needs review"}`).join("\n") : "No flagged requirements were found by the current issue-filtering rules. Manually review critical and security-related requirements." },
    { question: "What details are missing?", answer: llmResults.flatMap((item) => (item.analysis?.missing_information || []).map((entry) => `${item.requirement_id || "Requirement"}: ${entry}`)).slice(0, 8).join("\n") || "Confirm the actor, trigger, expected result, constraints, and measurable acceptance criteria for each requirement." },
    { question: "What should be fixed before approval?", answer: `${poorRequirements + needsImprovement} requirements are currently marked poor or needing improvement. Resolve ambiguity, add measurable acceptance criteria, check dependencies and conflicts, and retest the revised requirements.` },
    { question: "Are the requirements measurable and verifiable?", answer: "For each requirement, define measurable thresholds, boundary cases, failure behavior, and evidence that will prove it has been satisfied." },
  ];

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

        {/* Optional AI analysis */}
        <section className="vr-section vr-ai-section">
          <div className="vr-section-heading">
            <div>
              <span className="vr-eyebrow">AI-POWERED REVIEW</span>
              <h2>Detailed AI analysis</h2>
              <p>
                Run the integrated AI analysis to view explanations,
                quality-attribute findings, and recommendations.
              </p>
            </div>

            <span className="vr-ai-heading-icon">
              <BrainCircuit size={24} />
            </span>
          </div>

          <div className="vr-ai-prompt">
            <div className="vr-ai-prompt-icon">
              <BrainCircuit size={24} />
            </div>
            <div className="vr-ai-prompt-copy">
              <h3>Free open-weight LLM · Runs in your browser</h3>
              <p>
                Load Qwen2.5 0.5B Instruct locally using WebAssembly/WebGPU.
                No provider API key or paid inference endpoint is required.
                The first model download can be large and generation speed depends on your device.
              </p>
            </div>
            <button
              type="button"
              className="vr-primary-button"
              onClick={runFreeLocalModelReview}
              disabled={localModelLoading}
            >
              {localModelLoading ? (
                <>
                  <LoaderCircle size={17} className="vr-spinner" />
                  Loading model...
                </>
              ) : (
                <>
                  <BrainCircuit size={17} />
                  Run free local LLM review
                </>
              )}
            </button>
          </div>

          {localModelProgress && (
            <div className="vr-ai-explanation" role="status">{localModelProgress}</div>
          )}
          {localModelError && (
            <div className="vr-error-banner" role="alert">
              <AlertTriangle size={18} />
              <span>{localModelError}</span>
            </div>
          )}
          {localModelReport && (
            <article className="vr-issue-card vr-ai-result-card">
              <div className="vr-ai-overall">
                <span>OPEN-WEIGHT MODEL REVIEW</span>
                <strong>Qwen2.5 0.5B Instruct · Local browser inference</strong>
              </div>
              <pre className="vr-ai-explanation" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>
                {localModelReport}
              </pre>
            </article>
          )}

          {!llmAnalysis && (
            <div className="vr-ai-prompt">
              <div className="vr-ai-prompt-icon">
                <Sparkles size={24} />
              </div>
              <div className="vr-ai-prompt-copy">
                <h3>Explore deeper requirement insights</h3>
                <p>
                  The AI analysis can provide attribute-level findings
                  and recommendations when returned by your AI service.
                </p>
              </div>

              <button
                type="button"
                className="vr-primary-button"
                onClick={runLlmAnalysis}
                disabled={llmLoading}
              >
                {llmLoading ? (
                  <>
                    <LoaderCircle size={17} className="vr-spinner" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <BrainCircuit size={17} />
                    Analyze with AI
                  </>
                )}
              </button>
            </div>
          )}

          {llmFallbackNotice && (
            <div className="vr-ai-explanation" role="status">
              {llmFallbackNotice}
            </div>
          )}
          {llmError && (
            <div className="vr-error-banner" role="alert">
              <AlertTriangle size={18} />
              <span>{llmError}</span>
              <button
                type="button"
                onClick={runLlmAnalysis}
                disabled={llmLoading}
              >
                Try again
              </button>
            </div>
          )}

          {llmAnalysis && (
            <div className="vr-ai-results">
              <div className="vr-ai-summary">
                <span className="vr-ai-summary-icon">
                  <CheckCircle2 size={21} />
                </span>
                <div>
                  <h3>AI analysis response received</h3>
                  <p>
                    Requirements reported by the AI service:{" "}
                    {llmAnalysis.total_requirements ?? llmResults.length}
                  </p>
                </div>
                <button
                  type="button"
                  className="vr-secondary-button"
                  onClick={runLlmAnalysis}
                  disabled={llmLoading}
                >
                  {llmLoading ? (
                    <LoaderCircle size={15} className="vr-spinner" />
                  ) : (
                    <RefreshCw size={15} />
                  )}
                  Run again
                </button>
              </div>

              {llmResults.length === 0 ? (
                <div className="vr-empty-card">
                  <p>
                    The AI service returned no individual requirement
                    analysis results.
                  </p>
                </div>
              ) : (
                <div className="vr-issues-list">
                  {llmResults.map((result, index) => {
                    const analysis = result.analysis || {};

                    return (
                      <article
                        className="vr-issue-card vr-ai-result-card"
                        key={result.requirement_id ?? index}
                      >
                        <div className="vr-original-requirement">
                          <span>
                            REQUIREMENT{" "}
                            {result.requirement_id || `#${index + 1}`}
                          </span>
                          <p>{result.requirement || "No text provided."}</p>
                        </div>

                        <div className="vr-ai-overall">
                          <span>Quick insight</span>
                          <strong>{analysis.quality_score}/100 · {analysis.classification}</strong>
                        </div>
                        <div className="vr-issue-metadata">
                          <span>Clarity: {analysis.clarity || "—"}</span>
                          <span>Completeness: {analysis.completeness || "—"}</span>
                          <span>Testability: {analysis.testability || "—"}</span>
                        </div>
                        <p className="vr-ai-explanation">
                          {analysis.explanation
                            ? `${analysis.explanation.slice(0, 220)}${analysis.explanation.length > 220 ? "…" : ""}`
                            : "Review the detailed findings for more information."}
                        </p>
                        <button
                          type="button"
                          className="vr-secondary-button"
                          onClick={() => setExpandedInsightIds((current) => ({
                            ...current,
                            [result.requirement_id ?? index]: !current[result.requirement_id ?? index],
                          }))}
                          aria-expanded={Boolean(expandedInsightIds[result.requirement_id ?? index])}
                        >
                          {expandedInsightIds[result.requirement_id ?? index]
                            ? "Hide full insights"
                            : "View full insights"}
                        </button>

                        {expandedInsightIds[result.requirement_id ?? index] && (
                          <div className="vr-ai-full-insights">
                            <div className="vr-issue-metadata">
                              <span>Feasibility: {analysis.feasibility || "—"}</span>
                              <span>Consistency: {analysis.consistency || "—"}</span>
                            </div>
                            {analysis.explanation && (
                              <p className="vr-ai-explanation">{analysis.explanation}</p>
                            )}
                            {[
                              ["Ambiguities", analysis.ambiguities],
                              ["Missing information", analysis.missing_information],
                              ["Issues", analysis.issues],
                            ].map(([title, items]) => Array.isArray(items) && items.length > 0 && (
                              <div className="vr-detail-block" key={title}>
                                <h4><AlertTriangle size={16} />{title}</h4>
                                <ul>{items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul>
                              </div>
                            ))}
                            {analysis.suggested_rewrite && (
                              <div className="vr-suggestion-block">
                                <h4><Lightbulb size={16} />Suggested rewrite</h4>
                                <p>{analysis.suggested_rewrite}</p>
                              </div>
                            )}
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </section>

        {/* Contextual project assistant powered by the local open-weight model */}
        <section className="vr-section vr-quick-review">
          <div className="vr-section-heading">
            <div>
              <span className="vr-eyebrow">PROJECT ASSISTANT</span>
              <h2>Ask about your SRS</h2>
              <p>Ask questions about your requirements, validation scores, detected issues, or how to improve the SRS. Answers are generated locally in your browser.</p>
            </div>
            <span className="vr-ai-heading-icon"><BrainCircuit size={24} /></span>
          </div>
          <div className="vr-quick-review-buttons" style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "16px" }}>
            {[
              "Summarize my SRS",
              "What are the most important issues?",
              "How can I improve the poor requirements?",
              "Give me basic questions about this project",
              "What should I fix first?",
            ].map((prompt) => (
              <button key={prompt} type="button" className="vr-secondary-button" disabled={chatLoading} onClick={() => sendChatMessage(prompt)}>{prompt}</button>
            ))}
          </div>
          <div className="vr-issue-card vr-chat-panel">
            <div className="vr-ai-overall">
              <span>LOCAL AI ASSISTANT</span>
              <strong>Qwen2.5 0.5B Instruct · No paid API required</strong>
            </div>
            <div className="vr-chat-messages" aria-live="polite" style={{ display: "flex", flexDirection: "column", gap: "12px", maxHeight: "440px", overflowY: "auto", padding: "12px 0" }}>
              {chatMessages.length === 0 && (
                <p className="vr-ai-explanation">Hi! I can explain your validation report, summarize the SRS, identify high-priority fixes, suggest requirement improvements, and answer basic or important project questions. Choose a suggested question or type your own.</p>
              )}
              {chatMessages.map((message, index) => (
                <div key={index} style={{ alignSelf: message.role === "user" ? "flex-end" : "stretch", maxWidth: message.role === "user" ? "85%" : "100%", padding: "12px 14px", borderRadius: "12px", background: message.role === "user" ? "var(--primary-color, #e9e7ff)" : "var(--card-background, rgba(127,127,127,0.08))", color: "inherit", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                  <strong style={{ display: "block", fontSize: "12px", marginBottom: "5px" }}>{message.role === "user" ? "You" : "ReqValidator assistant"}</strong>
                  {message.content}
                </div>
              ))}
              {chatLoading && <p className="vr-ai-explanation" role="status"><LoaderCircle size={15} className="vr-spinner" /> Preparing an answer on this device...</p>}
            </div>
            {chatError && <div className="vr-error-banner" role="alert"><AlertTriangle size={16} />{chatError}</div>}
            <form onSubmit={(event) => { event.preventDefault(); sendChatMessage(); }} style={{ display: "flex", gap: "10px", alignItems: "center", marginTop: "12px" }}>
              <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask something about your SRS..." aria-label="Ask a question about your SRS" disabled={chatLoading} style={{ flex: 1, minWidth: 0 }} />
              <button type="submit" className="vr-primary-button" disabled={chatLoading || !chatInput.trim()}>{chatLoading ? <LoaderCircle size={16} className="vr-spinner" /> : <ArrowRight size={16} />} Send</button>
            </form>
            <p className="vr-ai-explanation" style={{ fontSize: "12px" }}>The first message may take longer while the model downloads. Model speed depends on your device. Verify important recommendations before using them as final requirements.</p>
          </div>
        </section>

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
