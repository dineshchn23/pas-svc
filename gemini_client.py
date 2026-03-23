import os
import re
from google import genai

GEMINI_KEY = os.getenv('GEMINI_API_KEY')
# Default model: gemini-2.0-flash (current stable flash model)
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')
PREFERRED_MODELS = (
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
)


def _normalize_model_name(model_value: str) -> str:
    """Normalize model env values to a valid model id.

    Accepts common accidental formats such as:
    - GEMINI_MODEL=gemini-1.5-flash
    - models/gemini-1.5-flash
    - models/gemini-1.5-flash:generateContent
    """
    if not model_value:
        return 'gemini-2.0-flash'

    normalized = model_value.strip().strip('"').strip("'")

    if normalized.upper().startswith('GEMINI_MODEL='):
        normalized = normalized.split('=', 1)[1].strip()

    if normalized.startswith('models/'):
        normalized = normalized.split('/', 1)[1]

    if ':generateContent' in normalized:
        normalized = normalized.split(':generateContent', 1)[0]

    return normalized or 'gemini-2.0-flash'


def _mask_sensitive(s: str) -> str:
    if not s:
        return s
    # mask Google API keys (AIza...), keep first 8 chars then '***'
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{8,})', lambda m: m.group(1)[:8] + '***', s)
    # mask any url query param named key=
    s = re.sub(r'([?&]key=)([0-9A-Za-z\-_]+)', lambda m: m.group(1) + m.group(2)[:8] + '***', s)
    return s


def _extract_model_id(name: str) -> str:
    if not name:
        return ''
    if name.startswith('models/'):
        return name.split('/', 1)[1]
    return name


def _list_available_model_ids(client) -> list[str]:
    model_ids = []
    try:
        for model in client.models.list():
            model_name = _extract_model_id(getattr(model, 'name', ''))
            if model_name:
                model_ids.append(model_name)
    except Exception:
        return []
    return list(dict.fromkeys(model_ids))


def _build_fallback_candidates(requested_model: str, available_ids: list[str]) -> list[str]:
    candidates = [requested_model]
    if not available_ids:
        for m in PREFERRED_MODELS:
            if m != requested_model:
                candidates.append(m)
        return candidates

    available = set(available_ids)
    for m in PREFERRED_MODELS:
        if m != requested_model and m in available:
            candidates.append(m)

    # If preferred list misses everything, try any available model as last resort.
    for m in available_ids:
        if m not in candidates:
            candidates.append(m)
    return candidates


def generate_insights(prompt: str) -> str:
    """Call Gemini using the official Google Python SDK (google-genai)."""
    if not GEMINI_KEY:
        return '[Gemini API key not set] Mock insight: ' + prompt[:400]

    model_name = _normalize_model_name(GEMINI_MODEL)

    client = genai.Client(api_key=GEMINI_KEY)
    available_ids = _list_available_model_ids(client)
    candidates = _build_fallback_candidates(model_name, available_ids)
    last_error = None

    for candidate in candidates:
        try:
            response = client.models.generate_content(
                model=candidate,
                contents=prompt,
                config={
                    'temperature': 0.2,
                    'max_output_tokens': 512,
                },
            )
            if getattr(response, 'text', None):
                return response.text
            return str(response)
        except Exception as e:
            last_error = e
            error_text = str(e).lower()
            # For quota/permission failures, do not keep trying alternate models.
            if 'quota' in error_text or '429' in error_text or 'permission' in error_text or '403' in error_text:
                break
            # For NOT_FOUND/INVALID_ARGUMENT, continue trying fallback candidates.
            continue

    masked_error = _mask_sensitive(str(last_error) if last_error else 'Unknown Gemini SDK error')
    shown_available = ', '.join(available_ids[:8]) if available_ids else '(unable to list via API key)'
    diag = [
        '[Gemini API error] SDK request failed',
        masked_error[:600],
        '',
        'Troubleshooting:',
        f'  Requested model : {model_name}',
        f'  Tried models    : {", ".join(candidates[:6])}',
        f'  Available models: {shown_available}',
        '  Ensure the "Generative Language API" is enabled in your Google Cloud project.',
        '  Verify the API key has no IP/referrer restrictions blocking server requests.',
    ]
    return '\n'.join(diag)
