"""
GLM-4.7 API Client for log analysis.

Handles API requests, retries, rate limiting, and cost tracking.
Supports both GLM native and Anthropic-compatible endpoints.
Official docs: https://docs.z.ai/guides/llm/glm-4.7
"""
import time
import json
import re
from typing import Dict, Any, List
import requests
from src.utils.logger import logger
from .base import BaseLLMClient, ChunkAnalysisResult

class GLMClient(BaseLLMClient):
    """
    Client for GLM-4.7 API.

    Supports both GLM native and Anthropic-compatible endpoints.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.z.ai/api/paas/v4/",
        model: str = "glm-4.7-flash",
        timeout: int = 120,
        max_retries: int = 3,
        max_output_tokens: int = 4000,
        temperature: float = 0.3,
        price_per_1k_input: float = 0.001,
        price_per_1k_output: float = 0.002
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._price_per_1k_input = price_per_1k_input
        self._price_per_1k_output = price_per_1k_output

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

        self._last_request_time = 0.0
        self._min_request_interval = 0.6

        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self.last_combine_input_tokens_estimate = None

    def analyze_chunk(
        self,
        chunk_lines: list,
        prompt_template: str,
        system_context: str,
        chunk_position: int
    ) -> ChunkAnalysisResult:
        """Analyze a single chunk of log lines."""
        chunk_text = "\n".join(chunk_lines)

        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt_template.replace("{log_lines}", chunk_text)}
        ]

        response_data = self._make_request_with_retry(messages)

        try:
            content = self._extract_content(response_data)
            result_json = self._extract_json(content)
            tokens_used, cost_usd = self._track_usage(response_data)

            logger.info(
                f"Chunk {chunk_position}: {len(chunk_lines)} lines, "
                f"{tokens_used} tokens, ${cost_usd:.4f}"
            )

            return ChunkAnalysisResult(
                issues=result_json.get("issues", []),
                summary=result_json.get("summary", ""),
                metrics=result_json.get("metrics", {}),
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                chunk_position=chunk_position,
                raw_json=result_json
            )

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return ChunkAnalysisResult(
                issues=[], summary=f"Parse error: {str(e)}",
                metrics={}, tokens_used=0, cost_usd=0.0,
                chunk_position=chunk_position, raw_json={}
            )

    def combine_analyses(
        self,
        chunk_results: List[ChunkAnalysisResult],
        combine_prompt: str,
        system_context: str
    ) -> Dict[str, Any]:
        """
        Combine multiple chunk analyses into a final report.

        The model handles deduplication, trend detection, and classification.
        """
        analyses_text = ""
        for result in chunk_results:
            raw = result.raw_json or {}
            analyses_text += f"\n### Chunk {result.chunk_position}\n"
            analyses_text += json.dumps(raw, ensure_ascii=False, indent=2)
            analyses_text += "\n"

        # Estimate combine input tokens (bytes/2 heuristic)
        self.last_combine_input_tokens_estimate = len(analyses_text.encode("utf-8")) // 2
        logger.info(
            f"Estimated combine input tokens: {self.last_combine_input_tokens_estimate}"
        )


        prompt = combine_prompt.replace(
            "{chunk_analyses}", analyses_text
        ).replace(
            "{chunk_count}", str(len(chunk_results))
        )

        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt}
        ]

        response_data = self._make_request_with_retry(messages)

        try:
            content = self._extract_content(response_data)
            result_json = self._extract_json(content)
            tokens_used, cost_usd = self._track_usage(response_data)

            logger.info(f"Combined {len(chunk_results)} analyses: {tokens_used} tokens, ${cost_usd:.4f}")
            return result_json

        except Exception as e:
            logger.error(f"Failed to parse combine response: {e}")
            return {
                "system_status": "UNKNOWN",
                "should_shutdown": False,
                "issues": [],
                "summary": f"Failed to combine: {str(e)}",
                "recommendations": []
            }

    def send_messages(self, messages: list) -> Dict[str, Any]:
        """
        Send a pre-built messages list and return the raw API response.

        Usage and cost are tracked automatically (same as analyze_chunk /
        combine_analyses). Use this when you need access to the raw response
        (e.g. for non-JSON output or custom parsing).
        """
        response_data = self._make_request_with_retry(messages)
        self._track_usage(response_data)
        return response_data

    def send_prompt(
        self,
        user_prompt: str,
        system_context: str
    ) -> Dict[str, Any]:
        """Send arbitrary prompt and get JSON response."""
        messages = [
            {"role": "system", "content": system_context},
            {"role": "user", "content": user_prompt}
        ]

        response_data = self._make_request_with_retry(messages)

        try:
            content = self._extract_content(response_data)
            result_json = self._extract_json(content)
            self._track_usage(response_data)
            return result_json

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return {"error": str(e)}

    def _extract_content(self, response_data: dict) -> str:
        """Extract text content from API response."""
        if "content" in response_data:
            return response_data["content"][0]["text"]
        elif "choices" in response_data:
            return response_data["choices"][0]["message"]["content"]
        else:
            raise ValueError(f"Unknown response format: {list(response_data.keys())}")

    def _track_usage(self, response_data: dict) -> tuple:
        """Track token usage and cost. Returns (tokens_used, cost_usd)."""
        usage = response_data.get("usage", {})
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        total_tokens = input_tokens + output_tokens

        cost_usd = (
            (input_tokens / 1000) * self._price_per_1k_input +
            (output_tokens / 1000) * self._price_per_1k_output
        )

        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost_usd += cost_usd

        return total_tokens, cost_usd

    def _make_request_with_retry(self, messages: list) -> Dict[str, Any]:
        """Make API request with exponential backoff retry."""
        for attempt in range(self._max_retries):
            try:
                self._enforce_rate_limit()

                if "anthropic" in self._base_url.lower():
                    endpoint = f"{self._base_url}/v1/messages"
                    system_prompt = None
                    user_messages = []
                    for msg in messages:
                        if msg["role"] == "system":
                            system_prompt = msg["content"]
                        else:
                            user_messages.append(msg)

                    payload = {
                        "model": self._model,
                        "messages": user_messages,
                        "temperature": self._temperature,
                        "max_tokens": self._max_output_tokens
                    }
                    if system_prompt:
                        payload["system"] = system_prompt
                else:
                    endpoint = f"{self._base_url}/chat/completions"
                    payload = {
                        "model": self._model,
                        "messages": messages,
                        "temperature": self._temperature,
                        "max_tokens": self._max_output_tokens
                    }

                response = self._session.post(
                    endpoint, json=payload, timeout=self._timeout
                )

                if response.status_code != 200:
                    logger.info(f"API status {response.status_code}: {response.text[:500]}")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                response_text = e.response.text if e.response else "No response"
                logger.info(f"API error: HTTP {status_code}: {response_text[:300]}")

                if status_code == 429 and attempt < self._max_retries - 1:
                    wait_time = 5 * (2 ** attempt)
                    logger.warning(f"Rate limit, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                elif status_code >= 500 and attempt < self._max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Server error ({status_code}), waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    raise

            except requests.exceptions.Timeout:
                if attempt < self._max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Timeout, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    raise

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == self._max_retries - 1:
                    raise

        raise Exception(f"Failed after {self._max_retries} attempts")

    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _extract_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON from response (handles markdown code blocks)."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract JSON from: {content[:500]}")

    def get_cost_stats(self) -> Dict[str, Any]:
        """Get cost statistics."""
        return {
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost_usd": self._total_cost_usd
        }

    def reset_cost_stats(self) -> None:
        """Reset cost tracking."""
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self.last_combine_input_tokens_estimate = None
