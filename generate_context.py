#!/usr/bin/env python3
"""
Generate Project Context for Log Analyzer.

Scans the project (source code, docs, configs) and uses LLM API
to generate context files that the log analyzer will use.

Usage:
    python generate_context.py --project-dir ..
    python generate_context.py --project-dir .. --output-dir ./data --force
"""
import os
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Set UTF-8 encoding for output
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
from src.llm import GLMClient


# File reading limits (chars) to stay within token budget
FILE_LIMITS = {
    "docs/workflow.md": 15000,
    "docs/architecture.md": 15000,
    "docs/configuration.md": 4000,
    "CLAUDE.md": 5000,
    "config.example.toml": 2000,
    "main.py": 1000,
}

# Python source file limit per file
PY_FILE_LIMIT = 5000
PY_MAX_FILES = 50


def scan_project(project_dir: Path) -> str:
    """
    Scan project directory and collect context.

    Args:
        project_dir: Path to project root

    Returns:
        Collected project content as a single string
    """
    parts = []

    # 1. Read all files in docs directory
    docs_dir = project_dir / "docs"
    docs_default_limit = 15000
    if docs_dir.exists() and docs_dir.is_dir():
        for doc_file in sorted(docs_dir.rglob("*")):
            if doc_file.is_file():
                rel_path = str(doc_file.relative_to(project_dir)).replace("\\", "/")
                char_limit = FILE_LIMITS.get(rel_path, docs_default_limit)
                try:
                    content = doc_file.read_text(encoding="utf-8")[:char_limit]
                    parts.append(f"### FILE: {rel_path}\n```\n{content}\n```\n")
                    print(f"  + {rel_path} ({len(content)} chars)")
                except Exception as e:
                    print(f"  ! Failed to read {rel_path}: {e}")

    # 2. Read other known files with limits
    for rel_path, char_limit in FILE_LIMITS.items():
        if rel_path.startswith("docs/"):
            continue
            
        file_path = project_dir / rel_path
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")[:char_limit]
                parts.append(f"### FILE: {rel_path}\n```\n{content}\n```\n")
                print(f"  + {rel_path} ({len(content)} chars)")
            except Exception as e:
                print(f"  ! Failed to read {rel_path}: {e}")

    # 2. Scan Python source files (class names, imports, key methods)
    src_dir = project_dir / "src"
    if src_dir.exists():
        py_files = sorted(src_dir.rglob("*.py"))[:PY_MAX_FILES]
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8")
                # Extract key parts: imports, class/def signatures
                summary = _extract_py_summary(content, PY_FILE_LIMIT)
                if summary.strip():
                    rel = py_file.relative_to(project_dir)
                    parts.append(f"### FILE: {rel}\n```python\n{summary}\n```\n")
                    print(f"  + {rel} ({len(summary)} chars, summary)")
            except Exception:
                pass

    if not parts:
        print("  ! No files found in project directory")
        return ""

    return "\n".join(parts)


def _extract_py_summary(content: str, limit: int) -> str:
    """
    Extract key parts from Python file: imports, class names, method signatures.
    """
    lines = content.split("\n")
    summary_lines = []
    total_chars = 0

    for line in lines:
        stripped = line.strip()
        # Keep: imports, class definitions, function definitions, docstrings (first line)
        if (stripped.startswith("import ")
                or stripped.startswith("from ")
                or stripped.startswith("class ")
                or stripped.startswith("def ")
                or stripped.startswith('"""')
                or stripped.startswith("# ")):
            if total_chars + len(line) > limit:
                break
            summary_lines.append(line)
            total_chars += len(line) + 1

    return "\n".join(summary_lines)


def generate_context(
    project_content: str,
    glm_client: GLMClient,
    prompts_dir: Path,
    language: str = "ru"
) -> tuple:
    """
    Send project content to GLM and get context documents.

    Args:
        project_content: Collected project content
        glm_client: API client
        prompts_dir: Path to the language-specific prompts directory
        language: Language code ("ru" or "en"), used for the system message

    Returns:
        Tuple of (project_context_md, analysis_rules_md)
    """
    # Load prompt template
    prompt_path = prompts_dir / "generate_context.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")

    # Fill in the project content
    prompt = prompt_template.replace("{project_content}", project_content)

    # System message depends on the selected language
    _system_messages = {
        "ru": "Ты эксперт по анализу программных проектов. Создай документацию для системы анализа логов.",
        "en": "You are an expert at analyzing software projects. Create documentation for a log analysis system.",
    }
    system_msg = _system_messages.get(language, _system_messages["en"])

    # Build messages
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]

    print("\nSending to GLM API...")
    response = glm_client.send_messages(messages)  # cost tracked inside client

    # Extract content from response
    if "content" in response:
        # Anthropic format
        content = response["content"][0]["text"]
    elif "choices" in response:
        # GLM format
        content = response["choices"][0]["message"]["content"]
    else:
        raise ValueError(f"Unknown response format: {list(response.keys())}")

    stats = glm_client.get_cost_stats()
    print(
        f"API response received "
        f"({stats['total_tokens']} tokens total, "
        f"${stats['total_cost_usd']:.4f})"
    )

    # Split into two documents
    return _split_documents(content)


