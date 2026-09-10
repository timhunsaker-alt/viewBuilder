"""XML field mapping & lookup routes (FR-011/FR-012, spec.md User Story 4).

Mounted now (Phase 2 Foundational, T008) so `/api/v1` carries a stable route surface as
soon as the feature lands, but its actual endpoints (`POST /xml-field-mappings`,
`GET /xml-field-mappings`, `GET /xml-field-mappings/{id}`,
`POST /xml-field-mappings/{id}/versions`, `POST /xml-field-mappings/{id}/lookup`) are
User-Story-4 scope (tasks.md T046/T047) and are intentionally not implemented in this
MVP checkpoint (User Story 1 only) — the `xml_field_mapping`/`xml_field_mapping_version`
tables this router will eventually serve already exist as of this migration (see
src/models/xml_field_mapping.py) so US4 can be added without further schema changes.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/xml-field-mappings", tags=["xml-field-mappings"])
