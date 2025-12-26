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
- Fixed "Error loading files" issue by adding user sync to Supabase database
  - Backend now auto-syncs users to Supabase when they authenticate
  - This fixes foreign key constraint issues when creating notebooks
  - Added `ensureUserExists` function in frontend as fallback

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
