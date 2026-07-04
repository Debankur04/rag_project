import redis, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass


DAILY_BUDGET_USD = {
    "free": 0.05,       # 5 cents/day
    "standard": 0.50,   # 50 cents/day
    "premium": 5.00,    # $5/day
}

MODEL_COSTS = {
    # (cost_per_1k_input, cost_per_1k_output) in USD
    "llama-3.3-70b-versatile": (0.00059, 0.00079),
    "llama-3.1-8b-instant":    (0.00005, 0.00008),
    "gemini-2.0-flash":        (0.00010, 0.00040),
}


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def cost_usd(self) -> float:
        inp, out = MODEL_COSTS.get(self.model, (0, 0))
        return (self.input_tokens / 1000 * inp) + (self.output_tokens / 1000 * out)


class TokenTracker:
    def __init__(self, redis_client: redis.Redis):
        self.r = redis_client

    def _ttl_to_midnight(self) -> int:
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return int((midnight - now).total_seconds())

    def _date_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def check_budget(self, user_id: str, user_tier: str = "free") -> bool:
        """Returns False if user has exceeded daily budget."""
        date = self._date_key()
        cost_key = f"cost:user:{user_id}:date:{date}"
        spent = float(self.r.get(cost_key) or 0)
        limit = DAILY_BUDGET_USD.get(user_tier, DAILY_BUDGET_USD["free"])
        return spent < limit

    def record_usage(self, user_id: str, usage: TokenUsage):
        date = self._date_key()
        ttl = self._ttl_to_midnight()
        pipe = self.r.pipeline()

        pipe.incrbyfloat(f"cost:user:{user_id}:date:{date}", usage.cost_usd)
        pipe.incrby(f"token:user:{user_id}:date:{date}:input", usage.input_tokens)
        pipe.incrby(f"token:user:{user_id}:date:{date}:output", usage.output_tokens)

        # Set TTL only if key is new (avoid resetting expiry)
        for key in [
            f"cost:user:{user_id}:date:{date}",
            f"token:user:{user_id}:date:{date}:input",
            f"token:user:{user_id}:date:{date}:output",
        ]:
            pipe.expire(key, ttl, xx=False)

        pipe.execute()

    def get_daily_summary(self, user_id: str) -> dict:
        date = self._date_key()
        return {
            "date": date,
            "input_tokens": int(self.r.get(f"token:user:{user_id}:date:{date}:input") or 0),
            "output_tokens": int(self.r.get(f"token:user:{user_id}:date:{date}:output") or 0),
            "cost_usd": float(self.r.get(f"cost:user:{user_id}:date:{date}") or 0),
        }