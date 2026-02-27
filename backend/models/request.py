from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class ExpandRequest(BaseModel):
    entity_id: str = Field(..., min_length=1, max_length=200)
