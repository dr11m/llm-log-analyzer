# Project Structure

## Purpose

AI Log Analyzer is a module for analyzing logs with an LLM. The project has two main flows: context generation from source artifacts and regular log analysis with report creation.

## Main directories and files

- `analyzer.py` — main entry for log analysis (manual/auto modes).
- `generate_context.py` — project context generation based on sources and docs.
- `src/` — core logic (orchestrator, chunker, reports, LLM client).
- `prompts/` — LLM prompt templates by language (`ru/`, `en/`).
- `single_prompts/` — one‑shot prompts for manual analysis in agent environments.
- `data/` — generated context files and analysis state.
- `reports/` — output log analysis reports.
- `config.example.yaml` — config template.
- `config.yaml` — local configuration (not for publication).
- `.env.example` — environment variable template.
- `.env` — local secrets (not for publication).
- `requirements.txt` — Python dependencies.
- `README.md`, `TODO.md`, `LICENSE` — docs and license.
- `article/` — author materials (not used by runtime code).

## Core modules (src)

| Module | Purpose |
|---|---|
| `src/orchestrator.py` | Analysis coordinator: chunks → LLM → combine → report → checkpoint |
| `src/chunker.py` | Reverse log reading, line/token chunking, rotation support |
| `src/prompt_builder.py` | System context assembly and prompt loading |
| `src/report_generator.py` | JSON and Markdown report generation |
| `src/state_manager.py` | Analysis state storage (`state.json`), atomic writes |
| `src/llm/base.py` | Abstract LLM client interface |
| `src/llm/glm_client.py` | GLM‑4.7 client implementation, retries, cost tracking |
| `src/utils/logger.py` | Basic project logger |

## Data and state

- `data/project_context.md` — LLM project context (generated/edited).
- `data/analysis_rules.md` — analysis rules (generated/edited).
- `data/state.json` — checkpoint: last analyzed position.
- `reports/*.json` and `reports/*.md` — analysis outputs.

## Database structure

There is **no** database in this project. All state and results are stored in the filesystem.

## External dependencies

- `requests` — HTTP client for LLM API.
- `pyyaml` — configuration loading.
- `python-dotenv` — environment variable loading.
