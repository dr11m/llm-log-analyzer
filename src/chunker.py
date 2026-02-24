"""
Log Chunker for reverse log reading.

Reads log files from end to beginning (newest → oldest),
handles rotated logs (.zip), and supports checkpoint-based resumption.
"""
import re
import zipfile
from pathlib import Path
from typing import Iterator, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from src.utils.logger import logger
from .state_manager import LogPosition


@dataclass
class LogChunk:
    """A chunk of log lines."""
    lines: List[str]  # List of log lines
    start_position: LogPosition  # Position of first line in chunk
    end_position: LogPosition  # Position of last line in chunk
    estimated_tokens: int  # Estimated token count (for GLM-4 context)

    def __len__(self) -> int:
        """Return number of lines in chunk."""
        return len(self.lines)


class LogChunker:
    """
    Reads log files in reverse order (newest → oldest).

    Supports:
    - Reverse reading (from end to beginning)
    - Rotated logs (analyzer.log.1.zip, analyzer.log.2.zip)
    - Checkpoint resumption (start from specific position)
    - Token estimation (for GLM-4 context management)
    """

    # Loguru format: "YYYY-MM-DD HH:mm:ss.SSS | LEVEL | ..."
    TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")

    def __init__(
        self,
        log_file: str,
        chunk_size_lines: int = 2000,
        max_chunk_tokens: int = 0,
        retention_days: int = 7,
        bytes_per_token: int = 2
    ):
        """
        Initialize log chunker.

        Chunking modes:
        - Token-based (preferred): set max_chunk_tokens > 0.
          Reads lines until token budget per chunk is reached.
        - Line-based (fallback): set chunk_size_lines > 0, max_chunk_tokens = 0.
          Fixed number of lines per chunk.

        Args:
            log_file: Path to main log file
            chunk_size_lines: Lines per chunk (used when max_chunk_tokens = 0)
            max_chunk_tokens: Max tokens per chunk (0 = use line-based)
            retention_days: How far back to analyze
            bytes_per_token: Bytes-to-token ratio for estimation.
                             2 = conservative (good for logs with timestamps/numbers).
                             3-4 = for plain English text.
        """
        self._log_file = Path(log_file)
        self._chunk_size = chunk_size_lines
        self._max_tokens = max_chunk_tokens
        self._use_token_mode = max_chunk_tokens > 0
        self._retention_days = retention_days
        self._bytes_per_token = bytes_per_token

    def iter_chunks_reverse(
        self,
        start_position: Optional[LogPosition] = None
    ) -> Iterator[LogChunk]:
        """
        Yield log chunks in reverse order (newest → oldest).

        Args:
            start_position: Position to start from (or None to start from end)

        Yields:
            LogChunk objects in reverse chronological order

        Process:
        1. Start from current file (analyzer.log)
        2. Read last N lines → Chunk 1
        3. Read previous N lines → Chunk 2
        4. When file start reached → check for analyzer.log.1.zip
        5. Extract and read from rotated file
        6. Stop when:
           - Reached start_position timestamp
           - Retention limit (7 days) reached
        """
        logger.info(f"Starting reverse log chunking from: {self._log_file}")

        # Get all log files (current + rotated)
        log_files = self._get_log_files()
        logger.info(f"Found {len(log_files)} log files to analyze")

        total_lines_processed = 0
        stop_timestamp = self._parse_timestamp(start_position.timestamp) if start_position else None

        # Process files in reverse order (newest first)
        for log_file_path in log_files:
            logger.debug(f"Processing log file: {log_file_path}")

            # Read lines from file (all at once or in batches)
            lines = self._read_file_lines(log_file_path)
            if not lines:
                logger.warning(f"No lines in file: {log_file_path}")
                continue

            # Process lines in reverse order (newest first)
            file_lines_processed = 0
            chunk_lines = []

            for i in range(len(lines) - 1, -1, -1):  # Reverse iteration
                line = lines[i]

                # Check if we reached the checkpoint
                if stop_timestamp:
                    line_timestamp = self._extract_timestamp(line)
                    if line_timestamp and line_timestamp <= stop_timestamp:
                        logger.info(f"Reached checkpoint timestamp: {stop_timestamp}")
                        # Yield last chunk if not empty
                        if chunk_lines:
                            yield self._create_chunk(
                                chunk_lines,
                                file_lines_processed + total_lines_processed,
                                log_file_path.name
                            )
                        return

                chunk_lines.append(line)
                file_lines_processed += 1

                # Yield chunk when limit reached (token-based or line-based)
                should_yield = False
                if self._use_token_mode:
                    chunk_tokens = sum(len(l.encode("utf-8")) for l in chunk_lines) // self._bytes_per_token
                    should_yield = chunk_tokens >= self._max_tokens
                else:
                    should_yield = len(chunk_lines) >= self._chunk_size

                if should_yield:
                    yield self._create_chunk(
                        chunk_lines,
                        file_lines_processed + total_lines_processed,
                        log_file_path.name
                    )
                    chunk_lines = []

            # Yield remaining lines as last chunk
            if chunk_lines:
                yield self._create_chunk(
                    chunk_lines,
                    file_lines_processed + total_lines_processed,
                    log_file_path.name
                )

            total_lines_processed += file_lines_processed
            logger.debug(f"Processed {file_lines_processed} lines from {log_file_path.name}")

        logger.info(f"Completed reverse chunking. Total lines processed: {total_lines_processed}")

    def _get_log_files(self) -> List[Path]:
        """
        Get list of log files (current + rotated) in reverse chronological order.

        Returns:
            List of Path objects (newest first)

        Example:
            [analyzer.log, analyzer.log.1.zip, analyzer.log.2.zip, ...]
        """
        files = []

        # Add current file if exists
        if self._log_file.exists():
            files.append(self._log_file)

        # Find rotated files (analyzer.log.1.zip, analyzer.log.2.zip, ...)
        pattern = f"{self._log_file.name}.*.zip"
        parent_dir = self._log_file.parent

        rotated_files = sorted(
            parent_dir.glob(pattern),
            key=lambda p: self._extract_rotation_number(p),
            reverse=False  # 1.zip is newer than 2.zip
        )

        files.extend(rotated_files)

        # Filter by retention (check modification time)
        retention_cutoff = datetime.now() - timedelta(days=self._retention_days)
        filtered_files = []

        for file_path in files:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if mtime >= retention_cutoff:
                filtered_files.append(file_path)
            else:
                logger.debug(f"Skipping old file (beyond retention): {file_path}")

        return filtered_files

    def _extract_rotation_number(self, path: Path) -> int:
        """Extract rotation number from filename (e.g., analyzer.log.1.zip → 1)."""
        match = re.search(r"\.(\d+)\.zip$", path.name)
        return int(match.group(1)) if match else 0

    def _read_file_lines(self, file_path: Path) -> List[str]:
        """
        Read all lines from file (supports .zip).

        Args:
            file_path: Path to log file

        Returns:
            List of lines (without newline characters)
        """
        try:
            if file_path.suffix == ".zip":
                # Extract and read from zip
                with zipfile.ZipFile(file_path, "r") as zf:
                    # Assume single file in zip (rotated log archive)
                    names = zf.namelist()
                    if not names:
                        logger.warning(f"Empty zip file: {file_path}")
                        return []

                    # Read first file in zip
                    with zf.open(names[0], "r") as f:
                        content = f.read().decode("utf-8")
                        return content.splitlines()
            else:
                # Read regular file
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().splitlines()

        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return []

    def _create_chunk(
        self,
        lines: List[str],
        line_number: int,
        file_name: str
    ) -> LogChunk:
        """
        Create LogChunk from lines.

        Args:
            lines: List of log lines (in reverse order: newest first)
            line_number: Current line number
            file_name: Name of log file

        Returns:
            LogChunk object
        """
        # Reverse lines to normal order (oldest first within chunk)
        # This helps GLM-4 understand temporal flow
        lines_normal_order = list(reversed(lines))

        # Extract timestamps
        start_timestamp = self._extract_timestamp(lines_normal_order[0])
        end_timestamp = self._extract_timestamp(lines_normal_order[-1])

        # Create positions
        start_pos = LogPosition(
            timestamp=start_timestamp.isoformat() if start_timestamp else "",
            line_number=line_number - len(lines),
            file_name=file_name
        )

        end_pos = LogPosition(
            timestamp=end_timestamp.isoformat() if end_timestamp else "",
            line_number=line_number,
            file_name=file_name
        )

        # Estimate tokens
        total_bytes = sum(len(line.encode("utf-8")) for line in lines_normal_order)
        estimated_tokens = total_bytes // self._bytes_per_token

        return LogChunk(
            lines=lines_normal_order,
            start_position=start_pos,
            end_position=end_pos,
            estimated_tokens=estimated_tokens
        )

    def _extract_timestamp(self, line: str) -> Optional[datetime]:
        """
        Extract timestamp from log line.

        Args:
            line: Log line (e.g., "2026-02-07 03:00:15.123 | INFO | ...")

        Returns:
            datetime object or None if parsing failed
        """
        match = self.TIMESTAMP_PATTERN.match(line)
        if not match:
            return None

        try:
            timestamp_str = match.group(1)
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            return None

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parse ISO timestamp string to datetime.

        Args:
            timestamp_str: ISO format string (e.g., "2026-02-07T03:00:00Z")

        Returns:
            datetime object or None
        """
        try:
            # Remove 'Z' suffix if present
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1]

            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
