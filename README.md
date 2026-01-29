# Local AI Orchestrator

Dynamic AI model routing with benchmark ingestion from OpenRouter, LMSYS, and HuggingFace.

## Features

- **Multi-source Benchmark Ingestion**: Fetches model data from OpenRouter, LMSYS Arena, and HuggingFace
- **Entity Resolution**: Matches models across sources using fuzzy matching
- **Dynamic Routing**: Routes requests based on quality, latency, and cost profiles
- **Complexity-Aware Routing**: Auto-adjusts model selection based on prompt difficulty
- **Fallback Handling**: Automatic retry with next-ranked model on failures
- **Circuit Breaker**: Disables failing models with cooldown
- **Security**: URL validation (SSRF protection) and API key authentication
- **Resilience**: Offline cache fallback and automatic data pruning

## Quick Start

```bash
# Install dependencies
poetry install

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run the server
poetry run uvicorn orchestrator.api:app --reload
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat with auto-routing |
| `/v1/models/rankings` | GET | Get ranked models by profile |
| `/v1/models` | GET | List available models |
| `/v1/routing_profiles` | GET | List routing profiles |
| `/health` | GET | Health check |

## Routing Profiles

| Profile | Best For |
|---------|----------|
| `quality` | Maximum accuracy, creative tasks |
| `balanced` | General use (default) |
| `speed` | Low latency, simple queries |
| `budget` | Cost optimization |
| `long_context` | Large documents |

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Required |
| `DATABASE_URL` | Database connection | `sqlite:///data/orchestrator.db` |
| `ORCHESTRATOR_API_KEY` | API authentication key | None (disabled) |
| `ORCHESTRATOR_ALLOWED_DOMAINS` | URL allowlist | Empty (all external) |
| `ORCHESTRATOR_METRIC_RETENTION_DAYS` | Days to keep metrics | 30 |
| `ORCHESTRATOR_OFFLINE_MODE_ENABLED` | Enable cache fallback | true |

## Development

```bash
# Run all tests
poetry run pytest

# Run canary tests (fast CI/CD)
poetry run pytest -m canary

# Run integration tests
poetry run pytest -m integration

# Run performance benchmarks
poetry run pytest -m performance

# Format and lint
poetry run ruff check src/ tests/
poetry run black src/ tests/
```

## Architecture

```
src/orchestrator/
├── adapters/         # OpenRouter, LMSYS, HuggingFace adapters
├── api/              # FastAPI application and routes
├── db/               # SQLAlchemy models and manager
├── http/             # HTTP client with retry logic
├── resolution/       # Entity matching across sources
├── routing/          # Scoring, profiles, router, complexity
├── scheduler/        # APScheduler background jobs
├── config.py         # Pydantic settings
├── security.py       # URL validation, API key auth
├── resilience.py     # Offline cache, data pruning
└── main.py           # Application entry point
```

## License

MIT
