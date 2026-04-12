import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Allows up to `max_requests` in a sliding `window_seconds` window.
    acquire() blocks until a slot is available.
    """

    def __init__(self, max_requests: int, window_seconds: float = 10.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - self.window_seconds
                self._timestamps = [t for t in self._timestamps if t > cutoff]

                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    return

                # Wait until the oldest request falls outside the window
                wait = self._timestamps[0] - cutoff
            time.sleep(wait)


# Pre-configured limiters at ~90% of actual limits
gamma_limiter = TokenBucketRateLimiter(max_requests=360, window_seconds=10.0)
clob_market_data_limiter = TokenBucketRateLimiter(max_requests=1350, window_seconds=10.0)
clob_batch_limiter = TokenBucketRateLimiter(max_requests=450, window_seconds=10.0)
data_api_limiter = TokenBucketRateLimiter(max_requests=900, window_seconds=10.0)
