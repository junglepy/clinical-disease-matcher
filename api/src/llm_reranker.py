import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import asyncio

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI

from .models import (
    DiseaseCandidate, RerankingResult, Conflict, ConflictType,
    VariantAnnotation
)
from .config import Settings
from .data_loader import DataLoader

logger = logging.getLogger(__name__)


class LLMReranker:
    """LLM-based переранжирование и валидация кандидатов заболеваний"""
    
    def __init__(self, settings: Settings, data_loader: DataLoader):
        self.settings = settings
        self.data_loader = data_loader
        # Поддержка custom base_url для OpenRouter/Ollama
        client_params = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_params["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**client_params)
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_tokens = settings.openai_max_tokens
        
        # Загружаем промпт
        prompt_path = Path(__file__).parent.parent / "prompts" / "reranking_prompt.txt"
        if prompt_path.exists():
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = self._get_default_system_prompt()
            
    def _get_default_system_prompt(self) -> str:
        """Промпт по умолчанию для переранжирования"""
        return """You are a medical genetics expert helping to match disease descriptions to OMIM/MONDO codes.
You will receive a list of candidate diseases found by different search methods, along with the original query and genetic information.

Your task is to:
1. Analyze all candidates and select the best match
2. Detect any conflicts between the provided gene and candidate diseases
3. Provide clear reasoning for your choice
4. Adjust confidence scores based on the quality of match

CRITICAL RULES:
- If the disease name matches the query exactly or is a very close match, prioritize it highly
- Do NOT penalize diseases where the query gene is present in their gene list, even if it's not the "primary" or most common gene
- Many genes can be associated with multiple diseases, and many diseases have multiple associated genes
- A gene being present in the disease's gene list is a positive signal, regardless of whether it's the main causative gene

Consider these factors (in order of importance):
1. Exact match or close match of disease name to query
2. Presence of the query gene in the disease's gene list (if gene provided)
3. Clinical presentation match based on synonyms and alternative names
4. Disease categories (rare, genetic, etc.)
5. Cross-references between OMIM and MONDO databases

Additional considerations:
- Exact and related synonyms (pay special attention to exact synonyms)
- Alternative disease names in different languages
- Age of onset if mentioned
- Inheritance pattern
- Variant location (exonic, intronic, promoter)

You must respond with valid JSON following this structure:
{
  "best_match_id": "OMIM:123456",
  "reasoning": "Clear explanation of why this is the best match",
  "ranked_candidates": [
    {
      "id": "OMIM:123456",
      "adjusted_score": 0.95,
      "adjustment_reason": "Perfect gene match and clinical presentation"
    }
  ],
  "conflicts": [
    {
      "type": "gene_disease_mismatch",
      "severity": 0.8,
      "message": "Gene X is not typically associated with disease Y",
      "expected_genes": ["GENE1", "GENE2"],
      "found_gene": "GENEX"
    }
  ]
}"""
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def rerank_candidates(
        self,
        candidates: List[DiseaseCandidate],
        query: str,
        gene: Optional[str] = None,
        variant_annotation: Optional[VariantAnnotation] = None,
        language: str = "ru",
        full_context: Optional[str] = None
    ) -> RerankingResult:
        """Переранжировать кандидатов с помощью LLM"""
        
        if not candidates:
            return RerankingResult(
                ranked_candidates=[],
                reasoning="No candidates to rerank",
                conflicts_detected=[]
            )
            
        try:
            # Формируем промпт для LLM
            user_prompt = self._format_user_prompt(
                candidates, query, gene, variant_annotation, language, full_context
            )
            
            # Запрос к OpenAI
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            # Парсим ответ
            content = response.choices[0].message.content
            logger.debug(f"LLM response: {content}")
            
            result = self._parse_llm_response(content, candidates)
            return result
            
        except Exception as e:
            logger.error(f"Error in LLM reranking: {e}")
            # Возвращаем исходный порядок при ошибке
            return RerankingResult(
                ranked_candidates=candidates,
                reasoning=f"LLM reranking failed: {str(e)}",
                conflicts_detected=[]
            )
            
    def _format_user_prompt(
        self,
        candidates: List[DiseaseCandidate],
        query: str,
        gene: Optional[str],
        variant_annotation: Optional[VariantAnnotation],
        language: str,
        full_context: Optional[str]
    ) -> str:
        """Форматирование промпта для LLM"""
        
        # Основная информация о запросе с UPPERCASE дублированием
        prompt_parts = [
            f'Query: "{query}" / "{query.upper()}" (uppercase duplicate for better tokenization)',
            f"Language: {language}"
        ]
        
        if gene:
            prompt_parts.append(f"Gene: {gene}")
            
        if variant_annotation:
            prompt_parts.append(f"Variant: {variant_annotation.variant.to_string()}")
            prompt_parts.append(f"Region type: {variant_annotation.region_type}")
            if variant_annotation.genes:
                prompt_parts.append(f"Genes at variant location: {', '.join(variant_annotation.genes)}")
            if variant_annotation.distance_to_gene is not None:
                prompt_parts.append(f"Distance to nearest gene: {variant_annotation.distance_to_gene}bp")
        
        # Добавляем полный контекст если он есть
        if full_context:
            prompt_parts.append(f"\nFull clinical context from source data:")
            prompt_parts.append(full_context)
            prompt_parts.append("\nPay special attention to:")
            prompt_parts.append("- Pathogenicity status (benign/pathogenic/VUS)")
            prompt_parts.append("- Variant type and coordinates")
            prompt_parts.append("- Any clinical notes or additional information")
                
        prompt_parts.append("\nCandidate diseases found:")
        
        # Форматируем кандидатов
        for i, candidate in enumerate(candidates[:10], 1):  # Топ-10 кандидатов для реранкера
            candidate_info = [
                f"\n{i}. {candidate.name.upper()}"  # Uppercase для основного названия
            ]
            
            if candidate.omim_id:
                candidate_info.append(f"   OMIM: {candidate.omim_id}")
            if candidate.mondo_id:
                candidate_info.append(f"   MONDO: {candidate.mondo_id}")
                
            # Добавляем Primary name для ясности
            candidate_info.append(f"   Primary name: {candidate.name}")
                
            # Убираем Score и Source - они могут смещать решение LLM
            
            if candidate.genes:
                candidate_info.append(f"   Associated genes: {', '.join(candidate.genes[:10])}")
                
            # Добавляем синонимы из базы данных
            disease_id = None
            if candidate.omim_id:
                disease_id = f"OMIM:{candidate.omim_id}"
            elif candidate.mondo_id:
                disease_id = candidate.mondo_id
                
            if disease_id and disease_id in self.data_loader.diseases:
                disease = self.data_loader.diseases[disease_id]
                
                # Добавляем exact синонимы
                if hasattr(disease, 'exact_synonyms') and disease.exact_synonyms:
                    candidate_info.append(f"   Exact synonyms: {', '.join(disease.exact_synonyms[:3])}")
                    
                # Добавляем related синонимы
                if hasattr(disease, 'related_synonyms') and disease.related_synonyms:
                    candidate_info.append(f"   Related synonyms: {', '.join(disease.related_synonyms[:3])}")
                    
                # Добавляем альтернативные названия
                if disease.alternative_names and len(disease.alternative_names) > 0:
                    candidate_info.append(f"   Alternative names: {', '.join(disease.alternative_names[:3])}")
                    
                # Добавляем subsets (rare, ordo_disease и т.д.)
                if hasattr(disease, 'subsets') and disease.subsets:
                    candidate_info.append(f"   Categories: {', '.join(disease.subsets)}")
                    
                # Добавляем кросс-ссылки
                if hasattr(disease, 'cross_references') and disease.cross_references:
                    xrefs = [f"{k}" for k, v in list(disease.cross_references.items())[:2]]
                    if xrefs:
                        candidate_info.append(f"   Cross-references: {', '.join(xrefs)}")
                
            # Проверка точного совпадения названия
            if self._is_exact_name_match(query, candidate):
                candidate_info.append("   ⚠️ EXACT NAME MATCH with query!")
                
            prompt_parts.extend(candidate_info)
            
        prompt_parts.append("\nPlease analyze these candidates and provide your assessment in the specified JSON format.")
        
        return "\n".join(prompt_parts)
        
    def _parse_llm_response(
        self, 
        content: str, 
        original_candidates: List[DiseaseCandidate]
    ) -> RerankingResult:
        """Парсинг ответа LLM с поддержкой новой и старой структуры"""
        try:
            data = json.loads(content)
            
            # Создаем словарь кандидатов для быстрого доступа
            candidates_dict = {}
            for candidate in original_candidates:
                if candidate.omim_id:
                    candidates_dict[f"OMIM:{candidate.omim_id}"] = candidate
                    candidates_dict[candidate.omim_id] = candidate  # Также без префикса
                if candidate.mondo_id:
                    candidates_dict[candidate.mondo_id] = candidate
                    
            # Определяем структуру ответа
            is_new_format = 'final_decision' in data and 'candidates_evaluation' in data
            
            # Извлекаем reasoning и best_match_id в зависимости от формата
            if is_new_format:
                # Новый формат с пошаговым анализом
                reasoning_parts = []
                
                if 'initial_analysis' in data:
                    reasoning_parts.append(f"Query analysis: {data['initial_analysis'].get('query_understanding', '')}")
                
                if 'critical_thinking' in data:
                    reasoning_parts.append(f"Critical thinking: {data['critical_thinking'].get('main_differentiator', '')}")
                    
                if 'final_decision' in data:
                    reasoning_parts.append(data['final_decision'].get('brief_justification', ''))
                    
                reasoning = " ".join(reasoning_parts)
                best_match_id = data.get('final_decision', {}).get('best_match_id')
                
                # Извлекаем флаг requires_clarification
                requires_clarification = data.get('final_decision', {}).get('requires_clarification', False)
                clarification_reason = data.get('final_decision', {}).get('clarification_reason')
            else:
                # Старый формат
                reasoning = data.get("reasoning", "")
                best_match_id = data.get("best_match_id")
                requires_clarification = False
                clarification_reason = None
                
            # Обрабатываем ранжированных кандидатов
            ranked_candidates = []
            confidence_adjustment = {}
            
            if is_new_format and 'candidates_evaluation' in data:
                # Новый формат: кандидаты отсортированы от худшего к лучшему
                candidates_eval = data['candidates_evaluation']
                # Сортируем по рангу (меньший ранг = лучше)
                sorted_candidates = sorted(candidates_eval, key=lambda x: x.get('rank', 999))
                
                for eval_item in sorted_candidates:
                    candidate_id = eval_item.get("id", "")
                    
                    # Находим оригинального кандидата
                    candidate = None
                    if candidate_id in candidates_dict:
                        candidate = candidates_dict[candidate_id]
                    else:
                        # Пробуем найти по частичному совпадению
                        for key, cand in candidates_dict.items():
                            if candidate_id in key or key in candidate_id:
                                candidate = cand
                                break
                    
                    if candidate:
                        # Вычисляем adjusted_score на основе ранга
                        rank = eval_item.get('rank', 10)
                        adjusted_score = max(0.1, 1.1 - (rank * 0.1))
                        
                        # Увеличиваем score для лучшего кандидата
                        if rank == 1 and candidate_id == best_match_id:
                            adjusted_score = max(adjusted_score, 0.95)
                            
                        reason = eval_item.get('selection_reason') or eval_item.get('elimination_reason', '')
                        
                        # Добавляем requires_clarification только для лучшего кандидата
                        match_details = {
                            **candidate.match_details,
                            "llm_adjusted": True,
                            "adjustment_reason": reason,
                            "llm_rank": rank
                        }
                        
                        # Если это лучший кандидат, добавляем флаг clarification
                        if candidate_id == best_match_id and requires_clarification:
                            match_details["requires_clarification"] = True
                            match_details["clarification_reason"] = clarification_reason
                        
                        adjusted_candidate = DiseaseCandidate(
                            omim_id=candidate.omim_id,
                            mondo_id=candidate.mondo_id,
                            name=candidate.name,
                            genes=candidate.genes,
                            score=adjusted_score,
                            source=candidate.source,
                            match_details=match_details
                        )
                        ranked_candidates.append(adjusted_candidate)
                        
                        # Сохраняем информацию об изменении score
                        if abs(adjusted_score - candidate.score) > 0.01:
                            confidence_adjustment[candidate_id] = adjusted_score - candidate.score
            else:
                # Старый формат: используем ranked_candidates
                for ranked_item in data.get("ranked_candidates", []):
                    candidate_id = ranked_item.get("id", "")
                    
                    # Находим оригинального кандидата
                    candidate = None
                    if candidate_id in candidates_dict:
                        candidate = candidates_dict[candidate_id]
                    else:
                        # Пробуем найти по частичному совпадению
                        for key, cand in candidates_dict.items():
                            if candidate_id in key or key in candidate_id:
                                candidate = cand
                                break
                                
                    if candidate:
                        # Обновляем score если указан
                        adjusted_score = ranked_item.get("adjusted_score", candidate.score)
                        adjusted_candidate = DiseaseCandidate(
                            omim_id=candidate.omim_id,
                            mondo_id=candidate.mondo_id,
                            name=candidate.name,
                            genes=candidate.genes,
                            score=adjusted_score,
                            source=candidate.source,
                            match_details={
                                **candidate.match_details,
                                "llm_adjusted": True,
                                "adjustment_reason": ranked_item.get("adjustment_reason", "")
                            }
                        )
                        ranked_candidates.append(adjusted_candidate)
                        
                        # Сохраняем информацию об изменении score
                        if abs(adjusted_score - candidate.score) > 0.01:
                            confidence_adjustment[candidate_id] = adjusted_score - candidate.score
                            
            # Если LLM не вернул всех кандидатов, добавляем остальные в конец
            ranked_ids = {self._get_candidate_id(c) for c in ranked_candidates}
            for candidate in original_candidates:
                if self._get_candidate_id(candidate) not in ranked_ids:
                    ranked_candidates.append(candidate)
                    
            # Обрабатываем конфликты
            conflicts = []
            for conflict_data in data.get("conflicts", []):
                conflict = Conflict(
                    type=ConflictType(conflict_data.get("type", "gene_disease_mismatch")),
                    severity=conflict_data.get("severity", 0.5),
                    message=conflict_data.get("message", ""),
                    expected=conflict_data.get("expected_genes", []),
                    found=conflict_data.get("found_gene", ""),
                    resolution_hint=conflict_data.get("resolution_hint")
                )
                conflicts.append(conflict)
                
            return RerankingResult(
                ranked_candidates=ranked_candidates,
                reasoning=reasoning,
                conflicts_detected=conflicts,
                confidence_adjustment=confidence_adjustment
            )
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            logger.error(f"Raw content: {content}")
            
            # Возвращаем исходный порядок при ошибке парсинга
            return RerankingResult(
                ranked_candidates=original_candidates,
                reasoning=f"Failed to parse LLM response: {str(e)}",
                conflicts_detected=[]
            )
            
    def _get_candidate_id(self, candidate: DiseaseCandidate) -> str:
        """Получить уникальный ID кандидата"""
        if candidate.omim_id:
            return f"OMIM:{candidate.omim_id}"
        elif candidate.mondo_id:
            return candidate.mondo_id
        else:
            return candidate.name
            
    def _is_exact_name_match(self, query: str, candidate: DiseaseCandidate) -> bool:
        """Проверка точного совпадения названия с улучшенной нормализацией"""
        # Более тщательная нормализация: lowercase, strip, убираем лишние пробелы
        query_normalized = ' '.join(query.lower().strip().split())
        
        # Проверяем основное название
        candidate_name_normalized = ' '.join(candidate.name.lower().strip().split())
        if candidate_name_normalized == query_normalized:
            return True
            
        # Проверяем альтернативные названия из кандидата
        if hasattr(candidate, 'alternative_names') and candidate.alternative_names:
            for alt_name in candidate.alternative_names:
                alt_name_normalized = ' '.join(alt_name.lower().strip().split())
                if alt_name_normalized == query_normalized:
                    return True
                    
        # Проверяем exact synonyms из data_loader
        disease_id = f"OMIM:{candidate.omim_id}" if candidate.omim_id else candidate.mondo_id
        if disease_id and disease_id in self.data_loader.diseases:
            disease = self.data_loader.diseases[disease_id]
            
            # Проверяем exact_synonyms
            if hasattr(disease, 'exact_synonyms') and disease.exact_synonyms:
                for synonym in disease.exact_synonyms:
                    synonym_normalized = ' '.join(synonym.lower().strip().split())
                    if synonym_normalized == query_normalized:
                        return True
                        
            # Также проверяем related_synonyms (может быть полезно)
            if hasattr(disease, 'related_synonyms') and disease.related_synonyms:
                for synonym in disease.related_synonyms:
                    synonym_normalized = ' '.join(synonym.lower().strip().split())
                    if synonym_normalized == query_normalized:
                        return True
                        
        return False