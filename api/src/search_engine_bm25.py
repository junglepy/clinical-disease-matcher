import numpy as np
from typing import List, Tuple, Dict, Optional, Set
from rank_bm25 import BM25Okapi
import logging
from pathlib import Path
import pickle

from .models import DiseaseCandidate, Disease
from .text_preprocessor import TextPreprocessor

logger = logging.getLogger(__name__)


class BM25SearchEngine:
    """BM25-based поисковый движок для заболеваний"""
    
    def __init__(self, preprocessor: TextPreprocessor, data_loader=None):
        self.preprocessor = preprocessor
        self.data_loader = data_loader
        
        # Данные для поиска
        self.disease_ids: List[str] = []
        self.disease_texts: List[str] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25 = None
        
        # Кеш для быстрого доступа
        self.diseases_cache: Dict[str, Disease] = {}
        
        # Параметры BM25
        self.k1 = 1.5  # Параметр насыщения термина
        self.b = 0.75  # Параметр нормализации длины документа
        
    def build_index(self, diseases: Dict[str, Disease]):
        """Построить поисковый индекс из словаря заболеваний"""
        logger.info("Building BM25 search index...")
        
        if not diseases:
            raise ValueError("No disease data provided")
        
        # Сохраняем кеш заболеваний
        self.diseases_cache = diseases
        
        # Разделяем на ID и тексты
        self.disease_ids = []
        self.disease_texts = []
        self.tokenized_corpus = []
        
        for disease_id, disease in diseases.items():
            # Создаем расширенный текст для лучшего матчинга
            text_parts = [disease.name]
            
            # Добавляем альтернативные названия
            if disease.alternative_names:
                text_parts.extend(disease.alternative_names)
                
            # Добавляем синонимы если есть
            if hasattr(disease, 'synonyms') and disease.synonyms:
                text_parts.extend(disease.synonyms)
                
            # Добавляем exact синонимы если есть  
            if hasattr(disease, 'exact_synonyms') and disease.exact_synonyms:
                text_parts.extend(disease.exact_synonyms)
                
            # Добавляем related синонимы если есть
            if hasattr(disease, 'related_synonyms') and disease.related_synonyms:
                text_parts.extend(disease.related_synonyms)
            
            # Объединяем все тексты
            combined_text = " ".join(text_parts)
            
            # Очищаем и нормализуем текст
            clean_text = self.preprocessor.clean_disease_name(combined_text)
            processed_text = self.preprocessor.preprocess(clean_text, 'en')
            
            # Финальный текст для индексации
            final_text = f"{clean_text} {processed_text}"
            
            self.disease_ids.append(disease_id)
            self.disease_texts.append(final_text)
            
            # Токенизируем для BM25
            tokens = final_text.lower().split()
            self.tokenized_corpus.append(tokens)
            
        # Создаем BM25 индекс
        self.bm25 = BM25Okapi(self.tokenized_corpus, k1=self.k1, b=self.b)
        
        logger.info(f"BM25 index built with {len(self.disease_ids)} disease entries")
        
    def search(self, queries: List[str], top_k: int = 20) -> List[DiseaseCandidate]:
        """
        Поиск заболеваний по списку запросов
        
        Args:
            queries: Список поисковых запросов (уже на английском)
            top_k: Количество результатов
            
        Returns:
            Список кандидатов заболеваний
        """
        if not self.bm25:
            raise ValueError("Search index not built. Call build_index() first.")
            
        # Собираем все результаты со всех запросов
        all_scores: Dict[int, float] = {}
        
        for query in queries:
            # Обрабатываем запрос
            processed_query = self.preprocessor.preprocess(query, 'en')
            combined_query = f"{query} {processed_query}"
            
            # Токенизируем запрос для BM25
            query_tokens = combined_query.lower().split()
            
            # Получаем BM25 scores
            scores = self.bm25.get_scores(query_tokens)
            
            # Агрегируем scores (берем максимум для каждого документа)
            for idx, score in enumerate(scores):
                if score > 0:
                    if idx in all_scores:
                        all_scores[idx] = max(all_scores[idx], score)
                    else:
                        all_scores[idx] = score
                        
        # Сортируем по scores
        sorted_indices = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Формируем результаты
        results = []
        seen_diseases = set()  # Для дедупликации
        
        for idx, score in sorted_indices[:top_k]:
            disease_id = self.disease_ids[idx]
            
            # Пропускаем дубликаты
            if disease_id in seen_diseases:
                continue
                
            seen_diseases.add(disease_id)
            
            if disease_id in self.diseases_cache:
                disease = self.diseases_cache[disease_id]
                
                # Нормализуем score в диапазон [0, 1]
                confidence = min(score / 50.0, 1.0)  # Эмпирическая нормализация
                
                # Определяем основные ID
                omim_id = disease.id.split(':')[1] if disease.source == 'OMIM' and ':' in disease.id else None
                mondo_id = disease.id if disease.source == 'MONDO' else None
                
                # Обогащаем кросс-ссылками если есть data_loader
                if self.data_loader:
                    if omim_id and not mondo_id:
                        # Если есть OMIM но нет MONDO - ищем маппинг
                        omim_full_id = f"OMIM:{omim_id}"
                        if omim_full_id in self.data_loader.omim_to_mondo:
                            mondo_id = self.data_loader.omim_to_mondo[omim_full_id]
                    elif mondo_id and not omim_id:
                        # Если есть MONDO но нет OMIM - ищем обратный маппинг
                        if mondo_id in self.data_loader.mondo_to_omim:
                            omim_id = self.data_loader.mondo_to_omim[mondo_id].replace("OMIM:", "")
                
                # Создаем кандидата
                candidate = DiseaseCandidate(
                    omim_id=omim_id,
                    mondo_id=mondo_id,
                    name=disease.name,
                    genes=disease.genes,
                    score=confidence,
                    source="bm25",
                    match_details={
                        "bm25_score": float(score),
                        "matched_queries": queries
                    }
                )
                results.append(candidate)
                
        return results
    
    def search_with_gene_boost(self, queries: List[str], gene: Optional[str], 
                              top_k: int = 20, gene_boost_factor: float = 1.5) -> List[DiseaseCandidate]:
        """Поиск с учетом гена"""
        # Получаем базовые результаты
        base_results = self.search(queries, top_k * 2)  # Берем больше для фильтрации
        
        if not gene:
            return base_results[:top_k]
            
        # Нормализуем символ гена
        gene_normalized = self.preprocessor.normalize_gene_symbol(gene)
        
        # Применяем буст для заболеваний с указанным геном
        boosted_results = []
        
        for candidate in base_results:
            disease_genes = [self.preprocessor.normalize_gene_symbol(g) 
                           for g in candidate.genes]
            
            if gene_normalized in disease_genes:
                # Увеличиваем скор для заболеваний с нужным геном
                boosted_score = min(candidate.score * gene_boost_factor, 1.0)
                candidate.score = boosted_score
                candidate.match_details["gene_boosted"] = True
                
            boosted_results.append(candidate)
                
        # Сортируем по новым скорам
        boosted_results.sort(key=lambda x: x.score, reverse=True)
        
        return boosted_results[:top_k]
    
    def find_similar_diseases(self, disease_id: str, top_k: int = 5) -> List[DiseaseCandidate]:
        """Найти похожие заболевания"""
        if disease_id not in self.diseases_cache:
            return []
            
        disease = self.diseases_cache[disease_id]
        
        # Используем название заболевания как запрос
        results = self.search([disease.name], top_k + 1)
        
        # Исключаем само заболевание из результатов
        return [r for r in results if r.omim_id != disease_id and r.mondo_id != disease_id][:top_k]
    
    def save_index(self, path: str):
        """Сохранить индекс на диск"""
        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем BM25 модель и данные
        index_data = {
            'disease_ids': self.disease_ids,
            'disease_texts': self.disease_texts,
            'tokenized_corpus': self.tokenized_corpus,
            'k1': self.k1,
            'b': self.b
        }
        
        with open(save_path / 'bm25_index.pkl', 'wb') as f:
            pickle.dump(index_data, f)
                
        logger.info(f"BM25 index saved to {save_path}")
        
    def load_index(self, path: str, diseases: Dict[str, Disease]):
        """Загрузить индекс с диска"""
        load_path = Path(path)
        
        # Загружаем данные
        with open(load_path / 'bm25_index.pkl', 'rb') as f:
            index_data = pickle.load(f)
            
        self.disease_ids = index_data['disease_ids']
        self.disease_texts = index_data['disease_texts']
        self.tokenized_corpus = index_data['tokenized_corpus']
        self.k1 = index_data.get('k1', 1.5)
        self.b = index_data.get('b', 0.75)
        
        # Восстанавливаем кеш заболеваний
        self.diseases_cache = diseases
        
        # Пересоздаем BM25 индекс
        self.bm25 = BM25Okapi(self.tokenized_corpus, k1=self.k1, b=self.b)
                
        logger.info(f"BM25 index loaded from {load_path}")