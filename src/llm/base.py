"""
Abstract base class for LLM API clients.

Implement this interface to add support for new LLM providers
(OpenAI, Anthropic, local models, etc.).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class ChunkAnalysisResult:
    """Result of analyzing a single log chunk."""
    issues: list
    summary: str
    metrics: Dict[str, Any]
    tokens_used: int
    cost_usd: float
    chunk_position: int
    raw_json: Dict[str, Any] = field(default_factory=dict)


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM API clients.

    To add a new provider:
    1. Create a new file in src/llm/ (e.g., openai_client.py)
    2. Inherit from BaseLLMClient
    3. Implement all abstract methods
    4. Update config to use the new provider
    """

    @abstractmethod
    def analyze_chunk(
        self,
        chunk_lines: list,
        prompt_template: str,
        system_context: str,
        chunk_position: int
    ) -> ChunkAnalysisResult:
        """Analyze a single chunk of log lines."""

    @abstractmethod
    def combine_analyses(
        self,
        chunk_results: List[ChunkAnalysisResult],
        combine_prompt: str,
        system_context: str
    ) -> Dict[str, Any]:
        """Combine multiple chunk analyses into a final report."""

    @abstractmethod
    def send_prompt(
        self,
        user_prompt: str,
        system_context: str
    ) -> Dict[str, Any]:
        """Send arbitrary prompt and get JSON response."""

    @abstractmethod
    def get_cost_stats(self) -> Dict[str, Any]:
        """Get accumulated cost statistics."""

    @abstractmethod
    def reset_cost_stats(self) -> None:
        """Reset cost tracking."""
