from fastapi import APIRouter, Query, HTTPException

from schemas.search_schemas import SearchRequest, SearchResponse
from services.search_service import search_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=SearchResponse)
def search_products(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    search_service.ensure_index()
    result = search_service.search(query=q, limit=limit, offset=offset)
    return SearchResponse(query=q, total=result["total"], results=result["results"])
