"""
State Manager for Log Analyzer.

Manages persistent state of log analysis, including last check position
and analysis history. Thread-safe implementation with JSON persistence.
"""
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from src.utils.logger import logger


@dataclass
class LogPosition:
    """Position in log file."""
    timestamp: str  # ISO format: "2026-02-07T03:00:00Z"
    line_number: int  # Global line number in file
    file_name: str  # Current log file name (e.g., "analyzer.log")
    byte_offset: Optional[int] = None  # For faster seeking (optional)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LogPosition":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class AnalyzerState:
    """Persistent state of log analyzer."""
    last_check_timestamp: str  # ISO format
    last_check_position: Optional[LogPosition]
    last_analysis_id: str
    total_analyses: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_check_timestamp": self.last_check_timestamp,
            "last_check_position": self.last_check_position.to_dict() if self.last_check_position else None,
            "last_analysis_id": self.last_analysis_id,
            "total_analyses": self.total_analyses
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyzerState":
        """Create from dictionary (JSON deserialization)."""
        position = None
        if data.get("last_check_position"):
            position = LogPosition.from_dict(data["last_check_position"])

        return cls(
            last_check_timestamp=data["last_check_timestamp"],
            last_check_position=position,
            last_analysis_id=data["last_analysis_id"],
            total_analyses=data["total_analyses"]
        )


class StateManager:
    """
    Manages state persistence for log analyzer.

    Thread-safe implementation using Lock.
    State is stored in JSON file for persistence across restarts.
    """

    def __init__(self, state_file: str):
        """
        Initialize state manager.

        Args:
            state_file: Path to state file (JSON)
        """
        self._state_file = Path(state_file)
        self._lock = threading.Lock()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure state file directory exists."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Optional[AnalyzerState]:
        """
        Load state from JSON file.

        Returns:
            AnalyzerState if file exists and valid, None otherwise
        """
        with self._lock:
            if not self._state_file.exists():
                logger.debug(f"State file not found: {self._state_file}")
                return None

            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                state = AnalyzerState.from_dict(data)
                logger.info(f"Loaded state: last_analysis={state.last_analysis_id}, total={state.total_analyses}")
                return state

            except Exception as e:
                logger.error(f"Failed to load state from {self._state_file}: {e}")
                return None

    def save_state(self, state: AnalyzerState) -> None:
        """
        Save state to JSON file (atomic write).

        Args:
            state: AnalyzerState to save
        """
        with self._lock:
            try:
                # Atomic write: write to temp file first, then rename
                temp_file = self._state_file.with_suffix(".tmp")

                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

                # Atomic rename
                temp_file.replace(self._state_file)

                logger.info(f"Saved state: analysis_id={state.last_analysis_id}, total={state.total_analyses}")

            except Exception as e:
                logger.error(f"Failed to save state to {self._state_file}: {e}")
                raise

    def create_initial_state(self, analysis_id: str) -> AnalyzerState:
        """
        Create initial state for first analysis.

        Args:
            analysis_id: ID of first analysis

        Returns:
            New AnalyzerState
        """
        return AnalyzerState(
            last_check_timestamp=datetime.now().isoformat() + "Z",
            last_check_position=None,
            last_analysis_id=analysis_id,
            total_analyses=0
        )

    def update_state(
        self,
        analysis_id: str,
        last_position: LogPosition,
        previous_state: Optional[AnalyzerState] = None
    ) -> AnalyzerState:
        """
        Update state after analysis.

        Args:
            analysis_id: ID of completed analysis
            last_position: Position in log where analysis stopped
            previous_state: Previous state (or None for first analysis)

        Returns:
            Updated AnalyzerState
        """
        total_analyses = (previous_state.total_analyses + 1) if previous_state else 1

        return AnalyzerState(
            last_check_timestamp=datetime.now().isoformat() + "Z",
            last_check_position=last_position,
            last_analysis_id=analysis_id,
            total_analyses=total_analyses
        )
