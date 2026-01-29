# Local AI Orchestrator

Dynamic AI model routing with benchmark ingestion from OpenRouter, LMSYS, and HuggingFace.

## Features

- **Multi-source Benchmark Ingestion**: Fetches model data from OpenRouter, LMSYS Arena, and HuggingFace
- **Entity Resolution**: Matches models across sources using fuzzy matching
- **Dynamic Routing**: Routes requests based on quality, latency, and cost profiles
- **Fallback Handling**: Automatic retry with next-ranked model on failures
- **Circuit Breaker**: Disables failing models with cooldown

## Quick Start

```bash
# Install dependencies
poetry install

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run the server
make run
```

## Development

```bash
# Format code
make format

# Run lints
make lint

# Run tests
make test
```

## API Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat endpoint with routing
- `GET /v1/models/ranked` - Get ranked models by profile
- `GET /health` - Health check

## Configuration

Set these environment variables:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `DATABASE_URL` | Database path (default: `sqlite:///data/orchestrator.db`) |

## License

MIT
