"""Allowlisted API failure metadata. Never return exception text or HTTP bodies."""

CATEGORIES = frozenset({'auth_error', 'quota_error', 'rate_limit', 'model_error', 'timeout',
                        'sdk_unavailable', 'key_unavailable', 'connection_error',
                        'protocol_error', 'api_error'})


def classify_exception(exc):
    category = getattr(exc, 'category', None)
    if isinstance(category, str) and category in CATEGORIES:
        return category
    names = {cls.__name__ for cls in type(exc).__mro__}
    status = getattr(exc, 'status_code', None)
    if isinstance(exc, (TimeoutError,)) or names & {'APITimeoutError', 'ReadTimeout', 'ConnectTimeout'}:
        return 'timeout'
    if isinstance(exc, ImportError):
        return 'sdk_unavailable'
    # Inspect provider errors only to classify; none of these strings is returned.
    body = getattr(exc, 'body', None)
    error = body.get('error', body) if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    code = str(error.get('code') or error.get('type') or getattr(exc, 'code', '')).lower()
    message = str(error.get('message') or '').lower()
    if status in (401, 403) or names & {'AuthenticationError', 'PermissionDeniedError'}:
        return 'auth_error'
    if 'anthropic-workspace-id' in message:
        return 'auth_error'
    if code in {'insufficient_quota', 'billing_error', 'quota_exceeded', 'credit_balance_too_low'} or any(
            phrase in message for phrase in ('credit balance', 'insufficient quota', 'quota exceeded')):
        return 'quota_error'
    if status == 429 or 'RateLimitError' in names:
        return 'rate_limit'
    if code in {'model_not_found', 'invalid_model', 'model_not_available'} or (
            status in (400, 404) and (error.get('param') == 'model' or 'model' in message)):
        return 'model_error'
    if isinstance(exc, ConnectionError) or 'APIConnectionError' in names:
        return 'connection_error'
    if 'LLMProtocolError' in names:
        return 'protocol_error'
    return 'api_error'