def _split_documents(content: str) -> tuple:
    """
    Split GLM response into two documents using ===SEPARATOR=== marker.
    """
    separator = "===SEPARATOR==="

    if separator in content:
        parts = content.split(separator, 1)
        doc1 = parts[0].strip()
        doc2 = parts[1].strip()
    else:
        # Fallback: try to split by [DOCUMENT_2]
        if "[DOCUMENT_2]" in content:
            parts = content.split("[DOCUMENT_2]", 1)
            doc1 = parts[0].strip()
            doc2 = parts[1].strip()
        else:
            # Can't split - put everything in doc1
            doc1 = content
            doc2 = "# Analysis Rules\n\n(GLM did not generate separate rules. Please fill in manually.)"

    # Clean up markers
    doc1 = doc1.replace("[DOCUMENT_1]", "").strip()
    doc2 = doc2.replace("[DOCUMENT_2]", "").strip()

    return doc1, doc2


def save_documents(
    output_dir: Path,
    project_context: str,
    analysis_rules: str,
    force: bool = False
):
    """
    Save generated documents to output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    context_path = output_dir / "project_context.md"
    rules_path = output_dir / "analysis_rules.md"

    # Check existing files
    if not force:
        if context_path.exists():
            print(f"\n! {context_path} already exists. Use --force to overwrite.")
            return
        if rules_path.exists():
            print(f"\n! {rules_path} already exists. Use --force to overwrite.")
            return

    # Save
    context_path.write_text(project_context, encoding="utf-8")
    print(f"\nSaved: {context_path} ({len(project_context)} chars)")

    rules_path.write_text(analysis_rules, encoding="utf-8")
    print(f"Saved: {rules_path} ({len(analysis_rules)} chars)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate project context for log analyzer by scanning the project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan parent project and generate docs (Russian output, default)
  python generate_context.py --project-dir ..

  # English output
  python generate_context.py --project-dir .. --language en

  # Custom output directory
  python generate_context.py --project-dir .. --output-dir ./data

  # Overwrite existing files
  python generate_context.py --project-dir .. --force
        """
    )

    parser.add_argument(
        "--project-dir",
        required=True,
        help="Path to the project root directory to scan"
    )

    parser.add_argument(
        "--output-dir",
        default="./data",
        help="Directory to save generated docs (default: ./data)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files"
    )

    parser.add_argument(
        "--language",
        choices=["ru", "en"],
        default="ru",
        help="Language for generated context documents and prompts (default: ru)"
    )

    args = parser.parse_args()

    # Validate project dir
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"Project directory not found: {project_dir}")
        sys.exit(1)

    # Load .env (optional)
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print(f".env not found at {env_path}, falling back to environment variables")

    api_key = os.getenv("GLM_API_KEY")
    base_url = os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4/")

    if not api_key:
        print("GLM_API_KEY not set. Add it to .env or export it in your shell.")
        sys.exit(1)

    # Initialize GLM client with higher max_tokens for doc generation
    glm_client = GLMClient(
        api_key=api_key,
        base_url=base_url,
        model=os.getenv("GLM_MODEL", "glm-4.7-flash"),
        max_output_tokens=15000
    )

    # Scan project
    print(f"Scanning project: {project_dir}")
    project_content = scan_project(project_dir)

    if not project_content:
        print("No content found. Check --project-dir path.")
        sys.exit(1)

    print(f"\nCollected {len(project_content)} chars of project content")

    # Generate context via GLM
    prompts_dir = Path(__file__).parent / "prompts" / args.language
    project_context, analysis_rules = generate_context(
        project_content=project_content,
        glm_client=glm_client,
        prompts_dir=prompts_dir,
        language=args.language
    )

    # Save
    output_dir = Path(args.output_dir)
    save_documents(
        output_dir=output_dir,
        project_context=project_context,
        analysis_rules=analysis_rules,
        force=args.force
    )

    print("\nDone! Review and edit the generated files as needed.")


if __name__ == "__main__":
    main()
