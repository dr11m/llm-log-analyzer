# AI Log Analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

> Standalone AI-powered log analyzer. Drop into any project.
> The model does all the thinking — no hardcoded rules.

[English](#english) | [Русский](#русский)

---

# English

## Overview

AI Log Analyzer is a standalone module that uses LLM APIs to analyze application logs. It reads your project's source code to understand what the system does, then analyzes logs to find issues, detect anomalies, and generate actionable reports.

**Key idea:** No hardcoded rules. The AI model decides what's important based on your project's context and customizable prompts.

**Works with any project** — just point it to your codebase and log files.

## Status

This version is still rough and not fully abstracted. It uses a specific LLM provider, and context generation is tied to Python project structure. I (the author) typically customize and adapt the module per project using simple prompts with lightweight models in agent environments. I believe anyone can expand this idea, improve it, and tailor it to their goals — feedback and ideas for improving prompts and code are always welcome.

See `TODO.md` for the current roadmap.

## How It Works

### Phase 1: Context Generation (run once)

```
Your Project (code, docs, configs)
         │
         ▼
   generate_context.py ──► LLM API
                           │
                           ▼
              data/project_context.md   ◄── you can edit these
              data/analysis_rules.md    ◄── to add your own rules
```

The script scans your project and uses the LLM to generate two context documents:
- **project_context.md** — what the system does, components, dependencies, normal behavior
- **analysis_rules.md** — classification rules (CRITICAL/MEDIUM/LOW), what is and isn't a problem

You can edit these files to add domain knowledge the model might have missed.

### Phase 2: Log Analysis (run regularly)

```
Log File ──► Chunker ──► [Chunk 1] ──► LLM ──► Analysis 1 ─┐
                         [Chunk 2] ──► LLM ──► Analysis 2 ─┤
                         [Chunk 3] ──► LLM ──► Analysis 3 ─┤
                         ...                                │
                         [Chunk N] ──► LLM ──► Analysis N ─┤
                                                            ▼
                                                    LLM (Combine)
                                                    + Deduplication
                                                    + Trend Detection
                                                    + Anomaly Detection
                                                            │
                                                            ▼
                                                Report (JSON + Markdown)
```

1. Reads N chunks from the end of the log (newest first)
2. Each chunk is analyzed independently by the LLM (N API calls)
3. All analyses are combined into a final report (1 API call)
4. The combine step handles deduplication, trend detection, and cross-chunk anomaly detection

**Total: N+1 API calls per analysis** (default: 5 chunks + 1 combine = 6 calls)

## Architecture

```
log_analyzer/
├── generate_context.py        # Phase 1: scan project → LLM → data/*.md
├── analyzer.py             # Phase 2: analyze logs → LLM → report
├── config.yaml             # Your configuration (gitignored)
├── config.example.yaml     # Config template
├── .env / .env.example     # API keys
├── requirements.txt
├── prompts/                # Customizable AI prompts (one subdir per language)
│   ├── ru/                     # Russian prompts (default)
│   │   ├── analyze_chunk.txt
│   │   ├── create_report.txt
│   │   ├── create_report_with_anomalies.txt
│   │   └── generate_context.txt
│   └── en/                     # English prompts
│       ├── analyze_chunk.txt
│       ├── create_report.txt
│       ├── create_report_with_anomalies.txt
│       └── generate_context.txt
├── single_prompts/         # One-shot prompt templates for manual analysis
├── data/                   # Generated context (editable)
│   ├── project_context.md      # Project description for the model
│   ├── analysis_rules.md       # Issue classification rules
│   └── state.json              # Checkpoint (last analysis position)
├── reports/                # Generated reports
│   ├── YYYYMMDD_HHMMSS.json   # Machine-readable
│   └── YYYYMMDD_HHMMSS.md     # Human-readable
└── src/
    ├── orchestrator.py         # Main coordinator
    ├── chunker.py              # Reverse log reader (newest → oldest)
    ├── prompt_builder.py       # Loads context + prompt templates
    ├── report_generator.py     # JSON + Markdown report generation
    ├── state_manager.py        # Checkpoint persistence
    └── llm/                    # LLM abstraction layer
        ├── base.py             # Abstract base class (BaseLLMClient)
        └── glm_client.py       # GLM-4.7 implementation
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp config.example.yaml config.yaml
cp .env.example .env  # optional if you prefer environment variables
# Edit .env (or export GLM_API_KEY/GLM_BASE_URL in your shell)
# Edit config.yaml: set path to your log file

# 3. Generate project context (run once, or when project changes)
python generate_context.py --project-dir /path/to/your/project

# 4. Review and edit generated context (optional)
# data/project_context.md — project description for the model
# data/analysis_rules.md  — classification rules

# 5. Run analysis
python analyzer.py --mode manual

# 6. Check reports
# reports/YYYYMMDD_HHMMSS.md   (human-readable)
# reports/YYYYMMDD_HHMMSS.json (machine-readable)
```

## Configuration

### .env

You can use a `.env` file or set these variables in your environment.

```
GLM_API_KEY=your_api_key_here
GLM_BASE_URL=https://api.z.ai/api/paas/v4/
# Alternative (Anthropic-compatible endpoint):
# GLM_BASE_URL=https://api.z.ai/api/anthropic
```

### config.yaml

| Parameter | Default | Description |
|-----------|---------|-------------|
| `project.log_file` | — | Path to your log file |
| `project.retention_days` | `7` | How far back to analyze |
| `api.model` | `glm-4.7-flash` | LLM model name |
| `api.prompts_language` | `ru` | Report language (`ru` or `en`) |
| `api.temperature` | `0.3` | Sampling temperature (0–1) |
| `api.pricing.input_per_1k` | `0.001` | Input token price per 1K (USD) |
| `api.pricing.output_per_1k` | `0.002` | Output token price per 1K (USD) |
| `analysis.num_chunks` | `5` | Number of log chunks |
| `analysis.max_total_tokens` | `0` | Token budget (0 = use line-based) |
| `analysis.chunk_size_lines` | `2000` | Lines per chunk (fallback) |
| `analysis.max_cost_usd` | `1.0` | Safety cost limit |
| `analysis.combine_prompt` | `create_report_with_anomalies` | Combine prompt name |
| `mode.check_interval_hours` | `3` | Auto mode interval |

### Chunking Modes

**Line-based** (default): Fixed number of lines per chunk.
```yaml
analysis:
  num_chunks: 5
  chunk_size_lines: 2000   # 5 x 2000 = 10,000 lines
  max_total_tokens: 0      # 0 = disabled
```

**Token-based**: Total token budget split across chunks.
```yaml
analysis:
  num_chunks: 5
  max_total_tokens: 150000  # 150K / 5 = 30K tokens per chunk
```

## CLI Reference

```bash
# Manual analysis with default settings
python analyzer.py --mode manual

# Specify number of chunks
python analyzer.py --mode manual --num-chunks 3

# Token-based chunking
python analyzer.py --mode manual --max-tokens 150000 --num-chunks 5

# Automatic mode (runs every N hours)
python analyzer.py --mode auto
python analyzer.py --mode auto --interval 2

# Generate/regenerate project context
python generate_context.py --project-dir /path/to/project
python generate_context.py --project-dir /path/to/project --force
```

## Customization

This is where the real power of the tool lies. Everything is designed to be tweaked and experimented with.

### Report Language

Prompts live in `prompts/ru/` (Russian) and `prompts/en/` (English). The prompt language drives the LLM's output language — switching to `en` will produce English reports.

Set in `config.yaml`:
```yaml
api:
  prompts_language: "ru"   # or "en"
```

Or override per run in `generate_context.py`:
```bash
python generate_context.py --project-dir .. --language en
```

You can also add more languages by creating a new subdirectory (e.g. `prompts/de/`) and placing translated copies of all 4 prompt files there, then setting `prompts_language: "de"` in your config.

### Prompts — Experiment Freely

All prompts are in `prompts/{language}/` and **fully customizable**. The prompts have a huge impact on what the model finds and how it reports — feel free to experiment:

- **analyze_chunk.txt** — what the model looks for in each log chunk. Try adjusting severity thresholds, adding specific patterns to watch for, or changing the output detail level
- **create_report.txt** — how to combine analyses (dedup + trends). Tune how aggressively duplicates are merged or how trends are detected
- **create_report_with_anomalies.txt** — combine + cross-chunk anomaly detection. The anomaly detection logic is entirely prompt-driven — you can make it more or less sensitive
- **generate_context.txt** — how to extract project context from source code. Adjust what aspects of your project the model focuses on

Different prompt versions produce noticeably different reports. There's no single "correct" version — it depends on your project and what matters to you.

### Generated Context — Edit After Generation

After running `generate_context.py`, the model creates two documents in `data/`. These are starting points — **you should review and edit them**:

- **project_context.md** — the model's understanding of your project. Add domain knowledge, business rules, SLAs, or anything the model missed
- **analysis_rules.md** — classification rules for issues. Add custom severity rules, known issues to ignore, or project-specific thresholds

The better the context, the more relevant the analysis. The model generates a solid base, but your domain expertise makes it precise.

Example context files (showing the expected structure and level of detail) are provided in:
- [`data/project_context.example.md`](data/project_context.example.md)
- [`data/analysis_rules.example.md`](data/analysis_rules.example.md)

## Adding New LLM Providers

The default implementation uses GLM-4.7, but the architecture is provider-agnostic. You can plug in **any LLM** — OpenAI, Anthropic, local models, or anything with an API:

1. Create `src/llm/your_provider.py`
2. Inherit from `BaseLLMClient`
3. Implement 5 methods:

```python
from src.llm.base import BaseLLMClient, ChunkAnalysisResult

class YourClient(BaseLLMClient):
    def analyze_chunk(self, chunk_lines, prompt_template, system_context, chunk_position):
        ...
    def combine_analyses(self, chunk_results, combine_prompt, system_context):
        ...
    def send_prompt(self, user_prompt, system_context):
        ...
    def get_cost_stats(self):
        ...
    def reset_cost_stats(self):
        ...
```

4. Update `analyzer.py` to instantiate your client instead of `GLMClient`

The abstraction layer handles the rest — chunking, reporting, state management all stay the same regardless of which model you use.

## Cost

~$0.15-0.30 per analysis with GLM-4.7-flash (N+1 API calls).

---

## Example Report

<details>
<summary>Click to expand (MLOps/DevOps scenario)</summary>

```markdown
# Log Analysis Report
**Status**: 🔴 CRITICAL
**Period**: 2026-02-07 00:15:32 - 2026-02-07 12:45:18

## Summary
За последние 12 часов система обработала 48,231 запрос. Из них 12,847 (26.6%)
завершились ошибкой. Основная проблема — перегрузка PostgreSQL connection pool,
которая привела к каскадному росту latency API и таймаутам inference pipeline.
Обнаружена аномалия: резкий рост ошибок 5xx с 2.1% до 34.7% между 08:00 и 09:30.

## 🔴 CRITICAL Issues (2)

### 🔴 #1: PostgreSQL Connection Pool Exhaustion
Пул соединений исчерпан. 847 запросов получили ConnectionPoolError за 08:15-12:45.
Средняя latency: 45ms → 3200ms.

**Occurrences**: 847 | **Chunks**: 4 | **Trend**: worsening

**Evidence**:
2026-02-07 08:15:02.331 | ERROR | db.pool | ConnectionPoolError: max connections (20)
2026-02-07 12:44:58.112 | ERROR | db.pool | ConnectionPoolError: wait timeout 30s

**Recommendation**: Увеличить max_connections до 50, установить PgBouncer

### 🔴 #2: ML Model Inference Timeout
Inference превышает timeout 30s. 234 предсказания не выполнены.
GPU utilization: 78% → 12%. Возможен memory leak.

**Occurrences**: 234 | **Chunks**: 3 | **Trend**: worsening

**Evidence**:
2026-02-07 09:30:15.887 | ERROR | inference | TimeoutError: exceeded 30s
2026-02-07 12:41:33.445 | ERROR | inference | CUDA OOM: allocate 2.4GB

**Recommendation**: Перезапустить inference service, проверить memory leak

## 🟡 MEDIUM Issues (2)

### 🟡 #1: Redis Cache Miss Rate Spike
Cache hit rate: 92% → 41%. 15,234 запроса в БД напрямую.
**Recommendation**: Проверить TTL, увеличить maxmemory Redis

### 🟡 #2: Kafka Consumer Lag
Lag: 45,000 сообщений. Rate: 120 msg/s (норма: 500).
**Recommendation**: Масштабировать consumer group

## Anomalies (2)

### 🔴 #1: [rate_change] Рост 5xx в 47 раз
89 (чанк 5) → 4,231 (чанк 2). Коррелирует с исчерпанием connection pool.

### 🟡 #2: [new_pattern] Появление CUDA OOM
Не было в чанках 4-5. Первое появление в чанке 3, экспоненциальный рост.

## Trends
- 5xx: 2.1% → 34.7% (worsening)
- DB latency: 45ms → 3200ms (worsening)
- Cache hit: 92% → 41% (worsening)
- GPU memory: 62% → 98% (worsening)

## Recommendations
1. [URGENT] Перезапустить inference service
2. [URGENT] Увеличить PostgreSQL max_connections
3. Установить PgBouncer
4. Увеличить maxmemory Redis
5. Мониторинг GPU memory с алертом на 85%

## Statistics
- **Lines Analyzed**: 10,000
- **Chunks**: 5 | **API Requests**: 6
- **Cost**: $0.2847 USD | **Duration**: 142.3s
```

</details>

---

# Русский

## Обзор

AI Log Analyzer — standalone-модуль для автоматического анализа логов с помощью LLM API. Он изучает исходный код вашего проекта, чтобы понять, как работает система, а затем анализирует логи — находит проблемы, обнаруживает аномалии и формирует отчёты с рекомендациями.

**Ключевая идея:** Никакой захардкоженной логики. Модель сама решает, что важно, на основе контекста вашего проекта и настраиваемых промптов.

**Работает с любым проектом** — просто укажите путь к кодовой базе и лог-файлу.

## Статус

Эта версия пока достаточно сырая и не до конца абстрактна. Она использует конкретную LLM, а генерация контекста привязана к структуре Python‑кода. Я (автор) обычно кастомизирую и немного адаптирую модуль под каждый проект через простые запросы к легким моделям в агентных средах. Уверен, что каждый сможет раскрутить эту идею, улучшить и подогнать под свои цели — всегда рад фидбеку и идеям по улучшению промптов и кода.

Roadmap: `TODO.md` (English).

## Как это работает

### Фаза 1: Генерация контекста (один раз)

```
Ваш проект (код, docs, конфиги)
         │
         ▼
   generate_context.py ──► LLM API
                           │
                           ▼
              data/project_context.md   ◄── можно редактировать
              data/analysis_rules.md    ◄── добавлять свои правила
```

Скрипт сканирует проект и через LLM генерирует два файла:
- **project_context.md** — что делает система, компоненты, зависимости, нормальное поведение
- **analysis_rules.md** — правила классификации (CRITICAL/MEDIUM/LOW)

### Фаза 2: Анализ логов (регулярно)

```
Лог-файл ──► Chunker ──► [Чанк 1] ──► LLM ──► Анализ 1 ─┐
                          [Чанк 2] ──► LLM ──► Анализ 2 ─┤
                          ...                              │
                          [Чанк N] ──► LLM ──► Анализ N ─┤
                                                           ▼
                                                   LLM (Объединение)
                                                   + Дедупликация
                                                   + Тренды
                                                   + Поиск аномалий
                                                           │
                                                           ▼
                                                Отчёт (JSON + Markdown)
```

**Итого: N+1 запросов к API** (по умолчанию: 5 + 1 = 6)

## Архитектура

```
log_analyzer/
├── generate_context.py        # Фаза 1: проект → LLM → data/*.md
├── analyzer.py             # Фаза 2: логи → LLM → отчёт
├── config.yaml             # Конфигурация (gitignored)
├── config.example.yaml     # Шаблон
├── .env / .env.example     # API-ключи
├── prompts/                # Настраиваемые промпты (по одной папке на язык)
│   ├── ru/                     # Русские промпты (по умолчанию)
│   │   ├── analyze_chunk.txt
│   │   ├── create_report.txt
│   │   ├── create_report_with_anomalies.txt
│   │   └── generate_context.txt
│   └── en/                     # Английские промпты
│       ├── analyze_chunk.txt
│       ├── create_report.txt
│       ├── create_report_with_anomalies.txt
│       └── generate_context.txt
├── single_prompts/         # Шаблоны промптов для разового анализа
├── data/                   # Контекст (редактируемый)
│   ├── project_context.md
│   ├── analysis_rules.md
│   └── state.json
├── reports/                # Отчёты
└── src/
    ├── orchestrator.py
    ├── chunker.py
    ├── prompt_builder.py
    ├── report_generator.py
    ├── state_manager.py
    └── llm/
        ├── base.py             # Абстрактный класс
        └── glm_client.py       # GLM-4.7 реализация
```

## Быстрый старт

```bash
# 1. Установка
pip install -r requirements.txt

# 2. Настройка
cp config.example.yaml config.yaml
cp .env.example .env  # необязательно, если используете переменные окружения
# Отредактируйте .env (или экспортируйте GLM_API_KEY/GLM_BASE_URL)
# Отредактируйте config.yaml

# 3. Генерация контекста
python generate_context.py --project-dir /путь/к/проекту

# 4. Анализ
python analyzer.py --mode manual

# 5. Отчёты в reports/
```

## Конфигурация

### .env

Можно использовать `.env` или экспортировать переменные окружения.

```
GLM_API_KEY=ваш_ключ
GLM_BASE_URL=https://api.z.ai/api/paas/v4/
# Альтернативный (Anthropic-совместимый) эндпоинт:
# GLM_BASE_URL=https://api.z.ai/api/anthropic
```

### config.yaml

| Параметр | Умолчание | Описание |
|----------|-----------|----------|
| `project.log_file` | — | Путь к лог-файлу |
| `api.temperature` | `0.3` | Температура сэмплинга (0–1) |
| `api.pricing.input_per_1k` | `0.001` | Цена входных токенов за 1K (USD) |
| `api.pricing.output_per_1k` | `0.002` | Цена выходных токенов за 1K (USD) |
| `analysis.num_chunks` | `5` | Количество чанков |
| `analysis.max_total_tokens` | `0` | Бюджет токенов (0 = по строкам) |
| `analysis.chunk_size_lines` | `2000` | Строк на чанк (fallback) |
| `analysis.max_cost_usd` | `1.0` | Лимит стоимости |
| `analysis.combine_prompt` | `create_report_with_anomalies` | Промпт объединения |

### Режимы чанкинга

**По строкам** (по умолчанию):
```yaml
num_chunks: 5
chunk_size_lines: 2000    # 5 x 2000 = 10,000 строк
max_total_tokens: 0       # отключено
```

**По токенам**:
```yaml
num_chunks: 5
max_total_tokens: 150000  # 150K / 5 = 30K на чанк
```

## CLI

```bash
python analyzer.py --mode manual                              # базовый
python analyzer.py --mode manual --num-chunks 3               # 3 чанка
python analyzer.py --mode manual --max-tokens 150000          # по токенам
python analyzer.py --mode auto --interval 2                   # авто
python generate_context.py --project-dir .. --force              # контекст
```

## Кастомизация

### Язык отчётов

Промпты хранятся в `prompts/ru/` (русский) и `prompts/en/` (английский). Язык промптов определяет язык отчётов — переключить на `en` означает английские отчёты.

Настройка в `config.yaml`:
```yaml
api:
  prompts_language: "ru"   # или "en"
```

Переопределение при генерации контекста:
```bash
python generate_context.py --project-dir .. --language ru
python generate_context.py --project-dir .. --language en
```

Добавить свой язык: создайте `prompts/de/` с переведёнными копиями всех 4 файлов и укажите `prompts_language: "de"` в конфиге.

### Промпты — экспериментируйте

Все промпты в `prompts/{language}/` полностью настраиваемы. Промпты **сильно влияют** на результат — разные версии дают разные отчёты. Экспериментируйте с порогами, форматом, детализацией.

### Сгенерированный контекст — редактируйте

После `generate_context.py` модель создаёт `data/project_context.md` и `data/analysis_rules.md`. Это стартовая точка, если хотите — дополните своими знаниями о проекте.

## Добавление LLM-провайдеров

По умолчанию используется GLM-4.7, но архитектура не привязана к провайдеру. Можно подключить **любую модель** — OpenAI, Anthropic, локальные модели.

Наследуйте `BaseLLMClient` из `src/llm/base.py` и реализуйте 5 методов:
`analyze_chunk`, `combine_analyses`, `send_prompt`, `get_cost_stats`, `reset_cost_stats`.

## Стоимость

~$0.15-0.30 за анализ (GLM-4.7-flash, N+1 запросов).

## Пример отчёта

<details>
<summary>Нажмите (MLOps/DevOps сценарий)</summary>

```markdown
# Log Analysis Report
**Status**: 🔴 CRITICAL
**Period**: 2026-02-07 00:15:32 - 2026-02-07 12:45:18

## Summary
48,231 запрос за 12 часов. 12,847 (26.6%) с ошибками.
Перегрузка PostgreSQL → каскадный рост latency → таймауты inference.
Аномалия: 5xx рост с 2.1% до 34.7%.

## 🔴 CRITICAL Issues (2)

### #1: Исчерпание пула PostgreSQL
847 ConnectionPoolError. Latency: 45ms → 3200ms.
Рекомендация: max_connections → 50, PgBouncer.

### #2: Таймаут инференса
234 таймаута. GPU: 78% → 12%. CUDA OOM.
Рекомендация: перезапуск, проверка memory leak.

## 🟡 MEDIUM Issues (2)

### #1: Cache Miss Rate
Hit rate: 92% → 41%. 15,234 запроса в БД.

### #2: Kafka Consumer Lag
45,000 сообщений. 120 msg/s (норма: 500).

## Anomalies (2)

### [rate_change] 5xx: рост в 47 раз
89 → 4,231. Коррелирует с pool exhaustion.

### [new_pattern] Появление CUDA OOM
Не было → экспоненциальный рост. Memory leak.

## Trends
- 5xx: 2.1% → 34.7% (worsening)
- DB latency: 45ms → 3200ms (worsening)
- GPU memory: 62% → 98% (worsening)

## Statistics
Lines: 10,000 | Chunks: 5 | Cost: $0.28 | Duration: 142s
```

</details>
