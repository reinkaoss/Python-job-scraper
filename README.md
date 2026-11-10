# Job Listings Scraper

Internal tool for turning job ads into structured listings you can review, edit, and export.

Paste public job URLs, or upload description files (`.docx`, `.pdf`, `.txt`, `.md`). The app fetches or reads the content, extracts fields with OpenAI (title, company, salary, description, apply link, and so on), and shows each job as a card. You can then correct the data, bulk-edit, export JSON, or generate a self-contained job-page URL.

## Stack

- **Frontend:** React (Create React App) in `frontend/`
- **Backend:** Flask in `api/index.py`, with helpers in `scripts/`
- **Hosting:** Vercel — static React build plus a Python serverless function at `/api`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

npm install
npm --prefix frontend install
```

Copy `.env.example` to `.env` in the project root and fill in:

| Variable | Used by | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Backend | Extraction |
| `PHANTOMJSCLOUD_API_KEY` | Backend | Renders job URLs to HTML |
| `APP_ENV` | Backend | Use `local` on your machine |
| `REACT_APP_API_BASE_URL` | Frontend | Leave empty; local React proxies to Flask |
| `REACT_APP_PUBLIC_BASE_URL` | Frontend | Optional. Domain baked into generated job-page URLs. Leave empty to use the current origin. Set to the deployed site if you generate URLs during local dev (the consumer cannot reach `localhost`). |

## Run locally

From the project root:

```bash
npm run dev:all
```

- UI: [http://localhost:3002](http://localhost:3002)
- API: [http://localhost:5001](http://localhost:5001)

The React dev server proxies `/api` to Flask, so the UI can call `/api/...` without setting `REACT_APP_API_BASE_URL`.

To run the pieces separately:

```bash
npm run dev:frontend   # port 3002
npm run dev:backend    # port 5001 (uses `.venv` if present)
```

## How it works

**URL Scraper** — paste comma-separated job URLs. Each page is rendered via PhantomJsCloud, stripped to text, then sent to the model. Results appear as cards.

**File Extractor** — upload one or more files (max 4MB each). Text is extracted, split into individual postings, then each posting is structured the same way as a scraped URL.

From the cards you can:

- Edit any field, including bulk edit on a selection
- Export one job or all jobs as JSON
- Generate a self-contained `/api/job-page?d=…` URL that another scraper can fetch

## API

All routes live under `/api`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/scrape-url` | Scrape a single URL |
| `POST` | `/api/scrape-multiple` | Scrape a batch of URLs |
| `POST` | `/api/extract-file` | Read an upload and split it into job chunks |
| `POST` | `/api/extract-file-job` | Extract structured fields from one chunk |
| `POST` | `/api/encode-job-urls` | Encode job data into job-page URLs |
| `GET` | `/api/job-page?d=…` | Serve the self-contained job HTML page |

## Deploy

The project is set up for Vercel (`vercel.json`):

- Frontend build: `cd frontend && npm install && npm run build`
- `/api/*` rewrites to the Python function in `api/index.py`

Set `OPENAI_API_KEY` and `PHANTOMJSCLOUD_API_KEY` in the Vercel project. Leave `REACT_APP_API_BASE_URL` empty so the browser calls same-origin `/api`.

On Vercel the filesystem is read-only except `/tmp`. Scraped HTML is written there; it is not persisted across invocations.
