"""
Dirt-simple in-memory rate limiter. Good enough for single-instance App Engine demo.

Counters live in a process-local dict keyed by (ip, bucket).
Each entry tracks a per-minute window and a per-day window.
Entries with no activity for >24h are purged on access.

Usage:
    from utilities.limit import check
    ok, reason = check(request.remote_addr, 'submit')
    if not ok:
        return jsonify({'error': reason}), 429
"""
import threading
import time

_lock = threading.Lock()
_store = {}  # {(ip, bucket): {'min_ts': float, 'min_count': int, 'day_ts': float, 'day_count': int}}
_last_purge = [0]

# bucket → (max_per_minute, max_per_day)
LIMITS = {
    'pick_role':     (10,  50),
    'submit':        ( 5,  30),
    'api_write':     (30, 500),  # tasks, comments, materials POST/PATCH
    'generic':       (60, 2000),
}

# Global hard cap on new user rows (orthogonal to per-IP limit)
MAX_USERS = 10_000
WARN_USERS = 5_000


def _purge_stale():
    now = time.time()
    if now - _last_purge[0] < 600:  # only purge every 10 min
        return
    _last_purge[0] = now
    cutoff = now - 86400
    dead = [k for k, v in _store.items() if v['day_ts'] < cutoff]
    for k in dead:
        _store.pop(k, None)


def check(ip, bucket):
    """
    Returns (allowed: bool, message: str).
    Increments counters on allow. No-op on deny.
    """
    if not ip:
        ip = 'unknown'
    now = time.time()
    per_min, per_day = LIMITS.get(bucket, LIMITS['generic'])
    key = (ip, bucket)

    with _lock:
        _purge_stale()
        rec = _store.get(key)
        if not rec:
            rec = {'min_ts': now, 'min_count': 0, 'day_ts': now, 'day_count': 0}
            _store[key] = rec

        # Minute window slides
        if now - rec['min_ts'] >= 60:
            rec['min_ts'] = now
            rec['min_count'] = 0
        # Day window slides
        if now - rec['day_ts'] >= 86400:
            rec['day_ts'] = now
            rec['day_count'] = 0

        if rec['min_count'] >= per_min:
            return False, f"rate limit: {per_min}/min for this action, try again in a moment"
        if rec['day_count'] >= per_day:
            return False, f"rate limit: {per_day}/day for this action, try again tomorrow"

        rec['min_count'] += 1
        rec['day_count'] += 1
        return True, 'ok'


def snapshot():
    """Dev helper — returns a rough view of current counters."""
    with _lock:
        return {str(k): dict(v) for k, v in _store.items()}
