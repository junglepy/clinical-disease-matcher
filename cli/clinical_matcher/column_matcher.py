"""
Модуль для интеллектуального определения столбцов в Excel/CSV файлах
"""

from typing import Optional, List, Dict, Tuple
from rapidfuzz import fuzz
import pandas as pd


class ColumnMatcher:
    """Класс для определения столбцов с диагнозами и генами"""
    
    # Ключевые слова для поиска столбца с диагнозом
    DIAGNOSIS_KEYWORDS = [
        'диагноз', 'заболевание', 'болезнь', 'патология', 'заключение',
        'diagnosis', 'disease', 'disorder', 'condition', 'finding',
        'фенотип', 'phenotype', 'синдром', 'syndrome'
    ]
    
    # Ключевые слова для поиска столбца с геном
    GENE_KEYWORDS = [
        'ген', 'gene', 'гены', 'genes', 'мутация', 'mutation',
        'вариант', 'variant', 'символ', 'symbol'
    ]
    
    # Стоп-слова для исключения неподходящих столбцов
    GENE_STOPWORDS = [
        'генотип', 'genotype', 'генетический', 'genetic',
        'анализ', 'analysis', 'тест', 'test'
    ]
    
    def __init__(self, min_score: float = 60.0):
        """
        Инициализация
        
        Args:
            min_score: Минимальный порог схожести для fuzzy matching (0-100)
        """
        self.min_score = min_score
    
    def find_diagnosis_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        Найти столбец с диагнозами
        
        Args:
            df: DataFrame для анализа
            
        Returns:
            Название столбца или None
        """
        return self._find_column_by_keywords(df, self.DIAGNOSIS_KEYWORDS)
    
    def find_gene_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        Найти столбец с генами
        
        Args:
            df: DataFrame для анализа
            
        Returns:
            Название столбца или None
        """
        # Сначала пробуем точное совпадение
        exact_matches = ['Ген (symbol)', 'Gene (symbol)', 'Ген', 'Gene']
        for col in df.columns:
            if col in exact_matches:
                return col
        
        # Затем fuzzy поиск с учетом стоп-слов
        candidates = []
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Пропускаем столбцы со стоп-словами
            if any(stopword in col_lower for stopword in self.GENE_STOPWORDS):
                continue
            
            # Ищем ключевые слова
            best_score = 0
            for keyword in self.GENE_KEYWORDS:
                # Для коротких слов используем точное вхождение
                if len(keyword) <= 3:
                    if keyword in col_lower:
                        score = 100
                    else:
                        continue
                else:
                    score = fuzz.partial_ratio(keyword, col_lower)
                
                if score > best_score:
                    best_score = score
            
            if best_score >= self.min_score:
                candidates.append((col, best_score))
        
        if candidates:
            # Возвращаем столбец с максимальным score
            return max(candidates, key=lambda x: x[1])[0]
        
        return None
    
    def _find_column_by_keywords(self, df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
        """
        Найти столбец по списку ключевых слов
        
        Args:
            df: DataFrame для анализа
            keywords: Список ключевых слов для поиска
            
        Returns:
            Название столбца или None
        """
        candidates = []
        
        for col in df.columns:
            col_lower = col.lower()
            best_score = 0
            
            for keyword in keywords:
                score = fuzz.partial_ratio(keyword, col_lower)
                if score > best_score:
                    best_score = score
            
            if best_score >= self.min_score:
                candidates.append((col, best_score))
        
        if candidates:
            # Возвращаем столбец с максимальным score
            return max(candidates, key=lambda x: x[1])[0]
        
        return None
    
    def analyze_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Проанализировать все столбцы и найти нужные
        
        Args:
            df: DataFrame для анализа
            
        Returns:
            Словарь с найденными столбцами
        """
        result = {
            'diagnosis_column': self.find_diagnosis_column(df),
            'gene_column': self.find_gene_column(df)
        }
        
        return result
    
    def get_column_scores(self, df: pd.DataFrame) -> List[Tuple[str, str, float]]:
        """
        Получить scores для всех столбцов (для отладки)
        
        Args:
            df: DataFrame для анализа
            
        Returns:
            Список кортежей (столбец, тип, score)
        """
        scores = []
        
        # Scores для диагнозов
        for col in df.columns:
            col_lower = col.lower()
            best_score = 0
            
            for keyword in self.DIAGNOSIS_KEYWORDS:
                score = fuzz.partial_ratio(keyword, col_lower)
                if score > best_score:
                    best_score = score
            
            if best_score > 0:
                scores.append((col, 'diagnosis', best_score))
        
        # Scores для генов
        for col in df.columns:
            col_lower = col.lower()
            
            # Пропускаем столбцы со стоп-словами
            if any(stopword in col_lower for stopword in self.GENE_STOPWORDS):
                continue
            
            best_score = 0
            for keyword in self.GENE_KEYWORDS:
                if len(keyword) <= 3:
                    if keyword in col_lower:
                        score = 100
                    else:
                        continue
                else:
                    score = fuzz.partial_ratio(keyword, col_lower)
                
                if score > best_score:
                    best_score = score
            
            if best_score > 0:
                scores.append((col, 'gene', best_score))
        
        # Сортируем по score
        scores.sort(key=lambda x: x[2], reverse=True)
        
        return scores