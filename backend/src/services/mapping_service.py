import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.connection_config import ConnectionConfig
from src.models.enum_translation import EnumTranslationVersion
from src.models.mapping import MAPPING_KINDS, MappingDefinition, MappingVersion

logger = logging.getLogger("viewbuilder.mapping_service")


class MappingValidationError(Exception):
    """Raised when a mapping's connections/column links fail validation (FR-026)."""


class MappingService:
    """Create/version mapping definitions. Every save creates a new, immutable
    mapping_version row — an existing version is never mutated (Constitution Principle II).
    """

    def __init__(self, db: Session):
        self.db = db

    def _validate_connection_roles(
        self, source_connection_id: uuid.UUID, target_connection_id: uuid.UUID
    ) -> None:
        source = self.db.get(ConnectionConfig, source_connection_id)
        target = self.db.get(ConnectionConfig, target_connection_id)
        if source is None:
            raise MappingValidationError(
                f"source_connection_id {source_connection_id} does not exist"
            )
        if target is None:
            raise MappingValidationError(
                f"target_connection_id {target_connection_id} does not exist"
            )
        if source.role not in ("source", "either"):
            raise MappingValidationError(f"connection '{source.name}' cannot be used as a source")
        if target.role not in ("target", "either"):
            raise MappingValidationError(f"connection '{target.name}' cannot be used as a target")

    def _validate_column_links(self, column_links: list[dict]) -> None:
        for link in column_links:
            if not link.get("sourceColumn") or not link.get("targetColumn"):
                raise MappingValidationError(
                    f"column link {link} is missing a sourceColumn or targetColumn"
                )
            translation_version_id = link.get("enumTranslationVersionId")
            if translation_version_id is not None:
                version = self.db.get(EnumTranslationVersion, translation_version_id)
                if version is None:
                    raise MappingValidationError(
                        f"column link for '{link['sourceColumn']}' references enum "
                        f"translation version {translation_version_id}, which does not exist "
                        "(FR-005: a translation table must be attached before it can be used)"
                    )

    def _validate_retirement_config(self, retirement_config: dict | None) -> None:
        if retirement_config is None:
            raise MappingValidationError(
                "a 'retirement' mapping requires retirement_config (FR-009)"
            )
        required = (
            "status_column",
            "retired_value_codes",
            "reason_column",
            "audit_binding",
        )
        missing = [key for key in required if key not in retirement_config]
        if missing:
            raise MappingValidationError(f"retirement_config is missing required keys: {missing}")

        audit_binding = retirement_config["audit_binding"]
        required_binding_keys = (
            "audit_table",
            "row_identity_target_column",
            "reason_target_column",
            "timestamp_target_column",
        )
        missing_binding = [key for key in required_binding_keys if key not in audit_binding]
        if missing_binding:
            raise MappingValidationError(
                f"retirement_config.audit_binding is missing required keys: {missing_binding}"
            )

        reason_translation_version_id = retirement_config.get("reason_translation_version_id")
        if reason_translation_version_id is not None:
            version = self.db.get(EnumTranslationVersion, reason_translation_version_id)
            if version is None:
                raise MappingValidationError(
                    f"retirement_config references enum translation version "
                    f"{reason_translation_version_id}, which does not exist"
                )

    def create_mapping(
        self,
        *,
        name: str,
        kind: str,
        source_connection_id: uuid.UUID,
        source_table: str,
        target_connection_id: uuid.UUID,
        target_table: str,
        column_links: list[dict],
        row_identity_column: str,
        retirement_config: dict | None = None,
    ) -> MappingDefinition:
        if kind not in MAPPING_KINDS:
            raise MappingValidationError(f"kind must be one of {MAPPING_KINDS}")
        self._validate_connection_roles(source_connection_id, target_connection_id)
        self._validate_column_links(column_links)
        if kind == "retirement":
            self._validate_retirement_config(retirement_config)

        definition = MappingDefinition(
            id=uuid.uuid4(),
            name=name,
            kind=kind,
            source_connection_id=source_connection_id,
            source_table=source_table,
            target_connection_id=target_connection_id,
            target_table=target_table,
        )
        self.db.add(definition)
        self.db.flush()

        version = MappingVersion(
            id=uuid.uuid4(),
            mapping_definition_id=definition.id,
            version_number=1,
            column_links=column_links,
            retirement_config=retirement_config,
            row_identity_column=row_identity_column,
        )
        self.db.add(version)
        self.db.flush()

        definition.current_version_id = version.id
        self.db.commit()
        self.db.refresh(definition)
        logger.info("mapping_created mapping_id=%s name=%s kind=%s", definition.id, name, kind)
        return definition

    def save_new_version(
        self,
        *,
        mapping_definition_id: uuid.UUID,
        column_links: list[dict],
        row_identity_column: str | None = None,
        retirement_config: dict | None = None,
    ) -> MappingVersion:
        definition = self.db.get(MappingDefinition, mapping_definition_id)
        if definition is None:
            raise MappingValidationError(f"no mapping definition {mapping_definition_id}")

        self._validate_column_links(column_links)
        if definition.kind == "retirement":
            previous_for_defaults = (
                self.db.get(MappingVersion, definition.current_version_id)
                if definition.current_version_id
                else None
            )
            effective_retirement_config = (
                retirement_config
                if retirement_config is not None
                else (previous_for_defaults.retirement_config if previous_for_defaults else None)
            )
            self._validate_retirement_config(effective_retirement_config)

        next_version_number = (
            self.db.query(func.max(MappingVersion.version_number))
            .filter(MappingVersion.mapping_definition_id == mapping_definition_id)
            .scalar()
            or 0
        ) + 1

        previous = (
            self.db.get(MappingVersion, definition.current_version_id)
            if definition.current_version_id
            else None
        )

        version = MappingVersion(
            id=uuid.uuid4(),
            mapping_definition_id=mapping_definition_id,
            version_number=next_version_number,
            column_links=column_links,
            retirement_config=(
                retirement_config
                if retirement_config is not None
                else (previous.retirement_config if previous else None)
            ),
            row_identity_column=row_identity_column
            or (previous.row_identity_column if previous else ""),
        )
        self.db.add(version)
        self.db.flush()

        definition.current_version_id = version.id
        self.db.commit()
        self.db.refresh(version)
        logger.info(
            "mapping_version_saved mapping_id=%s version=%s",
            mapping_definition_id,
            next_version_number,
        )
        return version

    def list_versions(self, mapping_definition_id: uuid.UUID) -> list[MappingVersion]:
        return list(
            self.db.query(MappingVersion)
            .filter(MappingVersion.mapping_definition_id == mapping_definition_id)
            .order_by(MappingVersion.version_number)
            .all()
        )

    def get(self, mapping_definition_id: uuid.UUID) -> MappingDefinition | None:
        return self.db.get(MappingDefinition, mapping_definition_id)

    def list(self) -> list[MappingDefinition]:
        return list(self.db.query(MappingDefinition).order_by(MappingDefinition.name).all())
