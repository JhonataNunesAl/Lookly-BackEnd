from pydantic import BaseModel, Field


class PaginationQueryParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le= 100)
    