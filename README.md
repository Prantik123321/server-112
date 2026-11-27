# NodeShare Backend

> Cross-platform private messaging and file-sharing backend for Windows Desktop and Android applications. Built with **FastAPI**, **Supabase PostgreSQL**, **MongoDB Atlas**, and deployable to **Vercel Python Runtime**.

---

## 🚀 Key Features & Highlights

- **Authentication Without Phone or Email**:
  - Full Name, Unique Username, Argon2id password hashing.
  - Short-lived JWT access tokens (15 minutes).
  - Secure opaque refresh tokens stored as SHA-256 hashes in database (30 days).
  - Automatic token rotation with family revocation on reuse detection.
  - Brute-force protection and IP-based rate limiting.

- **Dual-Database Architecture (Clear Separation of Concerns)**:
  - **Supabase PostgreSQL**: Authoritative store for user profiles, friendships, blocks, conversation metadata, group permissions, storage metadata, and notifications.
  - **MongoDB Atlas**: High-throughput distributed store for chat messages, replies, edit history, emoji reactions, and delivery receipts.
  - **Zero Duplicate Authoritative Data**: Strict cross-database safety and idempotency keys on message creation.

- **Smart User Search Engine**:
  - Multi-tier search ranking:
    1. Exact username
    2. Exact full name
    3. Username prefix
    4. Name prefix
    5. Similar spelling / typo tolerance (PostgreSQL `pg_trgm` GIN index)
    6. Partial match
  - Full Unicode support for **Bengali names** (e.g. `প্রান্তিক দাস`, `আব্দুর রহিম`) and English names.

- **Friend & Group System**:
  - Send, accept, reject, and cancel friend requests.
  - Mutual blocking and friend removal with instant cascading.
  - Group creation, avatars, owner/admin/member hierarchy, and teacher verification.

- **Verified Teacher System**:
  - Regular users vs. Teacher accounts.
  - Verification can **only** be granted by administrators (never self-assigned).
  - Teacher search filters and official teacher-led group creation.

- **Secure Direct-to-Storage File Sharing**:
  - Supabase Storage private buckets with signed upload and download URLs.
  - Large files upload directly from client to Supabase Storage (zero bandwidth burden on Vercel serverless functions).
  - Strict MIME validation and magic byte file signature verification (`filetype`).
  - Configurable upload size limit (100 MB) and user storage quotas (1 GB).

- **Real-Time Architecture**:
  - Designed for serverless environments (Vercel) using Supabase Realtime private channels for message notifications, typing indicators, read receipts, and online status.

---

## 🛠️ Local Windows Development Setup

### 1. Prerequisites
- Windows 10/11
- PowerShell 5.1+ or PowerShell 7+
- Python 3.12+ (tested with Python 3.13)

### 2. Environment Configuration
Clone or open the repository in Windows PowerShell:

```powershell
cd "c:\Users\Prantik Das\Documents\Node Share app"
```

Activate the virtual environment:
```powershell
.\.venv\Scripts\Activate.ps1
```

Copy the example environment configuration:
```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in your Supabase and MongoDB Atlas credentials:
```ini
ENVIRONMENT=development
JWT_SECRET_KEY=generate-a-random-32-byte-hex-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
SUPABASE_POSTGRES_URL=postgresql://postgres.your-project:password@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
MONGODB_URI=mongodb+srv://user:pass@cluster0.mongodb.net/?retryWrites=true&w=majority
```

### 3. Database Migration
In your Supabase project SQL Editor, run the migration script:
- Copy contents of `supabase/migrations/001_initial_schema.sql` and run it.
- Then run `supabase/policies/rls_policies.sql` to enable row-level security and restrict direct client access to sensitive columns.
- (Optional) Run `supabase/seed.sql` to populate initial test users and verified teacher accounts.

### 4. Running the Development Server
Start the local server with hot reloading:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Local Server: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Interactive API Docs (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Alternative Docs (ReDoc): [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 🧪 Running Automated Tests

Run the full pytest suite with coverage and verbose output:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Tests cover:
- Argon2id hashing and password strength
- Smart search 6-tier ranking and Bengali Unicode search
- Username normalization and SQL injection prevention
- File signature magic bytes validation
- Session and token security
- Route authentication and rate limiting

---

## 🚢 Vercel Deployment

NodeShare is designed to deploy to **Vercel** as a Python serverless function.

1. **Vercel Configuration**: `vercel.json` and `api/index.py` are pre-configured.
2. **Environment Variables**: Add all required variables from `.env.example` into your Vercel Project Settings -> Environment Variables. Generate a unique production `JWT_SECRET_KEY`; startup rejects the development default and documented placeholders.
3. **Database Connection Pooling**: Ensure `SUPABASE_POSTGRES_URL` uses port **6543** (Supabase Transaction Pooler / PgBouncer mode) so that ephemeral serverless instances do not exhaust database connections.
4. **Deploy via GitHub**:
   - Push your code to a GitHub repository.
   - Import the repository in [Vercel Dashboard](https://vercel.com).
   - Vercel automatically detects the Python runtime and routes all `/api/*` traffic to `api/index.py`.

---

## 📄 License
MIT License. Created for the NodeShare cross-platform ecosystem.
