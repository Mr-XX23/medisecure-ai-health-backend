# 🏥 Vaidya - AI Health Assistant

**Vaidya** is an intelligent multi-agent healthcare orchestration system that provides comprehensive health assistance through specialized AI agents for symptom checking, medical history analysis, medication safety, preventive care, and healthcare provider search.

## 🎯 What is Vaidya?

Vaidya acts as the **root supervisor agent** that intelligently routes user requests to specialized sub-agents:

- **Symptom Analyst**: Medical symptom checking and triage
- **History Agent**: Medical history analysis via FHIR
- **Preventive & Chronic Care Agent**: Preventive care recommendations
- **Drug Interaction Agent**: Medication safety analysis
- **Provider Locator Agent**: Healthcare provider search

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- MongoDB
- GitHub Token (for AI models)
- Google Maps API Key (optional, for provider search)

### Installation

```powershell
# 1. Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
# Create .env file with:
GITHUB_TOKEN=your_github_token
MONGODB_URL=mongodb://localhost:27017
GOOGLE_MAPS_API_KEY=your_google_maps_key  # Optional
```

### Start the Server

```powershell
# Development mode with auto-reload
uvicorn main:app --reload --port 8005

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8005
```

Server will be available at: `http://localhost:8005`

API Documentation: `http://localhost:8005/docs`

## 📡 API Endpoints

### Core Vaidya API

All interactions go through Vaidya, which intelligently routes to the appropriate specialist agent.

#### **Start a New Session**

```http
POST /api/v1/vaidya/start
```

**Response:**
```json
{
  "session_id": "uuid",
  "message": "Hello! I'm Vaidya, your AI health assistant...",
  "status": "active"
}
```

#### **Send a Message**

```http
POST /api/v1/vaidya/message
Content-Type: application/json

{
  "session_id": "uuid",
  "message": "I have a headache for 3 days"
}
```

**Response:** Server-Sent Events (SSE) stream

#### **Get Session Details**

```http
GET /api/v1/vaidya/session/{session_id}
```

#### **Get Assessment History**

```http
GET /api/v1/vaidya/history?limit=10&offset=0
```

## 💬 Usage Examples

### Example 1: Symptom Check

```powershell
# Start session
$start = Invoke-RestMethod -Uri "http://localhost:8005/api/v1/vaidya/start" -Method POST
$sessionId = $start.session_id

# Send symptom message
$body = @{
    session_id = $sessionId
    message = "I have chest pain for 3 days, moderate severity"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8005/api/v1/vaidya/message" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

**Vaidya automatically:**
1. Detects symptom check intent
2. Routes to Symptom Analyst
3. Collects Golden 4 (location, duration, severity, triggers)
4. Performs triage
5. Returns comprehensive assessment

### Example 2: Find Healthcare Provider

```powershell
$body = @{
    session_id = $sessionId
    message = "Find a cardiologist near me at 40.7128, -74.0060"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8005/api/v1/vaidya/message" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

**Vaidya automatically:**
1. Detects provider search intent
2. Routes to Provider Locator Agent
3. Searches nearby providers
4. Returns ranked list with ratings

### Example 3: Medication Safety Check

```powershell
$body = @{
    session_id = $sessionId
    message = "Can I take aspirin with warfarin?"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8005/api/v1/vaidya/message" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

**Vaidya automatically:**
1. Detects medication safety intent
2. Routes to Drug Interaction Agent
3. Analyzes interactions
4. Returns safety assessment

## 🧪 Testing

### Run API Tests

```powershell
# Comprehensive Vaidya API test
cd tests
./test_all_apis_fixed.ps1
```

### Run Python Tests

```powershell
# Install pytest
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_vaidya_supervisor.py -v
```

## 📚 Documentation

Detailed documentation is available in the `/docs` folder:

- **[VAIDYA_README.md](docs/VAIDYA_README.md)** - Vaidya overview and quick reference
- **[VAIDYA_QUICKSTART.md](docs/VAIDYA_QUICKSTART.md)** - Quick start guide with examples
- **[VAIDYA_SUPERVISOR.md](docs/VAIDYA_SUPERVISOR.md)** - Complete implementation guide
- **[VAIDYA_IMPLEMENTATION_SUMMARY.md](docs/VAIDYA_IMPLEMENTATION_SUMMARY.md)** - Architecture summary

### Feature-Specific Docs

- **[HISTORY_AGENT_IMPLEMENTATION.md](docs/HISTORY_AGENT_IMPLEMENTATION.md)** - Medical history integration
- **[DRUG_INTERACTION_IMPLEMENTATION.md](docs/DRUG_INTERACTION_IMPLEMENTATION.md)** - Medication safety
- **[PREVENTIVE_CARE_IMPLEMENTATION.md](docs/PREVENTIVE_CARE_IMPLEMENTATION.md)** - Preventive care
- **[PROVIDER_LOCATOR_IMPLEMENTATION.md](docs/PROVIDER_LOCATOR_IMPLEMENTATION.md)** - Provider search

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         User / Frontend                 │
└──────────────┬──────────────────────────┘
               │
        /api/v1/vaidya/*
               │
        ┌──────▼──────┐
        │   Vaidya    │ (Root Supervisor)
        │ Supervisor  │◄────────┐
        └──────┬──────┘         │
               │                │
    ┌──────────┴───────────┐    │
    │  Intent Detection    │    │
    │  & Smart Routing     │    │
    └──────────┬───────────┘    │
               │                │
    ┌──────────┴──────────┐     │
    ▼          ▼          ▼     │
┌────────┐ ┌────────┐ ┌────────┐
│Symptom │ │History │ │Provider│
│Analyst │ │ Agent  │ │Locator │
└───┬────┘ └───┬────┘ └───┬────┘
    │          │          │
┌───▼────┐ ┌──▼─────┐ ┌──▼─────┐
│ Drug   │ │Prevent.│ │ Final  │
│Interact│ │ Care   │ │Respond.│
└───┬────┘ └───┬────┘ └───┬────┘
    │          │          │
    └──────────┴──────────┘
               │
         Return to Vaidya ─────┘
```

## 🔧 Configuration

### Environment Variables

```env
# Required
GITHUB_TOKEN=ghp_xxxxx
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=ai_physician

# Optional
GOOGLE_MAPS_API_KEY=your_api_key
ENVIRONMENT=development
LOG_LEVEL=INFO
AI_PHYSICIAN_PORT=8005

# FHIR Configuration
FHIR_ENABLED=true
FHIR_USE_MOCK=false
FHIR_BASE_URL=http://hapi.fhir.org/baseR4
```

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Run tests: `pytest tests/ -v`
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues or questions:
- Check the documentation in `/docs`
- Run the test suite: `pytest tests/ -v`
- Check logs for error details

## 🎉 Features

- ✅ **Intelligent Routing**: Vaidya automatically detects intent and routes to the right agent
- ✅ **Multi-Agent Orchestration**: Seamless coordination between 6 specialist agents
- ✅ **Streaming Responses**: Real-time SSE streaming for better UX
- ✅ **Emergency Detection**: Automatic red flag detection and prioritization
- ✅ **Medical History**: FHIR integration for comprehensive patient context
- ✅ **Drug Safety**: Automatic medication interaction checking
- ✅ **Provider Search**: Find nearby healthcare providers with ratings
- ✅ **Preventive Care**: Personalized health recommendations
- ✅ **Session Management**: Persistent conversation history

---

Made with ❤️ by the Vaidya Team
