"""
Log Analyzer Orchestrator.

Simplified coordinator:
1. Read log chunks (newest to oldest)
2. Analyze each chunk via API (model finds anomalies)
3. Combine results via API (model deduplicates and aggregates)
4. Save report

No hardcoded processing logic - the model does all the thinking.
"""
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from .state_manager import StateManager, LogPosition
from .chunker import LogChunker
from .llm import BaseLLMClient
from .prompt_builder import PromptBuilder
from .report_generator import ReportGenerator

class LogAnalyzer:
    """
    Main orchestrator for log analysis.

    Workflow:
    1. Load state (last check position)
    2. Read N chunks of M lines from end of log
    3. Send each chunk to API for analysis
    4. Send all analyses to API for combination
    5. Save JSON + Markdown report
    6. Update state
    """

    def __init__(
        self,
        log_file: str,
        llm_client: BaseLLMClient,
        state_file: str = "./data/state.json",
        reports_dir: str = "./reports",
        data_dir: str = "./data",
        num_chunks: int = 5,
        chunk_size_lines: int = 2000,
        max_total_tokens: int = 0,
        max_chunk_tokens: int = 0,
        retention_days: int = 7,
        max_cost_usd: float = 1.0,
        combine_prompt: str = "create_report_with_anomalies",
        prompts_language: str = "ru"
    ):
        self._log_file = log_file
        self._num_chunks = num_chunks
        self._max_cost = max_cost_usd
        self._combine_prompt_name = combine_prompt

        self._state_manager = StateManager(state_file)

        # Token-based chunking priority:
        # 1) explicit max_chunk_tokens
        # 2) derived from max_total_tokens
        if max_chunk_tokens > 0:
            self._chunker = LogChunker(
                log_file,
                chunk_size_lines=0,  # Disabled, using tokens
                max_chunk_tokens=max_chunk_tokens,
                retention_days=retention_days
            )
        elif max_total_tokens > 0:
            max_chunk_tokens = max_total_tokens // num_chunks
            self._chunker = LogChunker(
                log_file,
                chunk_size_lines=0,  # Disabled, using tokens
                max_chunk_tokens=max_chunk_tokens,
                retention_days=retention_days
            )
        else:
            self._chunker = LogChunker(
                log_file,
                chunk_size_lines=chunk_size_lines,
                retention_days=retention_days
            )

        self._llm_client = llm_client

        base_dir = Path(__file__).parent.parent
        prompts_dir = base_dir / "prompts" / prompts_language
        data_dir_path = base_dir / data_dir if not Path(data_dir).is_absolute() else Path(data_dir)

        self._prompt_builder = PromptBuilder(
            prompts_dir=prompts_dir,
            data_dir=data_dir_path
        )

        self._report_generator = ReportGenerator(reports_dir=reports_dir)

    def analyze(self) -> Dict[str, Any]:
        """Run full analysis workflow."""
        print("Starting log analysis...")
        start_time = time.time()
        self._llm_client.reset_cost_stats()

        # 1. Load state
        state = self._state_manager.load_state()
        last_position = state.last_check_position if state else None

        if last_position:
            print(f"Resuming from: {last_position.timestamp}")
        else:
            print("First analysis - starting from end of logs")

        # 2. Analyze chunks
        chunk_results = []
        request_count = 0
        total_lines = 0

        for chunk in self._chunker.iter_chunks_reverse(start_position=last_position):
            if request_count >= self._num_chunks:
                print(f"Reached max requests limit ({self._num_chunks})")
                break

            cost_stats = self._llm_client.get_cost_stats()
            if cost_stats['total_cost_usd'] >= self._max_cost:
                print(f"Reached cost limit (${self._max_cost:.2f})")
                break

            print(f"Analyzing chunk {request_count + 1}/{self._num_chunks} ({len(chunk)} lines)...", end=" ")

            result = self._analyze_chunk(chunk, request_count + 1)
            chunk_results.append(result)
            request_count += 1
            total_lines += len(chunk)

            print(f"OK (${result.cost_usd:.4f})")

        if not chunk_results:
            print("No chunks analyzed")
            return self._empty_report()

        # 3. Combine analyses via API
        print(f"\nCombining {len(chunk_results)} chunk analyses...")
        combined = self._combine_results(chunk_results)

        # 4. Statistics
        combine_input_tokens_estimate = getattr(
            self._llm_client, "last_combine_input_tokens_estimate", None
        )
        cost_stats = self._llm_client.get_cost_stats()
        statistics = {
            "total_lines_analyzed": total_lines,
            "chunks_processed": len(chunk_results),
            "api_requests": request_count + 1,
            "total_tokens": cost_stats['total_tokens'],
            "cost_usd": cost_stats['total_cost_usd'],
            "analysis_duration_seconds": time.time() - start_time,
            "combine_input_tokens_estimate": combine_input_tokens_estimate
        }

        # 5. Generate report
        analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"Generating report (ID: {analysis_id})...")

        report_files = self._report_generator.generate_report(
            analysis_id=analysis_id,
            combined_analysis=combined,
            statistics=statistics
        )

        # 6. Update state
        time_range = combined.get("time_range", {})
        new_timestamp = time_range.get("end") or datetime.now().isoformat()
        new_state = self._state_manager.update_state(
            analysis_id=analysis_id,
            last_position=LogPosition(
                timestamp=new_timestamp,
                line_number=0,
                file_name=Path(self._log_file).name
            ),
            previous_state=state
        )
        self._state_manager.save_state(new_state)

        # Print summary
        status = combined.get("system_status", "UNKNOWN")
        issues = combined.get("issues", [])
        critical = sum(1 for i in issues if i.get("severity") == "CRITICAL")
        medium = sum(1 for i in issues if i.get("severity") == "MEDIUM")
        low = sum(1 for i in issues if i.get("severity") == "LOW")

        print(f"\nAnalysis complete!")
        print(f"  Status: {status}")
        print(f"  Issues: {critical} critical, {medium} medium, {low} low")
        print(f"  Cost: ${statistics['cost_usd']:.4f}")
        print(f"  Reports: {report_files['json_file']}")
        print(f"           {report_files['md_file']}")

        return {
            "analysis_id": analysis_id,
            "system_status": status,
            "should_shutdown": combined.get("should_shutdown", False),
            "issues": issues,
            "statistics": statistics,
            "report_files": report_files
        }

    def _analyze_chunk(self, chunk, position: int):
        """Analyze single chunk via API."""
        start_time = chunk.start_position.timestamp if chunk.start_position.timestamp else "N/A"
        end_time = chunk.end_position.timestamp if chunk.end_position.timestamp else "N/A"

        prompt = self._prompt_builder.build_chunk_prompt(
            chunk_lines=chunk.lines,
            chunk_start_time=start_time,
            chunk_end_time=end_time,
            chunk_position=position
        )

        return self._llm_client.analyze_chunk(
            chunk_lines=chunk.lines,
            prompt_template=prompt,
            system_context=self._prompt_builder.get_system_context(),
            chunk_position=position
        )

    def _combine_results(self, chunk_results: list) -> Dict[str, Any]:
        """Combine chunk analyses via API call."""
        combine_prompt = self._prompt_builder.build_combine_prompt(self._combine_prompt_name)

        return self._llm_client.combine_analyses(
            chunk_results=chunk_results,
            combine_prompt=combine_prompt,
            system_context=self._prompt_builder.get_system_context()
        )

    def _empty_report(self) -> Dict[str, Any]:
        """Return empty report when no analysis performed."""
        return {
            "analysis_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "system_status": "UNKNOWN",
            "should_shutdown": False,
            "issues": [],
            "statistics": {
                "total_lines_analyzed": 0,
                "chunks_processed": 0,
                "api_requests": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "analysis_duration_seconds": 0.0
            },
            "report_files": {}
        }
