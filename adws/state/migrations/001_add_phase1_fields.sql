-- ============================================================================
-- Migration: Add Phase 1 fields to existing databases
-- Version: 001
-- Date: 2025-11-07
-- Description: Adds critical tac-7 integration fields for Phase 1
-- ============================================================================

-- Add new columns to workflows table
ALTER TABLE workflows ADD COLUMN issue_number INTEGER;
ALTER TABLE workflows ADD COLUMN branch_name TEXT;
ALTER TABLE workflows ADD COLUMN base_branch TEXT DEFAULT 'main';
ALTER TABLE workflows ADD COLUMN worktree_path TEXT;
ALTER TABLE workflows ADD COLUMN retry_count INTEGER DEFAULT 0;

-- Rename total_cost to cost_usd for clarity
-- SQLite doesn't support ALTER COLUMN RENAME, so we need to handle this in Python

-- Add new index for issue_number (tac-7 integration)
CREATE INDEX IF NOT EXISTS idx_workflows_issue_number ON workflows(issue_number);

-- Verify migration
SELECT
    COUNT(*) as total_workflows,
    COUNT(issue_number) as workflows_with_issue_number,
    COUNT(branch_name) as workflows_with_branch_name,
    COUNT(worktree_path) as workflows_with_worktree_path
FROM workflows;
