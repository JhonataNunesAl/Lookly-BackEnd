from schemas.pagination import PaginationQueryParams
from fastapi import Query


def get_pagination(skip:int = Query(default=0, ge=0),
                   limit:int = Query(default=20, ge=1, le=100)):
    return PaginationQueryParams(skip= skip, limit= limit)

