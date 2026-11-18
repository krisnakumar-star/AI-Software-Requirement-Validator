# AI Software Requirement Validator

A web application for managing and reviewing Software Requirements Specifications (SRS), with a lightweight Python analysis service.

## Analysis service

The FastAPI service provides:
- Multi-label classification for functional, non-functional quality attributes, technical constraints, user stories, business rules, data, interface/integration, privacy and compliance requirements.
- Separate clarity, completeness, testability, atomicity and consistency indicator scores.
- Attribute-specific checks for performance, security, availability, reliability, usability, compatibility, maintainability, privacy, integrations, data rules and standards compliance.
- Detection of vague wording, missing actors/actions, unclear references, open-ended scope, compound requirements, missing triggers/outcomes, weak measurable targets and missing exception paths.
- Severity-coded findings with recommendations, explanations, and cautious rewrite guidance that does not invent stakeholder thresholds.
- An expert-style review report with an executive summary, risk verdict, strengths, dimension-by-dimension assessment, detailed reasoning, stakeholder clarification questions, draft acceptance criteria, illustrative positive/negative/regression test scenarios, and a prioritized improvement plan.
- Batch-level category summaries, average score, possible duplicate detection and possible cross-requirement conflicts.
- Existing single-analysis response fields are preserved; detailed findings are exposed separately for richer clients.

**Implementation note:** the current analyzer is a deterministic, model-free NLP/heuristic engine. It does not download model weights, call an external AI provider, require paid API credits, or claim to be a generative LLM. Its score is a textual quality indicator and should be reviewed by a requirements engineer.

## Render deployment

Create a Python Web Service with Root Directory `ai-service`.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Runtime: Python 3.11 or newer.
- Environment variable: `SRS_API_KEY` (private random value).
- Set the exact same value in Spring Boot as `LLM_API_KEY`.
- No model download, persistent model disk, GPU, JarvisClaw account, or paid AI provider is required.

Keep the existing Spring Boot configuration:
- `LLM_API_URL=https://<your-ai-service>.onrender.com`
- `LLM_API_KEY=<same value as SRS_API_KEY>`

## Local development

```bash
cd ai-service
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set `SRS_API_KEY`, then run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

The API endpoints are `GET /`, `GET /health`, `POST /analyze`, and `POST /analyze-batch`. The single and batch response structures retain the fields used by the existing backend.

## Security

Never commit API keys, database credentials, JWT secrets, or production environment files. Keep the AI service private behind its internal API key. The browser must communicate through Spring Boot and must never receive service credentials.
