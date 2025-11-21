-- ============================================================================
-- ADWS v2.0 State Management Database Schema
-- ============================================================================
-- Version: 1.0
-- Purpose: Core workflow lifecycle tracking and orchestration state
-- Issue: #1 - StateManager SQLite Schema & Core CRUD Operations
-- ============================================================================

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Enable Write-Ahead Logging for better concurrency
PRAGMA journal_mode = WAL;

-- ============================================================================
-- Workflows table: Core orchestration state
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflows (
    -- Phase 1: Identity & Core
    workflow_id TEXT PRIMARY KEY NOT NULL,
    workflow_name TEXT NOT NULL,
    workflow_type TEXT NOT NULL DEFAULT 'standard' CHECK(workflow_type IN (
        'standard', 'tdd', 'plan-only', 'test-only', 'review-only'
    )),
    issue_number INTEGER,  -- Phase 1 ✅ CRITICAL (tac-7 GitHub tracking)

    -- Phase 1: Lifecycle
    state TEXT NOT NULL CHECK(state IN (
        'created', 'initialized', 'running', 'paused',
        'completed', 'failed', 'cancelled', 'stuck', 'archived'
    )),

    -- Phase 1: Timestamps (UTC, ISO 8601 format)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    archived_at TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Phase 1: Git Context (tac-7 integration)
    branch_name TEXT,  -- Phase 1 ✅ CRITICAL (git branch tracking)
    base_branch TEXT DEFAULT 'main',  -- Phase 1 ✅ (base branch for PR)

    -- Phase 1: Resources (tac-7 integration)
    worktree_path TEXT,  -- Phase 1 ✅ CRITICAL (git worktree location)

    -- Phase 1: Metadata
    tags TEXT,  -- JSON array: ["frontend", "api", "database"]
    metadata TEXT,  -- JSON object for extensibility

    -- Phase 1: Result tracking
    exit_code INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Phase 1: Statistics
    cost_usd REAL DEFAULT 0.0,  -- Renamed from total_cost for clarity
    total_tokens INTEGER DEFAULT 0,

    -- Phase 3: Resource Allocation (added for Phase 3)
    backend_port INTEGER CHECK (backend_port IS NULL OR (backend_port >= 9100 AND backend_port <= 9199)),
    frontend_port INTEGER CHECK (frontend_port IS NULL OR (frontend_port >= 9200 AND frontend_port <= 9299)),

    -- Phase 3: Classification (added for Phase 3)
    issue_class TEXT CHECK (issue_class IS NULL OR issue_class IN (
        'feature', 'bug', 'test', 'refactor', 'docs', 'chore'
    )),

    -- Phase 3: Model Configuration (added for Phase 3)
    model_set TEXT DEFAULT 'base' CHECK (model_set IN ('base', 'fast', 'powerful')),

    -- Phase 3: Advanced Statistics (added for Phase 3)
    phase_count INTEGER DEFAULT 0 CHECK (phase_count >= 0),

    -- Constraints
    CHECK(state = 'archived' OR archived_at IS NULL),
    CHECK(state NOT IN ('running', 'paused', 'completed', 'failed') OR started_at IS NOT NULL)
);

