# MedBot Study Application

## Overview
MedBot is a comprehensive study application featuring AI-powered exam generation, a chatbot for Q&A, document upload/processing, flashcards, and study planning.

## Current State
- Application is fully functional with Python Flask backend serving React frontend
- All core features working: Authentication, Exam generation, Chatbot, Document processing

## Project Architecture

### Backend (Python Flask)
- **Location**: `backend/`
- **Entry point**: `backend/app.py`
- **Port**: 5000
- **Framework**: Flask with Flask-CORS, Flask-SQLAlchemy, Flask-Login

### Frontend (React)
- **Location**: `frontend/` (source), `frontend/build/` (production build)
- **Served by**: Flask backend as static files

### Key Integrations
- **Google Gemini API**: AI-powered exam generation and chatbot (`GEMINI_API_KEY`)
- **Supabase**: Database and authentication (`SUPABASE_URL`, `SUPABASE_KEY`)
- **OpenAI**: Additional AI features (`OPENAI_API_KEY` if needed)
- **SendGrid**: Email services (`SENDGRID_API_KEY`)
- **Arcade**: AI tool integration (`ARCADE_API_KEY`)

## Running the Application
The workflow "Start application" runs:
```bash
export LD_LIBRARY_PATH=/nix/store/xvzz97yk73hw03v5dhhz3j47ggwf1yq1-gcc-13.2.0-lib/lib:$LD_LIBRARY_PATH && cd backend && python3 app.py
```

The LD_LIBRARY_PATH is required for the grpc library used by google-generativeai.

## Recent Changes (December 26, 2025)
- Fixed workflow configuration to run Python Flask backend instead of Node.js
- Installed all required Python packages to `.pythonlibs/`
- Configured LD_LIBRARY_PATH for native library dependencies
- Application now running successfully with all core features
- **Fixed database architecture - Service User Workaround**:
  - Root cause: Supabase tables have FK constraints to `auth.users` but app uses custom Flask auth
  - Solution: "Service user" approach - all records created under existing Supabase user `c04c5c6a-367b-4322-8913-856d13a2da75`
  - Real owner ID stored in description field as JSON prefix: `{"real_owner":"uuid"}|description`
  - Helper functions: `get_owner_metadata()`, `extract_real_owner()`, `extract_description()`
  - Constant: `SUPABASE_SERVICE_USER_ID = 'c04c5c6a-367b-4322-8913-856d13a2da75'`
  - All `/api/notebooks` endpoints use Supabase with service user + description metadata filtering
  - All `/api/documents` endpoints use Supabase with **notebook ownership** for filtering (determines owner from notebook, not document metadata)
  - User auth still syncs to local SQLAlchemy database for session management
- **Document Filtering Fix**:
  - Documents are now filtered by notebook ownership, not document metadata
  - First gets all notebooks owned by user, then returns documents from those notebooks
  - Supports both new notebooks (with owner in description) and legacy direct ownership

## Environment Variables Required
- `GEMINI_API_KEY`: Google Gemini API key for AI features
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_KEY`: Supabase API key
- `SESSION_SECRET`: Flask session secret key
- `SENDGRID_API_KEY`: SendGrid API key for emails
- `ARCADE_API_KEY`: Arcade API key for tool integration

## Optional Features (Not Currently Enabled)
These features are disabled due to heavy dependencies:
- OCR (requires pytesseract)
- Image captioning (requires torch/transformers/BLIP)
- Local embeddings (requires sentence_transformers)

These are non-critical and can be enabled if needed by installing the respective packages.
