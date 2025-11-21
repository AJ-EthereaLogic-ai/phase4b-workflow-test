-- ============================================================================
-- PHASE 3 SCHEMA UPDATES: Add 5 new fields + indexes + constraints
-- ============================================================================
-- File: adws/state/migrations/002_add_phase3_fields.sql
--
-- This migration adds Phase 3 fields to the workflows table.
-- It does NOT remove or modify Phase 1 or Phase 2 fields.
-- Schema remains backward compatible with existing Phase 1 data.
-- ============================================================================

-- Add Phase 3 fields to workflows table
ALTER TABLE workflows ADD COLUMN backend_port INTEGER
  CHECK (backend_port IS NULL OR (backend_port >= 9100 AND backend_port <= 9199));

ALTER TABLE workflows ADD COLUMN frontend_port INTEGER
  CHECK (frontend_port IS NULL OR (frontend_port >= 9200 AND frontend_port <= 9299));

ALTER TABLE workflows ADD COLUMN issue_class TEXT
  CHECK (issue_class IS NULL OR issue_class IN (
    'feature', 'bug', 'test', 'refactor', 'docs', 'chore'
  ));

ALTER TABLE workflows ADD COLUMN model_set TEXT DEFAULT 'base'
  CHECK (model_set IN ('base', 'fast', 'powerful'));

ALTER TABLE workflows ADD COLUMN phase_count INTEGER DEFAULT 0
  CHECK (phase_count >= 0);

-- Create indexes for Phase 3 queries
CREATE INDEX idx_workflows_backend_port ON workflows(backend_port)
  WHERE backend_port IS NOT NULL;

CREATE INDEX idx_workflows_frontend_port ON workflows(frontend_port)
  WHERE frontend_port IS NOT NULL;

CREATE INDEX idx_workflows_issue_class ON workflows(issue_class)
  WHERE issue_class IS NOT NULL;

CREATE INDEX idx_workflows_model_set ON workflows(model_set);

-- Verify migration
SELECT COUNT(*) as total_workflows,
       COUNT(CASE WHEN backend_port IS NOT NULL THEN 1 END) as with_backend_port,
       COUNT(CASE WHEN frontend_port IS NOT NULL THEN 1 END) as with_frontend_port,
       COUNT(CASE WHEN issue_class IS NOT NULL THEN 1 END) as with_issue_class,
       COUNT(CASE WHEN model_set IS NOT NULL THEN 1 END) as with_model_set
FROM workflows;
