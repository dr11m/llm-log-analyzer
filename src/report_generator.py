"""
Report Generator for log analysis.

Generates JSON and Markdown reports from the model's combined analysis.
No hardcoded fields - renders whatever the model returns.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


class ReportGenerator:
    """Generates reports in JSON and Markdown formats."""

    def __init__(self, reports_dir: str = "./reports"):
        self._reports_dir = Path(reports_dir)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        analysis_id: str,
        combined_analysis: Dict[str, Any],
        statistics: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Generate both JSON and Markdown reports.

        Args:
            analysis_id: Analysis ID (timestamp)
            combined_analysis: Combined analysis from model
            statistics: Statistics dict (lines, tokens, cost)

        Returns:
            Dict with json_file and md_file paths
        """
        json_report = {
            "analysis_id": analysis_id,
            "generated_at": datetime.now().isoformat() + "Z",
            "statistics": statistics,
            **combined_analysis
        }

        md_report = self._build_markdown(json_report)

        json_file = self._save_json(analysis_id, json_report)
        md_file = self._save_markdown(analysis_id, md_report)

        return {"json_file": str(json_file), "md_file": str(md_file)}

    def _build_markdown(self, report: Dict[str, Any]) -> str:
        """Build Markdown report from JSON."""
        lines = []

        status = report.get("system_status", "UNKNOWN")
        shutdown = report.get("should_shutdown", False)

        # Header
        lines.append("# Log Analysis Report")
        lines.append(f"**Analysis ID**: {report['analysis_id']}")
        lines.append(f"**Date**: {report['generated_at']}")
        lines.append(f"**Status**: {self._status_emoji(status)} {status}")
        if shutdown:
            lines.append("**SHUTDOWN RECOMMENDED**")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Summary
        summary = report.get("summary", "")
        if summary:
            lines.append("## Summary")
            lines.append(summary)
            lines.append("")
            lines.append("---")
            lines.append("")

        # Time range
        time_range = report.get("time_range", {})
        if time_range:
            lines.append(f"**Period**: {time_range.get('start', 'N/A')} - {time_range.get('end', 'N/A')}")
            lines.append("")

        # Issues by severity
        issues = report.get("issues", [])
        if issues:
            for severity in ["CRITICAL", "MEDIUM", "LOW"]:
                severity_issues = [i for i in issues if i.get("severity") == severity]
                if severity_issues:
                    emoji = self._status_emoji(severity)
                    lines.append(f"## {emoji} {severity} Issues ({len(severity_issues)})")
                    lines.append("")
                    for idx, issue in enumerate(severity_issues, 1):
                        lines.extend(self._format_issue(issue, idx))
                    lines.append("---")
                    lines.append("")
        else:
            lines.append("## No Issues Found")
            lines.append("System appears healthy.")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Anomalies (cross-chunk patterns)
        anomalies = report.get("anomalies", [])
        if anomalies:
            lines.append(f"## Anomalies ({len(anomalies)})")
            lines.append("")
            for idx, anomaly in enumerate(anomalies, 1):
                severity = anomaly.get("severity", "LOW")
                emoji = self._status_emoji(severity)
                atype = anomaly.get("type", "unknown")
                lines.append(f"### {emoji} #{idx}: [{atype}] {anomaly.get('description', '')}")
                lines.append("")
                chunks = anomaly.get("chunks_compared", [])
                if chunks:
                    lines.append(f"**Chunks compared**: {chunks}")
                    lines.append("")
                evidence = anomaly.get("evidence", [])
                if evidence:
                    lines.append("**Evidence**:")
                    lines.append("```")
                    for e in evidence[:5]:
                        lines.append(str(e))
                    lines.append("```")
                    lines.append("")
            lines.append("---")
            lines.append("")

        # Trends
        trends = report.get("trends", [])
        if trends:
            lines.append("## Trends")
            lines.append("")
            for trend in trends:
                lines.append(f"- {trend}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Recommendations
        recommendations = report.get("recommendations", [])
        if recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for idx, rec in enumerate(recommendations, 1):
                lines.append(f"{idx}. {rec}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Statistics
        stats = report.get("statistics", {})
        if stats:
            lines.append("## Statistics")
            lines.append("")
            lines.append(f"- **Lines Analyzed**: {stats.get('total_lines_analyzed', 0):,}")
            lines.append(f"- **Chunks Processed**: {stats.get('chunks_processed', 0)}")
            lines.append(f"- **API Requests**: {stats.get('api_requests', 0)}")
            lines.append(f"- **Tokens Used**: {stats.get('total_tokens', 0):,}")
            lines.append(f"- **Cost**: ${stats.get('cost_usd', 0):.4f} USD")
            lines.append(f"- **Duration**: {stats.get('analysis_duration_seconds', 0):.1f}s")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by Log Analyzer*")

        return "\n".join(lines)

    def _format_issue(self, issue: Dict[str, Any], idx: int) -> List[str]:
        """Format single issue as Markdown."""
        lines = []

        severity = issue.get("severity", "LOW")
        emoji = self._status_emoji(severity)

        lines.append(f"### {emoji} #{idx}: {issue.get('title', 'Unknown')}")
        lines.append("")

        # Description
        desc = issue.get("description", "")
        if desc:
            lines.append(desc)
            lines.append("")

        # Count / chunks
        count = issue.get("total_count", issue.get("count", 0))
        chunks = issue.get("chunks_affected", 0)
        trend = issue.get("trend", "")
        meta_parts = []
        if count:
            meta_parts.append(f"**Occurrences**: {count}")
        if chunks:
            meta_parts.append(f"**Chunks**: {chunks}")
        if trend:
            meta_parts.append(f"**Trend**: {trend}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
            lines.append("")

        # Evidence
        evidence = issue.get("evidence", [])
        if evidence:
            lines.append("**Evidence**:")
            lines.append("```")
            for e in evidence[:5]:
                lines.append(str(e))
            lines.append("```")
            lines.append("")

        # Impact
        impact = issue.get("impact", "")
        if impact:
            lines.append(f"**Impact**: {impact}")
            lines.append("")

        # Recommendation
        rec = issue.get("recommendation", "")
        if rec:
            lines.append(f"**Recommendation**: {rec}")
            lines.append("")

        return lines

    def _status_emoji(self, status: str) -> str:
        """Get emoji for status."""
        return {
            "HEALTHY": "🟢", "DEGRADED": "🟡", "CRITICAL": "🔴",
            "MEDIUM": "🟡", "LOW": "🟢", "UNKNOWN": "⚪"
        }.get(status, "⚪")

    def _save_json(self, analysis_id: str, report: Dict[str, Any]) -> Path:
        """Save JSON report."""
        filepath = self._reports_dir / f"{analysis_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return filepath

    def _save_markdown(self, analysis_id: str, content: str) -> Path:
        """Save Markdown report."""
        filepath = self._reports_dir / f"{analysis_id}.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
