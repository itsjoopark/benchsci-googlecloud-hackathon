from pydantic import BaseModel


class ExtractedEntity(BaseModel):
    entity_name: str
    entity_type: str | None = None
    qualifiers: list[str] = []


class ExtractedEntityPair(BaseModel):
    entity1_name: str
    entity1_type: str | None = None
    entity2_name: str
    entity2_type: str | None = None
