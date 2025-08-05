import asyncio
import time
from typing import List, Dict, Optional, Tuple, Any
import logging
from collections import defaultdict

from .models import (
    HybridQuery, DiseaseCandidate, VariantAnnotation,
    UnifiedMatchResponse, UnifiedDiseaseMatch, UnifiedMetadata, UnifiedExtended,
    Conflict
)
from .gene_lookup import GeneToOmimLookup
from .variant_annotator import VariantAnnotator
from .search_engine_bm25 import BM25SearchEngine
from .llm_query_generator import LLMQueryGenerator
from .text_preprocessor import TextPreprocessor
from .data_loader import DataLoader
from .llm_reranker import LLMReranker
from .config import Settings

logger = logging.getLogger(__name__)


class HybridOrchestrator:
    """Координатор гибридного поиска заболеваний"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai_model = settings.openai_model
        self.architecture = settings.architecture
        
        # Загрузка данных
        logger.info("Loading disease data...")
        self.data_loader = DataLoader(settings.datasets_dir)
        self.diseases = self.data_loader.load_all()
        
        # Инициализация компонентов
        self.text_preprocessor = TextPreprocessor()
        self.gene_lookup = GeneToOmimLookup(settings.genemap_path)
        self.variant_annotator = VariantAnnotator(settings.ensembl_release)
        
        # Инициализация BM25 поиска
        logger.info("Building BM25 search index...")
        self.bm25_engine = BM25SearchEngine(self.text_preprocessor, self.data_loader)
        self.bm25_engine.build_index(self.diseases)
        
        # LLM компоненты
        self.llm_query_generator = LLMQueryGenerator(settings)
        self.llm_reranker = LLMReranker(settings, self.data_loader)
        
        # Веса для комбинирования методов
        self.gene_weight = settings.gene_weight
        self.bm25_weight = settings.bm25_weight
        self.conflict_penalty = settings.conflict_penalty
        
    async def search(self, query: HybridQuery) -> UnifiedMatchResponse:
        """Главный метод поиска"""
        start_time = time.time()
        
        # Проверка на отсутствие диагноза
        if not query.text or query.text.strip() in ["-", ""]:
            return UnifiedMatchResponse(
                results=[UnifiedDiseaseMatch(
                    rank=1,
                    omim_id=None,
                    mondo_id=None,
                    name="Диагноз не установлен",
                    score=0.0,
                    genes=[]
                )],
                metadata=UnifiedMetadata(
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    architecture=self.architecture,
                    model=self.openai_model,
                    total_results=1
                ),
                extended={
                    "no_diagnosis": True,
                    "message": "No diagnosis provided in the query"
                }
            )
        
        try:
            # 1. Аннотация варианта если есть
            variant_annotation = None
            variant_gene = None
            
            if query.variant_coordinates:
                variant_info = self.variant_annotator.parse_variant(query.variant_coordinates)
                if variant_info:
                    variant_annotation = self.variant_annotator.annotate_variant(variant_info)
                    if variant_annotation.genes:
                        variant_gene = variant_annotation.genes[0]
                        logger.info(f"Variant annotated: {variant_annotation.genes} in {variant_annotation.region_type}")
                        
            # 2. Определение рабочего гена
            working_gene = query.gene or variant_gene
            
            # 3. Параллельный запуск методов поиска
            search_tasks = []
            
            # Традиционный поиск по гену
            if working_gene:
                search_tasks.append(("gene_lookup", self._search_by_gene(working_gene)))
                
            # BM25 поиск по тексту
            search_tasks.append(("bm25", self._search_by_text(query.text, working_gene, query.language)))
            
            # Выполняем поиски параллельно
            search_results = {}
            if search_tasks:
                results = await asyncio.gather(*[task[1] for task in search_tasks])
                for (method_name, _), result in zip(search_tasks, results):
                    search_results[method_name] = result
                    
            # 4. Объединение результатов
            merged_candidates = self.merge_candidates(search_results)
            
            if not merged_candidates:
                # Нет результатов
                return self._create_empty_response(time.time() - start_time)
                
            # 5. LLM переранжирование если есть кандидаты
            reranking_result = await self.llm_reranker.rerank_candidates(
                candidates=merged_candidates[:20],  # Топ-20 для LLM
                query=query.text,
                gene=working_gene,
                variant_annotation=variant_annotation,
                language=query.language,
                full_context=query.full_context
            )
            
            # 6. Применение конфликтов и финальное ранжирование
            final_candidates = self._apply_conflicts(
                reranking_result.ranked_candidates,
                reranking_result.conflicts_detected
            )
            
            # 7. Формирование ответа
            processing_time = time.time() - start_time
            
            return self._create_response(
                candidates=final_candidates[:query.top_k],
                processing_time=processing_time,
                search_results=search_results,
                variant_annotation=variant_annotation,
                llm_reasoning=reranking_result.reasoning,
                conflicts=reranking_result.conflicts_detected
            )
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}", exc_info=True)
            processing_time = time.time() - start_time
            return self._create_error_response(str(e), processing_time)
            
    async def _search_by_gene(self, gene: str) -> List[DiseaseCandidate]:
        """Традиционный поиск по гену используя gene_lookup и data_loader"""
        logger.info(f"Searching by gene: {gene}")
        
        candidates = []
        seen_diseases = set()
        
        # 1. Сначала используем традиционный gene_lookup
        omim_diseases = self.gene_lookup.search_by_gene(gene)
        
        for disease in omim_diseases:
            # Получаем MONDO ID если есть маппинг
            mondo_id = None
            omim_full_id = f"OMIM:{disease.omim_id}"
            if omim_full_id in self.data_loader.omim_to_mondo:
                mondo_id = self.data_loader.omim_to_mondo[omim_full_id]
            
            candidate = DiseaseCandidate(
                omim_id=disease.omim_id,
                mondo_id=mondo_id,
                name=disease.name,
                genes=disease.genes,
                score=0.95,  # Высокая уверенность для прямого соответствия
                source="gene_lookup",
                match_details={
                    "method": "direct_gene_match",
                    "gene_query": gene
                }
            )
            candidates.append(candidate)
            seen_diseases.add(omim_full_id)
        
        # 2. Дополняем результатами из data_loader.gene_to_diseases
        gene_upper = gene.upper()
        if gene_upper in self.data_loader.gene_to_diseases:
            for disease_id in self.data_loader.gene_to_diseases[gene_upper]:
                if disease_id not in seen_diseases and disease_id in self.data_loader.diseases:
                    disease = self.data_loader.diseases[disease_id]
                    
                    # Определяем ID в зависимости от источника
                    omim_id = disease.id.replace("OMIM:", "") if disease.source == "OMIM" else None
                    mondo_id = disease.id if disease.source == "MONDO" else None
                    
                    # Обогащаем кросс-ссылками
                    if omim_id and not mondo_id and disease.id in self.data_loader.omim_to_mondo:
                        mondo_id = self.data_loader.omim_to_mondo[disease.id]
                    elif mondo_id and not omim_id and mondo_id in self.data_loader.mondo_to_omim:
                        omim_id = self.data_loader.mondo_to_omim[mondo_id].replace("OMIM:", "")
                    
                    candidate = DiseaseCandidate(
                        omim_id=omim_id,
                        mondo_id=mondo_id,
                        name=disease.name,
                        genes=disease.genes,
                        score=0.90,  # Немного ниже уверенность чем у gene_lookup
                        source="gene_to_diseases",
                        match_details={
                            "method": "gene_to_diseases_mapping",
                            "gene_query": gene
                        }
                    )
                    candidates.append(candidate)
                    seen_diseases.add(disease.id)
            
        logger.info(f"Gene lookup found {len(candidates)} candidates")
        return candidates
        
    async def _search_by_text(self, text: str, gene: Optional[str], language: str) -> List[DiseaseCandidate]:
        """Поиск через BM25 с генерацией запросов через LLM"""
        logger.info(f"Searching by text: '{text[:50]}...' (lang={language})")
        
        # Генерируем поисковые запросы
        if language == 'ru':
            # Для русского текста генерируем английские запросы через LLM
            context = f"Gene: {gene}" if gene else None
            queries = await self.llm_query_generator.generate_queries(text, context)
            logger.info(f"Generated {len(queries)} search queries: {queries}")
        else:
            # Для английского используем оригинальный текст
            queries = [text]
            
        # Выполняем BM25 поиск
        if gene:
            candidates = self.bm25_engine.search_with_gene_boost(
                queries=queries,
                gene=gene,
                top_k=20,
                gene_boost_factor=self.settings.bm25_gene_boost
            )
        else:
            candidates = self.bm25_engine.search(
                queries=queries,
                top_k=20
            )
            
        logger.info(f"BM25 search found {len(candidates)} candidates")
        return candidates
        
    def merge_candidates(self, search_results: Dict[str, List[DiseaseCandidate]]) -> List[DiseaseCandidate]:
        """Объединение результатов из разных источников"""
        # Группируем по ID заболевания
        disease_scores = defaultdict(list)
        disease_info = {}
        
        for method, candidates in search_results.items():
            method_weight = self.gene_weight if method == "gene_lookup" else self.bm25_weight
            
            for candidate in candidates:
                # Создаем уникальный ключ для заболевания
                disease_key = self._get_disease_key(candidate)
                
                # Сохраняем взвешенный score
                weighted_score = candidate.score * method_weight
                disease_scores[disease_key].append({
                    "method": method,
                    "score": candidate.score,
                    "weighted_score": weighted_score
                })
                
                # Сохраняем информацию о заболевании
                if disease_key not in disease_info:
                    disease_info[disease_key] = candidate
                else:
                    # Объединяем информацию
                    existing = disease_info[disease_key]
                    if not existing.omim_id and candidate.omim_id:
                        existing.omim_id = candidate.omim_id
                    if not existing.mondo_id and candidate.mondo_id:
                        existing.mondo_id = candidate.mondo_id
                    # Объединяем гены
                    existing.genes = list(set(existing.genes + candidate.genes))
                    
        # Вычисляем финальные scores
        merged_candidates = []
        
        for disease_key, scores in disease_scores.items():
            # Суммируем взвешенные scores
            total_weighted_score = sum(s["weighted_score"] for s in scores)
            
            # Бонус за присутствие в нескольких методах
            method_count = len(set(s["method"] for s in scores))
            if method_count > 1:
                total_weighted_score *= (1 + 0.1 * (method_count - 1))
                
            # Нормализуем score
            final_score = min(total_weighted_score, 1.0)
            
            # Создаем финального кандидата
            candidate = disease_info[disease_key]
            merged_candidate = DiseaseCandidate(
                omim_id=candidate.omim_id,
                mondo_id=candidate.mondo_id,
                name=candidate.name,
                genes=candidate.genes,
                score=final_score,
                source="combined",
                match_details={
                    "methods": [s["method"] for s in scores],
                    "method_scores": {s["method"]: s["score"] for s in scores},
                    "final_score": final_score
                }
            )
            merged_candidates.append(merged_candidate)
            
        # Сортируем по score
        merged_candidates.sort(key=lambda c: c.score, reverse=True)
        
        logger.info(f"Merged {len(merged_candidates)} unique candidates from {len(search_results)} methods")
        return merged_candidates
        
    def _get_disease_key(self, candidate: DiseaseCandidate) -> str:
        """Создать уникальный ключ для заболевания"""
        if candidate.omim_id:
            return f"OMIM:{candidate.omim_id}"
        elif candidate.mondo_id:
            return candidate.mondo_id
        else:
            # Используем название как fallback
            return f"NAME:{candidate.name.lower()}"
            
    def _apply_conflicts(
        self, 
        candidates: List[DiseaseCandidate], 
        conflicts: List[Conflict]
    ) -> List[DiseaseCandidate]:
        """Применить штрафы за конфликты"""
        if not conflicts:
            return candidates
            
        # Создаем словарь конфликтов по заболеваниям
        conflict_map = defaultdict(list)
        for conflict in conflicts:
            # Конфликты применяются ко всем кандидатам с проблемным геном
            for candidate in candidates:
                if conflict.found in candidate.genes:
                    conflict_map[self._get_disease_key(candidate)].append(conflict)
                    
        # Применяем штрафы
        adjusted_candidates = []
        for candidate in candidates:
            disease_key = self._get_disease_key(candidate)
            
            if disease_key in conflict_map:
                # Вычисляем общий штраф
                max_severity = max(c.severity for c in conflict_map[disease_key])
                penalty = self.settings.conflict_penalty * max_severity
                
                # Применяем штраф
                adjusted_score = candidate.score * (1 - penalty)
                
                adjusted_candidate = DiseaseCandidate(
                    omim_id=candidate.omim_id,
                    mondo_id=candidate.mondo_id,
                    name=candidate.name,
                    genes=candidate.genes,
                    score=adjusted_score,
                    source=candidate.source,
                    match_details={
                        **candidate.match_details,
                        "conflict_penalty": penalty,
                        "conflicts": len(conflict_map[disease_key])
                    }
                )
                adjusted_candidates.append(adjusted_candidate)
            else:
                adjusted_candidates.append(candidate)
                
        # Пересортировка после применения штрафов
        adjusted_candidates.sort(key=lambda c: c.score, reverse=True)
        
        return adjusted_candidates
        
    def _create_response(
        self,
        candidates: List[DiseaseCandidate],
        processing_time: float,
        search_results: Dict[str, List[DiseaseCandidate]],
        variant_annotation: Optional[VariantAnnotation],
        llm_reasoning: str,
        conflicts: List[Conflict]
    ) -> UnifiedMatchResponse:
        """Создать унифицированный ответ"""
        
        # Конвертируем кандидатов в унифицированный формат
        results = []
        for idx, candidate in enumerate(candidates):
            # Обогащаем кросс-ссылками если их нет
            omim_id = candidate.omim_id
            mondo_id = candidate.mondo_id
            
            # Если есть OMIM но нет MONDO - пытаемся найти
            if omim_id and not mondo_id:
                omim_full_id = f"OMIM:{omim_id}"
                if omim_full_id in self.data_loader.omim_to_mondo:
                    mondo_id = self.data_loader.omim_to_mondo[omim_full_id]
            
            # Если есть MONDO но нет OMIM - пытаемся найти
            elif mondo_id and not omim_id:
                if mondo_id in self.data_loader.mondo_to_omim:
                    omim_id = self.data_loader.mondo_to_omim[mondo_id].replace("OMIM:", "")
            
            # Извлекаем флаги из match_details для первого результата
            requires_clarification = False
            clarification_reason = None
            if idx == 0 and candidate.match_details:
                requires_clarification = candidate.match_details.get('requires_clarification', False)
                clarification_reason = candidate.match_details.get('clarification_reason')
            
            result = UnifiedDiseaseMatch(
                rank=idx + 1,
                omim_id=omim_id,
                mondo_id=mondo_id,
                name=candidate.name,
                score=candidate.score,
                genes=candidate.genes[:10],  # Ограничиваем количество генов
                requires_clarification=requires_clarification,
                clarification_reason=clarification_reason
            )
            results.append(result)
            
        # Метаданные
        metadata = UnifiedMetadata(
            processing_time_ms=int(processing_time * 1000),
            architecture=self.architecture,
            model=self.openai_model,
            total_results=len(results)
        )
        
        # Расширенная информация
        extended = UnifiedExtended(
            methods_used=list(search_results.keys()) + ["llm_rerank"],
            variant_annotation=variant_annotation.dict() if variant_annotation else None,
            llm_reasoning=llm_reasoning,
            conflicts=[{
                "type": c.type.value,
                "severity": c.severity,
                "message": c.message,
                "resolution_hint": c.resolution_hint
            } for c in conflicts],
            search_details={
                "gene_lookup_hits": len(search_results.get("gene_lookup", [])),
                "bm25_hits": len(search_results.get("bm25", [])),
                "merged_candidates": len(candidates) if candidates else 0
            }
        )
        
        return UnifiedMatchResponse(
            results=results,
            metadata=metadata,
            extended=extended,
            error=None
        )
        
    def _create_empty_response(self, processing_time: float) -> UnifiedMatchResponse:
        """Создать пустой ответ"""
        metadata = UnifiedMetadata(
            processing_time_ms=int(processing_time * 1000),
            architecture=self.architecture,
            model=self.openai_model,
            total_results=0
        )
        
        return UnifiedMatchResponse(
            results=[],
            metadata=metadata,
            extended=UnifiedExtended(
                methods_used=[],
                conflicts=[],
                search_details={"message": "No matches found"}
            ),
            error=None
        )
        
    def _create_error_response(self, error_message: str, processing_time: float) -> UnifiedMatchResponse:
        """Создать ответ с ошибкой"""
        metadata = UnifiedMetadata(
            processing_time_ms=int(processing_time * 1000),
            architecture=self.architecture,
            model=self.openai_model,
            total_results=0
        )
        
        return UnifiedMatchResponse(
            results=[],
            metadata=metadata,
            extended=None,
            error={
                "code": "SEARCH_ERROR",
                "message": error_message
            }
        )