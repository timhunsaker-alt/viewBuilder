"""Reconciliation routes (FR-009/FR-010, spec.md User Story 3).

Mounted now (Phase 2 Foundational, T008) so `/api/v1` carries a stable route surface as
soon as the feature lands, but its actual endpoints
(`POST /view-definitions/{id}/reconcile`, `GET /view-definitions/{id}/reconciliations`,
`GET /reconciliations/{id}`) are User-Story-3 scope (tasks.md T040/T041) and are
intentionally not implemented in this MVP checkpoint (User Story 1 only) — the
`reconciliation_run` table this router will eventually serve already exists as of this
migration (see src/models/reconciliation.py) so US3 can be added without further schema
changes.
"""

from fastapi import APIRouter

router = APIRouter(tags=["reconciliation"])
