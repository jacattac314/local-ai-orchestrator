# Next Steps Plan

This document outlines the prioritized development roadmap for the Local AI Orchestrator project, organized by phase and priority level.

---

## Current State Summary

**Version**: 0.1.0 (Released January 29, 2025)

**Recent Accomplishments**:
- Ollama local models integration (zero-cost local inference)
- Budget management service with daily/weekly/monthly tracking
- Portfolio-grade documentation (README, ARCHITECTURE, DEPLOYMENT)
- Comprehensive CI/CD workflows
- Full test suite with canary, integration, and performance tests

**Architecture Health**: Production-ready foundation with clean separation of concerns, circuit breaker resilience, and multi-source data aggregation.

---

## Phase 1: Foundation Strengthening (Immediate Priority)

These items address gaps that should be resolved before adding new features.

### 1.1 Fix CHANGELOG.md Formatting
**Priority**: High
**Rationale**: The CHANGELOG has broken nested bullet formatting that affects readability. Documentation quality matters for a portfolio project.

**Action Items**:
- [ ] Clean up malformed bullet point nesting
- [ ] Ensure proper markdown rendering

### 1.2 Add Missing Test Coverage for New Features
**Priority**: High
**Rationale**: The recently added Ollama adapter and budget management features need dedicated test files.

**Action Items**:
- [ ] Create `tests/test_ollama_adapter.py` with:
  - Local model discovery tests
  - Fallback behavior when Ollama is unavailable
  - Cost calculation (zero-cost) verification
- [ ] Create `tests/test_budget.py` with:
  - Daily/weekly/monthly limit enforcement
  - Alert threshold triggering (80% warning)
  - Hard limit blocking behavior
  - Reset cycle logic

### 1.3 API Schema Documentation
**Priority**: Medium
**Rationale**: OpenAPI/Swagger documentation should be complete for all endpoints.

**Action Items**:
- [ ] Verify all endpoints have proper Pydantic schemas
- [ ] Add examples to schema docstrings
- [ ] Ensure `/docs` endpoint renders correctly

### 1.4 Error Handling Audit
**Priority**: Medium
**Rationale**: Consistent error responses across all endpoints improve API usability.

**Action Items**:
- [ ] Standardize error response format across all routes
- [ ] Add custom exception handlers for common failure modes
- [ ] Document error codes in API docs

---

## Phase 2: Version 0.2.0 Features (Short-term)

These align with the published roadmap for Q1 2025.

### 2.1 Redis Distributed Caching
**Priority**: High
**Rationale**: Required for horizontal scaling beyond single instance. Current in-memory caching doesn't share state.

**Dependencies**: None

**Action Items**:
- [ ] Add `redis` dependency to pyproject.toml
- [ ] Create `src/orchestrator/cache/redis_cache.py` adapter
- [ ] Implement cache interface abstraction (in-memory vs Redis)
- [ ] Add Redis configuration env vars (`REDIS_URL`, `REDIS_TTL`)
- [ ] Update docker-compose with Redis service
- [ ] Add integration tests for Redis caching

### 2.2 Request Quota Management
**Priority**: High
**Rationale**: Prevents abuse and enables fair usage policies. Natural extension of existing budget management.

**Dependencies**: Budget management service (completed)

**Action Items**:
- [ ] Create `src/orchestrator/quota/` module
- [ ] Implement rate limiting (requests per minute/hour)
- [ ] Add per-user/per-key quota tracking
- [ ] Create quota exceeded response handling
- [ ] Add quota status endpoint (`GET /v1/quota`)
- [ ] Add tests for quota enforcement

### 2.3 WebSocket Streaming Support
**Priority**: Medium
**Rationale**: Modern LLM APIs support streaming; users expect this for real-time responses.

**Dependencies**: None

**Action Items**:
- [ ] Add WebSocket endpoint for streaming completions
- [ ] Implement SSE (Server-Sent Events) as fallback
- [ ] Update SDK client with streaming support
- [ ] Add streaming examples to documentation
- [ ] Test streaming with various model providers

### 2.4 Enhanced Monitoring & Observability
**Priority**: Medium
**Rationale**: Production deployments need visibility into system health.

**Dependencies**: None

**Action Items**:
- [ ] Expand `/metrics` endpoint with additional counters:
  - Requests per profile
  - Circuit breaker state changes
  - Cache hit/miss ratios
  - Budget utilization percentage
- [ ] Add structured logging with correlation IDs
- [ ] Create Grafana dashboard template
- [ ] Document alerting recommendations

### 2.5 User Authentication & Authorization
**Priority**: Medium
**Rationale**: Multi-user scenarios require identity management beyond simple API keys.

**Dependencies**: Redis (for session storage)

**Action Items**:
- [ ] Implement JWT-based authentication
- [ ] Add user registration/management endpoints
- [ ] Create role-based access control (admin, user, readonly)
- [ ] Add per-user quota and budget tracking
- [ ] Update SDK with auth token management

