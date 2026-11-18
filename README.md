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



## Free open-weight LLM in the browser

The Validation Results page includes an optional local-model review using `onnx-community/Qwen2.5-0.5B-Instruct` through Transformers.js. The model runs on the visitor's device using WebGPU when available and falls back to WASM/CPU. It does not require a provider API key or paid inference API. Model files are downloaded from Hugging Face on first use and may be cached by the browser; first load can take time and performance depends on the user's hardware. The existing FastAPI rule-based analysis remains available and supplies deterministic checks and scores. The small 0.5B model generates additional natural-language explanations, clarification questions, draft acceptance criteria and test ideas; it should not be treated as an expert substitute or a guarantee of correctness.

This browser-side option avoids putting LLM weights on the Render free service. Render free web services have resource and ephemeral-filesystem limitations; they also spin down when idle. See the [Render free service limitations](https://render.com/docs/free). Transformers.js runs supported models in the browser with ONNX Runtime and WebGPU/WASM; see [Transformers.js documentation](https://huggingface.co/docs/transformers.js/en/index) and the [Qwen2.5 0.5B ONNX model card](https://huggingface.co/onnx-community/Qwen2.5-0.5B-Instruct).

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
