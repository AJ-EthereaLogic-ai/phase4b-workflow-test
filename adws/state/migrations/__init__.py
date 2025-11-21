"""
ADWS v2.0 State Management - Database Migrations

This module provides database migration utilities for evolving the ADWS state
management schema across versions.
"""

from adws.state.migrations.migrate import migrate_to_phase1

__all__ = ["migrate_to_phase1"]