---

## Phase 3: Version 0.3.0 Features (Medium-term)

These are more complex features for Q2 2025.

### 3.1 Custom Adapter Plugin System
**Priority**: High
**Rationale**: Enables community contributions and enterprise customization without core modifications.

**Dependencies**: None (but benefits from v0.2.0 stability)

**Action Items**:
- [ ] Define adapter plugin interface specification
- [ ] Create plugin discovery mechanism (entry points)
- [ ] Implement plugin lifecycle management (load, reload, unload)
- [ ] Add plugin configuration schema
- [ ] Create example plugin template repository
- [ ] Document plugin development guide

### 3.2 A/B Testing Framework
**Priority**: Medium
**Rationale**: Allows controlled experiments comparing routing strategies and models.

**Dependencies**: Enhanced analytics (v0.2.0)

**Action Items**:
- [ ] Design experiment configuration schema
- [ ] Implement traffic splitting logic
- [ ] Add experiment metrics collection
- [ ] Create experiment analysis endpoints
- [ ] Build experiment management CLI commands

### 3.3 GraphQL Endpoint
**Priority**: Low
**Rationale**: Provides flexible querying alternative to REST for complex clients.

**Dependencies**: None

**Action Items**:
- [ ] Add `strawberry-graphql` dependency
- [ ] Define GraphQL schema for models, rankings, analytics
- [ ] Implement resolvers
- [ ] Add subscription support for real-time updates
- [ ] Update documentation

### 3.4 Fine-grained Routing Rules
**Priority**: Medium
**Rationale**: Power users need conditional routing based on content patterns, user segments, etc.

**Dependencies**: Custom adapter plugins (3.1)

**Action Items**:
- [ ] Design rule specification DSL or JSON schema
- [ ] Implement rule evaluation engine
- [ ] Add rule management endpoints
- [ ] Create UI for rule configuration
- [ ] Test rule priority and conflict resolution

---

## Phase 4: Version 1.0.0 Preparation (Long-term)

Foundation for production-grade release.

### 4.1 OpenTelemetry Integration
**Priority**: High for v1.0
**Rationale**: Enterprise observability standard; required for production SLA.

**Action Items**:
- [ ] Add OpenTelemetry SDK dependencies
- [ ] Instrument all critical paths with spans
- [ ] Configure exporters (Jaeger, Zipkin, OTLP)
- [ ] Add trace context propagation
- [ ] Document observability setup

### 4.2 Multi-tenant Architecture
**Priority**: High for v1.0
**Rationale**: Enterprise customers need isolated environments.

**Action Items**:
- [ ] Design tenant isolation model
- [ ] Implement tenant-scoped data partitioning
- [ ] Add tenant management APIs
- [ ] Create tenant provisioning automation
- [ ] Test cross-tenant isolation

### 4.3 High Availability Guide
**Priority**: Medium for v1.0
**Rationale**: Production SLA requires documented HA setup.

**Action Items**:
- [ ] Document active-passive failover patterns
- [ ] Create Kubernetes HA manifests (multiple replicas, PDBs)
- [ ] Test leader election for scheduled tasks
- [ ] Document database HA considerations
- [ ] Add health check best practices

### 4.4 API Stability Guarantee
**Priority**: Required for v1.0
**Rationale**: Semantic versioning commitment for production users.

**Action Items**:
- [ ] Audit all public APIs for consistency
- [ ] Document deprecation policy
- [ ] Add API versioning strategy (path or header-based)
- [ ] Create migration guides template
- [ ] Lock public interface contracts

---

## Maintenance & Technical Debt

Ongoing items to address alongside feature work.

### M.1 Dependency Updates
- [ ] Regularly update dependencies (monthly cadence)
- [ ] Monitor for security advisories
- [ ] Test compatibility with new Python versions (3.12, 3.13)

### M.2 Performance Benchmarking
- [ ] Establish baseline performance metrics
- [ ] Add load testing to CI (k6 or locust)
- [ ] Track routing latency regression

### M.3 Documentation Freshness
- [ ] Keep ARCHITECTURE.md in sync with code changes
- [ ] Update SDK examples when API changes
- [ ] Maintain troubleshooting guide

---

## Recommended Starting Point

For the next development session, the recommended priority order is:

1. **Fix CHANGELOG.md formatting** - Quick win, improves presentation
2. **Add tests for Ollama adapter and budget management** - Ensures recent work is properly validated
3. **Begin Redis caching implementation** - Highest-impact v0.2.0 feature

This sequence provides immediate quality improvements while building toward the next release milestone.

---

## Notes

- This plan is intentionally conservative; each phase should be completed before moving to the next
- Dependencies between items are noted; respect these to avoid rework
- Consider community feedback on feature priorities as the project gains users
- Portfolio value comes from depth, not breadth - better to have fewer well-implemented features

---

*Last updated: 2025-02-02*
