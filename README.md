# CareerNavigator AI

CareerNavigator AI is a student project for exploring a collected sample of job
postings, understanding skill demand, comparing a student profile with career
roles, identifying skill gaps, and generating a weekly learning plan.

The system is periodically refreshed, not continuously real-time. Job market
analytics require a configured database and collected data. Recommendations,
role catalogs, skill-gap analysis by role importance, and learning plans can be
explored without live job data. No hiring probability is calculated.

## System architecture

```text
SerpApi Google Jobs API (India)
        |
        v
FastAPI collector -> raw snapshots -> cleaning, deduplication, skill extraction
                                            |
                                            v
                                PostgreSQL or MySQL database
                                            |
                                            v
                              FastAPI analytics and career APIs
                                            |
                                            v
                              React + Vite web application
```

The browser sends requests to FastAPI. FastAPI validates inputs, fetches
authorized job data when requested, normalizes records, computes analytics,
and reads or writes database records. Career-role requirements and learning
resource links are kept in editable JSON catalogs. Recommendations use
explainable weighted content-based skill coverage; they are not trained
predictions or probabilities of being hired.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ and npm
- PostgreSQL 14+ or MySQL 8.x for persistent job-market data and roadmap
  records (SQLite is used by the automated tests)
- A SerpApi account and API key for live Google Jobs collection
- Git (optional, for version control)

The SerpApi key is used by the backend only. Never put it in frontend code or
commit a populated `.env` file.

## Local setup on Windows

Run commands from the repository root.

### 1. Create a Python environment and install backend dependencies

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

If PowerShell blocks environment activation, use the environment's interpreter
directly, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 2. Configure the backend environment

Copy `.env.example` to `.env` in the repository root. Keep the existing
PostgreSQL database URL and add the key obtained from
[SerpApi signup](https://serpapi.com/users/sign_up):

```dotenv
CAREERCOMPASS_DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/careercompass
CAREERCOMPASS_SERPAPI_API_KEY=your_private_serpapi_key
CAREERCOMPASS_SERPAPI_COUNTRY_CODE=in
CAREERCOMPASS_SERPAPI_LANGUAGE=en
CAREERCOMPASS_SERPAPI_MAX_PAGES=3
```

For MySQL instead, use
`mysql+pymysql://USERNAME:PASSWORD@localhost:3306/careercompass?charset=utf8mb4`.
Make sure the selected database server is running and the database user has
access before initialization. URL-encode special characters in the database
username or password. Do not paste credentials into source files, screenshots,
or issues.

Initialize tables and seed skill, role, and learning-resource reference data:

```powershell
python -m backend.app.db.init_db
```

Expected success message:

```text
CareerNavigator database tables and reference data are ready.
```

### 3. Start the API

In a terminal at the repository root:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Check `http://127.0.0.1:8000/api/health` and open the interactive API
documentation at `http://127.0.0.1:8000/docs`.

### 4. Start the web application

In a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open the local Vite URL printed by the command (normally
`http://localhost:5173`). The Vite development server proxies `/api` requests
to FastAPI at port 8000.

## Collect and process job data

The collector requests Google Jobs search results through SerpApi, with India
(`gl=in`) as the default country. It follows the provider's pagination token
only up to `CAREERCOMPASS_SERPAPI_MAX_PAGES` (at most 10). SerpApi's free plan
and quotas can change; verify the current plan limits and applicable provider
and job-listing terms before use. The application does not scrape job websites
directly.

1. Register for SerpApi's Google Jobs API, confirm the current account quota,
   and add its API key privately to `.env` as `CAREERCOMPASS_SERPAPI_API_KEY`.
2. With the API running and key configured, request an India sample using
   `GET /api/jobs/search?query=data%20analyst&location=Pune`.
3. Review the response and source terms. Submit its `jobs` array to
   `POST /api/jobs/process` using the interactive docs or another API client.
4. Review the response's created/updated counts and data-quality report.
5. Reload the dashboard to see analytics for the stored sample.

Repeat this process when you want to refresh the sample. Collection time is
stored separately from the source posting date. One collection cannot establish
a historical trend; trends need multiple dated snapshots and must be
interpreted accordingly.

## Application pages

- **Overview and Job Market:** filtered unique-posting counts, job listings,
  skill demand, and available source/date/sample information. Skill demand is
  the percentage of unique filtered postings that mention a skill.
- **Career Match:** ranks curated roles using weighted requirement coverage.
  Enter skills as comma-separated names; optionally add a level after a colon,
  for example `SQL: advanced, Excel: beginner`. Unqualified skills default to
  intermediate.
- **Skill Gaps:** groups requirements into possessed, partial, and missing.
  With stored job data, gap priority includes observed skill demand; without
  it, role importance is used and the UI says so.
- **Learning Roadmap:** builds one weekly milestone for each partial or missing
  requirement, with practice tasks and cataloged resources. Resources without
  a catalog entry are not given invented links. Checkbox progress is stored in
  the current browser only.
- **Sources & Project:** describes data provenance and limitations.

Student profiles are submitted for analysis but are not stored as student
profiles. Generated roadmaps are persisted when the database is configured and
initialized.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | API health |
| `GET` | `/api/jobs/search` | Bounded India-focused SerpApi Google Jobs search |
| `POST` | `/api/jobs/clean` | Normalize and quality-check supplied postings |
| `POST` | `/api/jobs/process` | Save raw snapshots and cleaned jobs |
| `GET` | `/api/market/summary` | Filtered market summary |
| `GET` | `/api/market/skills` | Skill-demand percentages |
| `GET` | `/api/market/jobs` | Filtered job records |
| `GET` | `/api/careers/roles` | Curated role catalog |
| `POST` | `/api/careers/recommendations` | Explainable role matching |
| `POST` | `/api/careers/skill-gaps` | Role-specific skill-gap analysis |
| `POST` | `/api/careers/roadmaps` | Personalized weekly learning plan |

The interactive OpenAPI page at `/docs` shows request schemas, filters, and
response examples.

## Tests and frontend checks

From the repository root:

```powershell
python -m pytest backend\tests -q
```

From the `frontend` directory:

```powershell
npm run lint
npm run build
```

Backend tests use an in-memory SQLite database and mocked external API
responses. They do not require PostgreSQL/MySQL, SerpApi credentials, or
network access.
The frontend production build does not require a running API.

## Important limitations

- Live collection needs a valid SerpApi key and remains subject to plan
  quotas, provider terms, and the source job listing's conditions. Google Jobs
  may return relative posting dates; these are left unknown rather than
  converted into fabricated exact dates.
- Market metrics describe only the collected and cleaned sample, not the full
  labor market.
- Salary or experience summaries are omitted when source data is absent or not
  reliable enough.
- The editable role catalog is a starting reference, not a universal or
  independently validated definition of every occupation.
- Similarity scores describe overlap with encoded skills, not employability or
  hiring likelihood.
- Resource availability and content can change; students should verify a
  resource before using it.
