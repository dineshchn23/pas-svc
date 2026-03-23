# AI Portfolio Analysis Backend

This backend provides FastAPI endpoints for portfolio analysis using yfinance and Gemini.
Gemini calls are made with Google's official Python SDK (`google-genai`).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## Environment variables

Create a `.env` file inside `pas-svc/`:

```
GEMINI_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-2.0-flash   # optional, this is the default
```

If you deploy to Vercel, add the same names in the Vercel Environment Variables UI, but paste only the value.
Example: for `GEMINI_API_KEY`, paste `AIza...`, not `GEMINI_API_KEY=AIza...`.

Obtain a key from https://aistudio.google.com/app/apikey  
Ensure the **Generative Language API** is enabled for your Google Cloud project.

## Run (from inside the `pas-svc` folder)

```bash
cd pas-svc
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Demo UI (single-port POC)

After starting the server, open:

```text
http://localhost:8000/
```

The page is served directly by FastAPI from `ui/` and calls backend APIs on the same origin.

## Endpoints

- `POST /analyze` — run portfolio analysis
- `GET /results` — fetch last analysis result
- `GET /debug/gemini` — test Gemini API connectivity
