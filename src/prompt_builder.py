"""
Prompt Builder for log analysis.

Loads system context from data/*.md files and prompt templates from prompts/.
No hardcoded domain knowledge - everything comes from generated docs.
"""
from pathlib import Path
from src.utils.logger import logger


class PromptBuilder:
    """Builds prompts from data context and template files."""

    def __init__(self, prompts_dir: str, data_dir: str):
        """
        Args:
            prompts_dir: Path to prompts/ directory
            data_dir: Path to data/ directory (with project_context.md, analysis_rules.md)
        """
        self._prompts_dir = Path(prompts_dir)
        self._data_dir = Path(data_dir)
        self._system_context = self._build_system_context()
        self._prompts_cache = {}

    def _build_system_context(self) -> str:
        """Build system context from data/*.md files."""
        parts = []

        # Load project context
        context_path = self._data_dir / "project_context.md"
        if context_path.exists():
            try:
                content = context_path.read_text(encoding="utf-8")
                parts.append(content)
                logger.info(f"Loaded project_context.md ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to load project_context.md: {e}")

        # Load analysis rules
        rules_path = self._data_dir / "analysis_rules.md"
        if rules_path.exists():
            try:
                content = rules_path.read_text(encoding="utf-8")
                parts.append(content)
                logger.info(f"Loaded analysis_rules.md ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to load analysis_rules.md: {e}")

        if not parts:
            logger.warning("No context files found in data/. Run generate_context.py first.")
            parts.append("No project context available. Analyze logs based on general patterns.")

        return "\n\n".join(parts)

    def get_system_context(self) -> str:
        """Get built system context."""
        return self._system_context

    def build_chunk_prompt(
        self,
        chunk_lines: list,
        chunk_start_time: str,
        chunk_end_time: str,
        chunk_position: int
    ) -> str:
        """Build prompt for chunk analysis."""
        template = self._load_prompt("analyze_chunk.txt")

        prompt = template.replace(
            "{chunk_start_time}", chunk_start_time
        ).replace(
            "{chunk_end_time}", chunk_end_time
        ).replace(
            "{chunk_line_count}", str(len(chunk_lines))
        ).replace(
            "{chunk_position}", str(chunk_position)
        )

        return prompt

    def build_combine_prompt(self, prompt_name: str = "create_report") -> str:
        """Build prompt for combining chunk analyses.

        Args:
            prompt_name: Prompt name without .txt extension.
                         "create_report" — dedup + trends only
                         "create_report_with_anomalies" — dedup + trends + anomaly detection
        """
        return self._load_prompt(f"{prompt_name}.txt")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file (cached)."""
        if filename in self._prompts_cache:
            return self._prompts_cache[filename]

        filepath = self._prompts_dir / filename
        try:
            content = filepath.read_text(encoding="utf-8")
            self._prompts_cache[filename] = content
            logger.debug(f"Loaded prompt: {filename}")
            return content
        except Exception as e:
            logger.error(f"Failed to load prompt {filename}: {e}")
            raise