-- Indexes for fast queries on workflows table
CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state);
CREATE INDEX IF NOT EXISTS idx_workflows_created_at ON workflows(created_at);
CREATE INDEX IF NOT EXISTS idx_workflows_last_activity ON workflows(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_workflows_workflow_type ON workflows(workflow_type);
CREATE INDEX IF NOT EXISTS idx_workflows_state_created ON workflows(state, created_at);
CREATE INDEX IF NOT EXISTS idx_workflows_issue_number ON workflows(issue_number);  -- Phase 1 ✅ (tac-7 integration)

-- Phase 3 indexes (added for Phase 3)
CREATE INDEX IF NOT EXISTS idx_workflows_backend_port ON workflows(backend_port) WHERE backend_port IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflows_frontend_port ON workflows(frontend_port) WHERE frontend_port IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflows_issue_class ON workflows(issue_class) WHERE issue_class IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflows_model_set ON workflows(model_set);

-- ============================================================================
-- Workflow phases table: Track phase execution history
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,

    -- Phase identification
    phase_name TEXT NOT NULL CHECK(phase_name IN (
        'plan', 'build', 'test', 'review', 'deploy',
        'generate_tests', 'verify_red', 'verify_green', 'refactor'
    )),
    phase_index INTEGER NOT NULL,

    -- Execution state
    state TEXT NOT NULL CHECK(state IN (
        'pending', 'running', 'completed', 'failed', 'skipped'
    )),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,

    -- Results
    exit_code INTEGER,
    error_message TEXT,

    -- Retry tracking
    attempt_number INTEGER DEFAULT 1,
    max_attempts INTEGER DEFAULT 3,

    -- LLM usage metrics
    llm_requests INTEGER DEFAULT 0,
    llm_tokens_input INTEGER DEFAULT 0,
    llm_tokens_output INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(workflow_id, phase_name, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_phases_workflow_id ON workflow_phases(workflow_id);
CREATE INDEX IF NOT EXISTS idx_phases_state ON workflow_phases(state);
CREATE INDEX IF NOT EXISTS idx_phases_phase_name ON workflow_phases(phase_name);

-- ============================================================================
-- Workflow events table: Audit trail and debugging
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,

    -- Event details
    event_type TEXT NOT NULL CHECK(event_type IN (
        'workflow_created', 'workflow_state_changed', 'phase_started',
        'phase_completed', 'phase_failed', 'workflow_paused',
        'workflow_resumed', 'workflow_cancelled', 'workflow_archived',
        'resource_allocated', 'resource_released', 'error_occurred'
    )),
    phase_name TEXT,

    -- State transition (for workflow_state_changed events)
    from_state TEXT,
    to_state TEXT,

    -- Event data
    message TEXT,
    metadata TEXT,  -- JSON object

    -- Timestamp
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_workflow_id ON workflow_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON workflow_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON workflow_events(created_at);

-- ============================================================================
-- Workflow metrics table: Aggregated statistics
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Aggregation period
    metric_date DATE NOT NULL,
    workflow_type TEXT NOT NULL,

    -- Counts
    total_workflows INTEGER DEFAULT 0,
    completed_workflows INTEGER DEFAULT 0,
    failed_workflows INTEGER DEFAULT 0,
    cancelled_workflows INTEGER DEFAULT 0,

    -- Durations (seconds)
    avg_duration_seconds REAL,
    min_duration_seconds REAL,
    max_duration_seconds REAL,

    -- Costs
    total_cost_usd REAL DEFAULT 0.0,
    avg_cost_usd REAL DEFAULT 0.0,

    -- Success rate
    success_rate REAL,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(metric_date, workflow_type)
);

CREATE INDEX IF NOT EXISTS idx_metrics_date ON workflow_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_metrics_type ON workflow_metrics(workflow_type);

-- ============================================================================
-- Views for common queries
-- ============================================================================

-- Active workflows view: Shows currently executing workflows
CREATE VIEW IF NOT EXISTS active_workflows AS
SELECT
    workflow_id,
    workflow_name,
    state,
    workflow_type,
    created_at,
    started_at,
    last_activity_at,
    CASE
        WHEN state = 'running' AND
             (JULIANDAY('now') - JULIANDAY(last_activity_at)) * 24 > 1
        THEN 1
        ELSE 0
    END as appears_stuck
FROM workflows
WHERE state IN ('initialized', 'running', 'paused');

-- Workflow summary view: Complete workflow information with computed fields
CREATE VIEW IF NOT EXISTS workflow_summary AS
SELECT
    workflow_id,
    workflow_name,
    state,
    workflow_type,
    tags,
    created_at,
    started_at,
    completed_at,
    CAST(
        (JULIANDAY(COALESCE(completed_at, 'now')) - JULIANDAY(started_at)) * 24 * 60
        AS INTEGER
    ) as duration_minutes,
    total_cost,
    total_tokens,
    error_message
FROM workflows;
