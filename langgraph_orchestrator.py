"""LangGraph orchestrator adapter.

This module attempts to use LangGraph if it's installed to build a simple flow.
If LangGraph is not available or its runtime API differs, it falls back to the
existing `SupervisorAgent` orchestration to ensure the system runs locally.

Extend this file to create a richer LangGraph flow as desired.
"""
import importlib
import traceback
from typing import List, Dict, Tuple, Optional

langgraph = None
try:
    langgraph = importlib.import_module('langgraph')
except Exception:
    langgraph = None


def orchestrate(
    supervisor,
    portfolio: List[Dict],
    analysis_config: Optional[Dict] = None,
) -> Tuple[List[str], Dict]:
    """Orchestrate agents using LangGraph when available, otherwise fallback.

    Returns (tasks, results) same as SupervisorAgent.run.
    """
    if not langgraph:
        # LangGraph not installed — use Supervisor directly
        return supervisor.run(portfolio, analysis_config)

    # LangGraph is available; attempt to create a simple flow.
    # Because LangGraph APIs vary across versions and installs, keep this
    # attempt guarded and fall back to Supervisor on any error.
    try:
        # Minimal representation: ask Supervisor to run but register a
        # descriptive flow object if LangGraph exposes one. We don't rely on
        # any specific API surface here to remain compatible across installs.
        flow_info = {'flow': 'langgraph-lite', 'nodes': ['risk', 'compliance', 'reporting']}

        # If LangGraph provides a logger or client, we can optionally call it.
        if hasattr(langgraph, 'log'):
            try:
                langgraph.log('Starting portfolio analysis flow', flow_info)
            except Exception:
                pass

        # Execute the same sequence as Supervisor for now.
        return supervisor.run(portfolio, analysis_config)
    except Exception as e:
        # On any error, fallback to Supervisor
        return supervisor.run(portfolio, analysis_config)
