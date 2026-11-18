# AI Software Requirement Validator

An AI-powered web application designed to help users validate software requirements, identify inconsistencies and duplicates, and analyze Software Requirements Specification (SRS) documents.

## Overview

The AI Software Requirement Validator provides a centralized platform for managing software projects and reviewing their requirements. It combines a React frontend, a Spring Boot backend, and a Python-based AI service.

## Features

- **User Authentication:** Register and log in securely.
- **Project Management:** Create, view, and manage software requirement projects.
- **SRS Upload:** Upload Software Requirements Specification documents.
- **Requirement Management:** Add and manage individual software requirements.
- **Requirement Validation:** Check requirements for potential issues.
- **Duplicate Detection:** Identify potentially duplicate requirements.
- **Consistency Detection:** Help identify inconsistencies between requirements.
- **AI-Powered Analysis:** Analyze requirements using the configured language-model service.
- **Validation Results:** Review validation results and analysis for your project.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, Vite, JavaScript, CSS |
| Backend | Java, Spring Boot, Maven |
| AI Service | Python |
| Database | MongoDB |
| Authentication | JWT |
| Version Control | Git and GitHub |

## Project Structure

```text
AI-Software-Requirement-Validator/
├── ai-service/
│   └── main.py
├── backend/
│   ├── pom.xml
│   └── src/
│       └── main/
│           ├── java/
│           └── resources/
├── frontend/
│   ├── package.json
│   └── src/
├── .gitignore
└── README.md
```

## Application Screenshots

### Home Page

![Home Page](screenshots/home.png)

### Dashboard

![Dashboard](screenshots/dashboard.png)

### Validation Results

![Validation Results](screenshots/validation-result.png)
## Prerequisites

Install the following before running the application:

- Node.js and npm
- Java and Maven (or use the included Maven wrapper)
- Python 3
- MongoDB
- Access to the configured language-model API, if required for AI analysis

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Rakshali-p09/AI-Software-Requirement-Validator.git
cd AI-Software-Requirement-Validator
```

### 2. Start MongoDB

Ensure your MongoDB server is running and the database connection is configured correctly.

The backend's default database URI is:

```text
mongodb://localhost:27017/requirement_validator
```

### 3. Configure and run the AI service

The FastAPI service calls JarvisClaw's OpenAI-compatible Chat Completions API at `https://api.jarvisclaw.ai/v1/chat/completions`.

Create `ai-service/.env` from `.env.example` and configure:

- `SRS_API_KEY`: a private random key shared with the backend's `LLM_API_KEY`.
- `JARVISCLAW_API_KEY`: your JarvisClaw API key (starts with `sk-`). This provider credential is different from `SRS_API_KEY`.
- `LLM_MODEL`: a model identifier available in your JarvisClaw account; `auto` uses the provider's smart router.

Never commit either key. In Render, set these as environment variables on the AI service. The backend must have `LLM_API_KEY` equal to the AI service's `SRS_API_KEY`.

```powershell
cd ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uvicorn main:app --host 0.0.0.0 --port 8001
```

Verify `/health` reports both internal authentication and provider API key configuration before testing a real `/analyze` request.

### 4. Run Spring Boot

In a separate PowerShell terminal, set `LLM_API_KEY` to the same private value as `SRS_API_KEY`. Set `JWT_SECRET` to the existing application's stable secret. Configure `MONGODB_URI` if MongoDB is not using the local default. Never rotate the JWT secret casually because existing sessions depend on it.

```powershell
$env:LLM_API_URL = "http://localhost:8001"
$env:LLM_API_KEY = "same-value-as-SRS_API_KEY"
$env:LLM_API_CONNECT_TIMEOUT = "10000"
$env:LLM_API_READ_TIMEOUT = "120000"
cd backend
.\mvnw.cmd spring-boot:run
```

Spring Boot listens on port `8080` by default. The authenticated project analysis endpoint calls FastAPI and stores returned analyses on the existing requirement records.

### 5. Run React

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite. React only sends authenticated requests to Spring Boot; it never receives either AI service key.

### 6. Start MongoDB

If MongoDB is installed as a Windows service, run PowerShell as an account permitted to start it:

```powershell
Start-Service MongoDB
```

The backend uses `mongodb://localhost:27017/requirement_validator` by default. Set `MONGODB_URI` for a different local or hosted database.

## Security Notes

- Never commit API keys, passwords, or production secrets.
- Use environment variables for sensitive configuration.
- Use a unique, strong JWT secret.
- Configure CORS and database access appropriately before deployment.
- Do not expose private documents or uploaded user data in a public repository.

## Future Improvements

- More advanced requirement quality checks.
- Improved reporting and validation summaries.
- Enhanced requirement traceability.
- Deployment and integration testing.

## Author

**Rakshali Patidar**

GitHub: [Rakshali-p09](https://github.com/Rakshali-p09)

## License

No license has been specified yet. All rights are reserved by default unless a license is added to this repository.
