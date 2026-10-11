"""Responder-auth helpers. Pure and unit-tested. NOT a substitute for real identity (Cognito/OIDC) or a security review."""
import hmac, time

MIN_TOKEN_LEN = 24


def token_acceptable(token: str) -> bool:
    """Fail closed on weak/placeholder tokens (Secrets Manager value should be >= 24 random chars)."""
    return isinstance(token, str) and len(token) >= MIN_TOKEN_LEN and token.strip() == token


def tokens_equal(supplied: str, expected: str) -> bool:
    """Constant-time compare on bytes (hmac.compare_digest raises TypeError for non-ASCII str)."""
    return hmac.compare_digest((supplied or "").encode("utf-8"), expected.encode("utf-8"))


class FailureLimiter:
    """In-process lockout after repeated failed logins. Per task only (API runs 1 task); use WAF/Cognito for real protection."""
    def __init__(self, max_failures=5, window_s=300, clock=time.monotonic):
        self.max, self.window, self.clock, self.fails = max_failures, window_s, clock, {}

    def _recent(self, key):
        now = self.clock(); xs = [t for t in self.fails.get(key, []) if now - t < self.window]
        self.fails[key] = xs; return xs

    def blocked(self, key): return len(self._recent(key)) >= self.max
    def record_failure(self, key): self._recent(key).append(self.clock())
    def reset(self, key): self.fails.pop(key, None)


def client_key(headers: dict, fallback: str) -> str:
    """Behind one ALB, the LAST X-Forwarded-For entry is the address the ALB saw; earlier entries are client-controlled."""
    xff = headers.get("x-forwarded-for", "")
    return xff.split(",")[-1].strip() or fallback if xff else fallback
