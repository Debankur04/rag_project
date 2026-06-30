"""
Production model router with:
  - Cost-aware routing (cheap vs. expensive selection)
  - Latency-aware switching (rolling p99 window)
  - Automatic failover with circuit-breaker pattern
  - Cooldown after failure (exponential backoff)
"""
import time, asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from rag_project.query_microservice.controllers.add_intent import insert_intent



class ModelTier(Enum):
    CHEAP = "cheap"
    EXPENSIVE = "expensive"


@dataclass
class ModelHealth:
    error_count: int = 0
    total_calls: int = 0
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    circuit_open: bool = False
    circuit_open_until: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.error_count / self.total_calls

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[idx]

    def is_healthy(self) -> bool:
        if self.total_calls < 30:
            return True
        if self.circuit_open:
            if time.time() > self.circuit_open_until:
                self.circuit_open = False   # half-open
                return True
            return False
        return self.error_rate < 0.05 and self.p99_latency < 3000


class ModelRouter:
    def __init__(self, config: dict):
        self.config = config
        self.health: dict[str, ModelHealth] = {
            k: ModelHealth() for k in config["models"]
        }
        self._clients: dict[str, object] = {}

    def _build_client(self, model_key: str):
        cfg = self.config["models"][model_key]
        if cfg["provider"] == "groq":
            import os
            return ChatGroq(model=cfg["model_name"], api_key=os.getenv("GROQ_API_KEY"))
        elif cfg["provider"] == "gemini":
            import os
            return ChatGoogleGenerativeAI(
                model=cfg["model_name"], google_api_key=os.getenv("GEMINI_API_KEY")
            )
        raise ValueError(f"Unknown provider: {cfg['provider']}")

    def get_client(self, model_key: str):
        if model_key not in self._clients:
            self._clients[model_key] = self._build_client(model_key)
        return self._clients[model_key]

    def select_model(self, query: str, user_tier: str = "standard", db=None) -> str:
        """Route to cheapest healthy model that meets quality bar."""
        rules = self.config["routing_rules"]

        if rules.get("use_intent_classifier", False):
            from rag_project.query_microservice.llmops.intent_classifier import IntentClassifier
            classifier = IntentClassifier(model_name=self.config["models"][rules["simple_query_model"]]["model_name"])
            intent_res = classifier.classify(query)
            if db:
                insert_intent(db=db, query=query, intent_res=intent_res)
            if intent_res:
                candidate = rules["simple_query_model"]
                if self.health[candidate].is_healthy():
                    return candidate

        # Walk the fallback chain
        for model_key in rules["fallback_chain"]:
            if self.health[model_key].is_healthy():
                return model_key

        raise RuntimeError("All models unhealthy — serving degraded response")

    def record_success(self, model_key: str, latency_ms: float):
        h = self.health[model_key]
        h.total_calls += 1
        h.latencies.append(latency_ms)

    def record_failure(self, model_key: str, error: Exception):
        h = self.health[model_key]
        h.total_calls += 1
        h.error_count += 1
        if h.error_rate > 0.05:
            h.circuit_open = True
            h.circuit_open_until = time.time() + 60   # 60s cooldown