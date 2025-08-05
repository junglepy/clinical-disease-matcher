import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.models import HybridQuery, UnifiedMatchResponse, HealthResponse
from src.config import get_settings, DATA_DIR
from src.hybrid_orchestrator import HybridOrchestrator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные объекты
settings = None
orchestrator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global settings, orchestrator
    
    # Startup
    logger.info("Starting Hybrid Disease Matcher API...")
    
    try:
        # Загружаем настройки
        settings = get_settings()
        
        # Проверяем наличие genemap2.txt
        genemap_path = Path(settings.genemap_path)
        if not genemap_path.exists():
            # Пробуем symlink на baseline данные
            baseline_genemap = Path("../disease-matcher-baseline/data/OMIM/genemap2.txt")
            if baseline_genemap.exists():
                logger.info(f"Creating symlink to baseline genemap2.txt")
                DATA_DIR.mkdir(exist_ok=True, parents=True)
                genemap_path.symlink_to(baseline_genemap.absolute())
            else:
                logger.error(f"genemap2.txt not found at {genemap_path}")
                raise FileNotFoundError(f"genemap2.txt not found. Please copy it to {genemap_path}")
        
        # Инициализируем orchestrator
        orchestrator = HybridOrchestrator(settings)
        
        # BM25 индекс уже построен локально
        logger.info(f"BM25 index ready with {len(orchestrator.diseases)} diseases loaded")
        
        logger.info("Hybrid Disease Matcher API is ready!")
        
    except Exception as e:
        logger.error(f"Failed to start: {e}")
        raise
        
    yield
    
    # Shutdown
    logger.info("Shutting down Hybrid Disease Matcher API...")


# Создание FastAPI приложения
app = FastAPI(
    title="Hybrid Disease Matcher API",
    description="Гибридная система матчинга заболеваний с поддержкой генных координат и LLM",
    version="1.0.0",
    lifespan=lifespan
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=dict)
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Hybrid Disease Matcher API",
        "version": "1.0.0",
        "endpoints": {
            "match": "/api/v1/match",
            "health": "/api/v1/health"
        },
        "features": [
            "Gene-to-OMIM lookup",
            "Variant coordinate parsing with pyensembl",
            "BM25 text search integration",
            "LLM-based reranking and validation",
            "Conflict detection"
        ]
    }


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Проверка состояния сервиса"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    # Проверяем компоненты
    components = {
        "gene_lookup": bool(orchestrator.gene_lookup),
        "variant_annotator": bool(orchestrator.variant_annotator),
        "bm25_engine": bool(orchestrator.bm25_engine),
        "llm_reranker": bool(orchestrator.llm_reranker),
        "data_loader": bool(orchestrator.data_loader),
        "llm_query_generator": bool(orchestrator.llm_query_generator)
    }
    
    # Проверяем внешние сервисы
    baseline_status = f"local_index_loaded ({len(orchestrator.diseases)} diseases)"
    llm_status = "unknown"
        
    # LLM проверяем по наличию API ключа
    if settings and settings.openai_api_key:
        llm_status = "configured"
    else:
        llm_status = "not_configured"
    
    return HealthResponse(
        status="healthy" if all(components.values()) else "degraded",
        version="1.0.0",
        components=components,
        baseline_api_status=baseline_status,
        llm_api_status=llm_status
    )


@app.post("/api/v1/match", response_model=UnifiedMatchResponse)
async def match_disease(query: HybridQuery):
    """Гибридный поиск заболевания"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    logger.info(f"Processing query: text='{query.text[:50]}...', gene={query.gene}, variant={query.variant_coordinates}")
    
    try:
        # Выполняем поиск через orchestrator
        response = await orchestrator.search(query)
        
        # Логируем результаты
        if response.results:
            top_result = response.results[0]
            logger.info(
                f"Top match: {top_result.name} "
                f"(OMIM:{top_result.omim_id}, score:{top_result.score:.3f})"
            )
        else:
            logger.info("No matches found")
            
        return response
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        
        # Возвращаем ошибку в унифицированном формате
        from src.models import UnifiedMetadata, UnifiedExtended
        
        return UnifiedMatchResponse(
            results=[],
            metadata=UnifiedMetadata(
                processing_time_ms=0,
                architecture=settings.architecture if settings else "hybrid_bm25_llm",
                model=settings.openai_model if settings else "gpt-4-turbo-preview",
                total_results=0
            ),
            extended=None,
            error={
                "code": "PROCESSING_ERROR",
                "message": str(e)
            }
        )


if __name__ == "__main__":
    # Получаем настройки для определения порта
    settings = get_settings()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )