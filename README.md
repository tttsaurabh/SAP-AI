# SAP Knowledge AI Assistant

A production-grade AI assistant trained exclusively on administrator-provided SAP knowledge (ABAP, MDG, S/4HANA, workflows, master data, design specifications) built using a Retrieval-Augmented Generation (RAG) architecture.

## Architecture

- **Frontend**: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Lucide icons, Framer Motion.
- **Backend**: FastAPI (Python 3.12), SQLAlchemy (database ORM), Qdrant (dense vector search), BM25 (keyword search).
- **Database**: PostgreSQL (user metadata, chats, feedback), Redis (session cache, background task queue).

## Setup Instructions

### Prerequisites
1. Node.js v20+ & npm
2. Python 3.12+ & pip
3. Docker Desktop (for running PostgreSQL, Qdrant, and Redis)

### Step 1: Run Services (via Docker)
Start PostgreSQL, Qdrant, and Redis:
```bash
docker-compose up -d
```

### Step 2: Backend Setup
1. Navigate to the backend folder:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your `.env` file based on `.env.example`.
5. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```

### Step 3: Frontend Setup
1. Navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the Next.js local development server:
   ```bash
   npm run dev
   ```
4. Open [http://localhost:3000](http://localhost:3000) in your browser.
