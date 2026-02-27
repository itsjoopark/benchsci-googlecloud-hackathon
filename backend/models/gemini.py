from pydantic import BaseModel


class ExtractedEntity(BaseModel):
    entity_name: str
    entity_type: str | None = None
    qualifiers: list[str] = []
