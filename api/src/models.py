from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# Request models
class HybridQuery(BaseModel):
    """Запрос для гибридного поиска"""
    text: str = Field(..., description="Текст диагноза или симптомов")
    gene: Optional[str] = Field(None, description="Символ гена")
    variant_coordinates: Optional[str] = Field(None, description="Координаты варианта (например, chrX:154250998-C>T)")
    language: str = Field("ru", description="Язык запроса (ru/en)")
    top_k: int = Field(10, ge=1, le=50, description="Количество результатов")
    full_context: Optional[str] = Field(None, description="Полный контекст из исходной строки данных")


# Response models (unified format)
class UnifiedDiseaseMatch(BaseModel):
    """Единый формат результата"""
    rank: int = Field(..., description="Позиция в результатах")
    omim_id: Optional[str] = Field(None, description="OMIM идентификатор")
    mondo_id: Optional[str] = Field(None, description="MONDO идентификатор")
    name: str = Field(..., description="Название заболевания")
    score: float = Field(..., ge=0.0, le=1.0, description="Оценка уверенности")
    genes: List[str] = Field(default_factory=list, description="Связанные гены")
    requires_clarification: bool = Field(False, description="Требуется клиническое уточнение")
    clarification_reason: Optional[str] = Field(None, description="Причина необходимости уточнения")


class UnifiedMetadata(BaseModel):
    """Метаданные ответа"""
    processing_time_ms: int = Field(..., description="Время обработки в миллисекундах")
    architecture: str = Field("hybrid", description="Архитектура системы")
    model: str = Field(..., description="Используемая модель")
    total_results: int = Field(..., description="Количество результатов")


class UnifiedExtended(BaseModel):
    """Расширенная информация"""
    methods_used: List[str] = Field(..., description="Использованные методы поиска")
    variant_annotation: Optional[Dict[str, Any]] = Field(None, description="Аннотация варианта")
    llm_reasoning: Optional[str] = Field(None, description="Объяснение от LLM")
    conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="Обнаруженные конфликты")
    search_details: Optional[Dict[str, Any]] = Field(None, description="Детали поиска")


class UnifiedMatchResponse(BaseModel):
    """Унифицированный формат ответа"""
    results: List[UnifiedDiseaseMatch] = Field(..., description="Результаты поиска")
    metadata: UnifiedMetadata = Field(..., description="Метаданные")
    extended: Optional[UnifiedExtended] = Field(None, description="Расширенная информация")
    error: Optional[Dict[str, str]] = Field(None, description="Информация об ошибке")


# Internal models
class Disease(BaseModel):
    """Универсальное представление заболевания"""
    id: str  # OMIM:123456 или MONDO:0000001
    name: str
    alternative_names: List[str] = Field(default_factory=list)
    genes: List[str] = Field(default_factory=list)
    source: str  # "OMIM" или "MONDO"
    # Дополнительные поля для MONDO
    exact_synonyms: List[str] = Field(default_factory=list)
    related_synonyms: List[str] = Field(default_factory=list)
    subsets: List[str] = Field(default_factory=list)  # rare, ordo_disease и т.д.
    cross_references: Dict[str, str] = Field(default_factory=dict)  # OMIM -> MONDO и наоборот


class OmimDisease(BaseModel):
    """Заболевание из OMIM"""
    omim_id: str
    name: str
    genes: List[str] = Field(default_factory=list)
    phenotypes: List[str] = Field(default_factory=list)


class VariantInfo(BaseModel):
    """Информация о варианте"""
    chromosome: str
    position: int
    reference: str
    alternative: str
    
    def to_string(self) -> str:
        return f"{self.chromosome}:{self.position}:{self.reference}>{self.alternative}"


class RegionType(str, Enum):
    """Тип геномного региона"""
    EXONIC = "exonic"
    INTRONIC = "intronic"
    PROMOTER = "promoter"
    UTR = "utr"
    INTERGENIC = "intergenic"
    UNKNOWN = "unknown"


class VariantAnnotation(BaseModel):
    """Аннотация варианта"""
    variant: VariantInfo
    genes: List[str] = Field(default_factory=list)
    region_type: RegionType = RegionType.UNKNOWN
    distance_to_gene: Optional[int] = None
    functional_impact: Optional[str] = None


class DiseaseCandidate(BaseModel):
    """Кандидат заболевания для ранжирования"""
    omim_id: Optional[str] = None
    mondo_id: Optional[str] = None
    name: str
    genes: List[str] = Field(default_factory=list)
    score: float
    source: str  # "gene_lookup", "bm25", "combined"
    match_details: Dict[str, Any] = Field(default_factory=dict)


class ConflictType(str, Enum):
    """Тип конфликта"""
    GENE_DISEASE_MISMATCH = "gene_disease_mismatch"
    VARIANT_GENE_MISMATCH = "variant_gene_mismatch"
    REGION_TYPE_CONFLICT = "region_type_conflict"


class Conflict(BaseModel):
    """Информация о конфликте"""
    type: ConflictType
    severity: float = Field(ge=0.0, le=1.0)
    message: str
    expected: List[str] = Field(default_factory=list)
    found: str
    resolution_hint: Optional[str] = None


class RerankingResult(BaseModel):
    """Результат LLM переранжирования"""
    ranked_candidates: List[DiseaseCandidate]
    reasoning: str
    conflicts_detected: List[Conflict] = Field(default_factory=list)
    confidence_adjustment: Dict[str, float] = Field(default_factory=dict)


# Health check
class HealthResponse(BaseModel):
    """Статус сервиса"""
    status: str = "healthy"
    version: str = "1.0.0"
    components: Dict[str, bool] = Field(default_factory=dict)
    baseline_api_status: Optional[str] = None
    llm_api_status: Optional[str] = None