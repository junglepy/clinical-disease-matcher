import httpx
import asyncio
from typing import List, Optional, Dict, Any
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import DiseaseCandidate, UnifiedMatchResponse
from .config import Settings

logger = logging.getLogger(__name__)


class BM25Wrapper:
    """Обертка для вызова baseline BM25 API"""
    
    def __init__(self, baseline_url: str, timeout: int = 30):
        self.baseline_url = baseline_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
            
    async def _ensure_client(self):
        """Убедиться что клиент создан"""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def search(
        self, 
        query: str, 
        gene: Optional[str] = None,
        language: str = "ru", 
        top_k: int = 20
    ) -> List[DiseaseCandidate]:
        """Поиск заболеваний через baseline API"""
        await self._ensure_client()
        
        # Формируем запрос
        request_data = {
            "text": query,
            "language": language,
            "top_k": top_k
        }
        
        if gene:
            request_data["gene"] = gene
            
        try:
            # Делаем запрос к baseline API
            response = await self._client.post(
                f"{self.baseline_url}/api/v1/match",
                json=request_data
            )
            response.raise_for_status()
            
            # Парсим ответ
            data = response.json()
            
            # Обрабатываем унифицированный формат
            if isinstance(data, dict) and "results" in data:
                # Новый формат с results/metadata/extended
                return self._parse_unified_response(data)
            else:
                # Старый формат - массив результатов
                return self._parse_legacy_response(data)
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from baseline API: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Error calling baseline API: {e}")
            return []
            
    def _parse_unified_response(self, data: Dict[str, Any]) -> List[DiseaseCandidate]:
        """Парсинг унифицированного формата ответа"""
        candidates = []
        
        results = data.get("results", [])
        extended = data.get("extended", {})
        
        for result in results:
            # Создаем кандидата из унифицированного формата
            candidate = DiseaseCandidate(
                omim_id=result.get("omim_id"),
                mondo_id=result.get("mondo_id"),
                name=result.get("name", ""),
                genes=result.get("genes", []),
                score=result.get("score", 0.0),
                source="bm25",
                match_details={
                    "rank": result.get("rank", 0),
                    "search_method": extended.get("search_method", "bm25"),
                    "translation_used": extended.get("translation_used", False)
                }
            )
            candidates.append(candidate)
            
        return candidates
        
    def _parse_legacy_response(self, data: Any) -> List[DiseaseCandidate]:
        """Парсинг старого формата ответа (массив)"""
        candidates = []
        
        if isinstance(data, list):
            for idx, item in enumerate(data):
                candidate = DiseaseCandidate(
                    omim_id=item.get("omim_id"),
                    mondo_id=item.get("mondo_id"),
                    name=item.get("name", ""),
                    genes=item.get("genes", []),
                    score=item.get("confidence", item.get("score", 0.0)),
                    source="bm25",
                    match_details={
                        "rank": idx + 1,
                        "search_method": "bm25"
                    }
                )
                candidates.append(candidate)
                
        return candidates
        
    async def health_check(self) -> bool:
        """Проверка доступности baseline API"""
        await self._ensure_client()
        
        try:
            response = await self._client.get(f"{self.baseline_url}/api/v1/health")
            response.raise_for_status()
            data = response.json()
            return data.get("status") == "healthy"
        except Exception as e:
            logger.error(f"Baseline API health check failed: {e}")
            return False
            
    async def get_api_info(self) -> Optional[Dict[str, Any]]:
        """Получить информацию о baseline API"""
        await self._ensure_client()
        
        try:
            response = await self._client.get(f"{self.baseline_url}/api/v1/health")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None