"""
Встроенные тесты для CLI
"""

import pandas as pd
from typing import List, Dict, Any

from .column_matcher import ColumnMatcher
from .processor import ExcelProcessor
from .config import Config


def test_column_detection() -> Dict[str, Any]:
    """Тест определения столбцов"""
    # Тестовый DataFrame с разными вариантами названий
    test_df = pd.DataFrame({
        'Диагноз': ['Синдром Марфана'],
        'Ген (symbol)': ['FBN1'],
        'Генотип': ['c.1234C>T'],
        'Заключение': ['Патогенный вариант']
    })
    
    matcher = ColumnMatcher()
    columns = matcher.analyze_columns(test_df)
    
    # Проверяем правильность определения
    diagnosis_ok = columns['diagnosis_column'] == 'Диагноз'
    gene_ok = columns['gene_column'] == 'Ген (symbol)'
    
    return {
        'name': 'Определение столбцов',
        'passed': diagnosis_ok and gene_ok,
        'error': None if diagnosis_ok and gene_ok else 
                f"Диагноз: {columns['diagnosis_column']}, Ген: {columns['gene_column']}"
    }


def test_empty_values_handling() -> Dict[str, Any]:
    """Тест обработки пустых значений"""
    test_df = pd.DataFrame({
        'Заболевание': ['Синдром Дауна', '-', 'NULL', '', 'NaN', '<NULL>'],
        'Gene': ['', 'CFTR', '-', 'FBN1', 'TP53', 'BRCA1']
    })
    
    config = Config()
    processor = ExcelProcessor(config)
    rows = processor._prepare_rows(test_df, 'Заболевание', 'Gene')
    
    # Должны быть пропущены строки с индексами 1, 2, 3, 4, 5
    skipped_indices = [r['index'] for r in rows if r['skip']]
    expected_skipped = [1, 2, 3, 4, 5]
    
    return {
        'name': 'Обработка пустых значений',
        'passed': skipped_indices == expected_skipped,
        'error': None if skipped_indices == expected_skipped else 
                f"Пропущены: {skipped_indices}, ожидалось: {expected_skipped}"
    }


def test_fuzzy_matching() -> Dict[str, Any]:
    """Тест нечеткого поиска столбцов"""
    test_df = pd.DataFrame({
        'Основной диагноз МКБ': ['G71.0'],
        'Генетический маркер': ['DMD'],
        'Дата исследования': ['2024-01-01']
    })
    
    matcher = ColumnMatcher()
    columns = matcher.analyze_columns(test_df)
    
    # Должен найти столбцы несмотря на неточное совпадение
    diagnosis_found = columns['diagnosis_column'] is not None
    gene_found = columns['gene_column'] is not None
    
    return {
        'name': 'Нечеткий поиск столбцов',
        'passed': diagnosis_found and gene_found,
        'error': None if diagnosis_found and gene_found else 
                f"Не найдены столбцы: диагноз={diagnosis_found}, ген={gene_found}"
    }


def test_gene_column_priority() -> Dict[str, Any]:
    """Тест приоритета при выборе столбца с геном"""
    test_df = pd.DataFrame({
        'Диагноз': ['Муковисцидоз'],
        'Генотип': ['p.Phe508del/p.Phe508del'],
        'Ген (symbol)': ['CFTR'],
        'Генетический анализ': ['Выполнен']
    })
    
    matcher = ColumnMatcher()
    columns = matcher.analyze_columns(test_df)
    
    # Должен выбрать "Ген (symbol)", а не "Генотип"
    correct_gene_col = columns['gene_column'] == 'Ген (symbol)'
    
    return {
        'name': 'Приоритет столбца с геном',
        'passed': correct_gene_col,
        'error': None if correct_gene_col else 
                f"Выбран столбец: {columns['gene_column']}"
    }


def test_config_operations() -> Dict[str, Any]:
    """Тест операций с конфигурацией"""
    config = Config()
    
    # Установка значений
    config.api_url = 'http://test:8080'
    config.max_concurrent = 10
    config.timeout = 30
    
    # Сохранение и загрузка
    config.save()
    
    new_config = Config()
    new_config.load()
    
    # Проверка
    values_match = (
        new_config.api_url == 'http://test:8080' and
        new_config.max_concurrent == 10 and
        new_config.timeout == 30
    )
    
    # Восстановление исходных значений
    original_config = Config()
    original_config.save()
    
    return {
        'name': 'Операции с конфигурацией',
        'passed': values_match,
        'error': None if values_match else 'Значения не совпадают после загрузки'
    }


def test_multilingual_columns() -> Dict[str, Any]:
    """Тест определения столбцов на разных языках"""
    test_df = pd.DataFrame({
        'Diagnosis': ['Marfan syndrome'],
        'Gene symbol': ['FBN1'],
        'Variant': ['c.1234C>T']
    })
    
    matcher = ColumnMatcher()
    columns = matcher.analyze_columns(test_df)
    
    # Должен определить английские названия
    diagnosis_found = columns['diagnosis_column'] == 'Diagnosis'
    gene_found = columns['gene_column'] == 'Gene symbol'
    
    return {
        'name': 'Многоязычные столбцы',
        'passed': diagnosis_found and gene_found,
        'error': None if diagnosis_found and gene_found else 
                'Не определены английские названия столбцов'
    }


def run_all_tests() -> List[Dict[str, Any]]:
    """Запустить все тесты"""
    tests = [
        test_column_detection,
        test_empty_values_handling,
        test_fuzzy_matching,
        test_gene_column_priority,
        test_config_operations,
        test_multilingual_columns
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            results.append({
                'name': test_func.__name__,
                'passed': False,
                'error': f"Исключение: {str(e)}"
            })
    
    return results