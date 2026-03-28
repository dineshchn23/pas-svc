from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import List
import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# load .env from backend folder if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

from schemas import PortfolioRequest
from memory import store
from agents import SupervisorAgent, RiskAgent, ComplianceAgent, ReportingAgent, Aggregator
from langgraph_orchestrator import orchestrate as lg_orchestrate

app = FastAPI(title='AI Portfolio Analysis')

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / 'ui'

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if UI_DIR.exists():
    app.mount('/ui', StaticFiles(directory=str(UI_DIR)), name='ui')

# instantiate agents
risk_agent = RiskAgent()
compliance_agent = ComplianceAgent()
reporting_agent = ReportingAgent()
aggregator = Aggregator()
supervisor = SupervisorAgent(risk_agent, compliance_agent, reporting_agent, aggregator)


@app.get('/')
def home():
    index_file = UI_DIR / 'index.html'
    if not index_file.exists():
        raise HTTPException(404, 'UI not found. Create ui/index.html')
    return FileResponse(str(index_file))

@app.post('/analyze')
async def analyze(payload: PortfolioRequest):
    portfolio = [p.dict() for p in payload.portfolio]
    analysis_config = payload.analysis_config.dict() if payload.analysis_config else {}
    tasks, results = lg_orchestrate(supervisor, portfolio, analysis_config)
    stored_result = dict(results.get('aggregation', {}) or {})
    if results.get('timings'):
        stored_result['timings'] = results['timings']
    if not stored_result:
        stored_result = results
    store.set('last_result', stored_result)
    return {
        'tasks': tasks,
        'status': 'completed',
        'result_preview': {'risk_present': 'risk' in results},
        'result': results,
    }


@app.post('/analyze/stream')
async def analyze_stream(payload: PortfolioRequest):
    """SSE endpoint: streams agent events as each stage completes.

    Clients consume via fetch + ReadableStream (EventSource only supports GET).
    Events: started | agent_running | agent_done | agent_error | aggregated | done | error
    """
    portfolio = [p.dict() for p in payload.portfolio]
    analysis_config = payload.analysis_config.dict() if payload.analysis_config else {}
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(event: str, data: dict):
        loop.call_soon_threadsafe(q.put_nowait, (event, data))

    def run_agents():
        try:
            tasks, results = supervisor.run_with_callback(portfolio, emit, analysis_config)
            stored_result = dict(results.get('aggregation', {}) or {})
            if results.get('timings'):
                stored_result['timings'] = results['timings']
            if not stored_result:
                stored_result = results
            store.set('last_result', stored_result)
            loop.call_soon_threadsafe(q.put_nowait, ('done', {'tasks': tasks}))
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, ('error', {'message': str(exc)}))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)  # sentinel

    loop.run_in_executor(None, run_agents)

    async def event_gen():
        while True:
            item = await q.get()
            if item is None:
                break
            event, data = item
            yield f'event: {event}\ndata: {json.dumps(data)}\n\n'

    return StreamingResponse(
        event_gen(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.get('/debug/gemini')
def debug_gemini():
    """Run a short diagnostic call to the configured Gemini model.

    Returns masked output from the `generate_insights` helper. Useful to
    validate model name, endpoint access, and API key permissions.
    """
    from gemini_client import generate_insights
    out = generate_insights('Reply with exactly: GEMINI_OK')
    is_error = isinstance(out, str) and out.startswith('[Gemini API error]')
    connected = not is_error
    return {
        'connected': connected,
        'model': os.getenv('GEMINI_MODEL'),
        'diagnostic': out,
        'message': 'Gemini reachable' if connected else 'Gemini request failed',
    }

@app.get('/results')
async def get_results():
    res = store.get('last_result')
    if not res:
        raise HTTPException(404, 'No results yet')
    return res
