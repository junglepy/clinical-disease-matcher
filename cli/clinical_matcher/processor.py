#!/usr/bin/env python3
"""
Скрипт для обработки реальных клинических данных через API матчинга заболеваний.
Использует fuzzy matching для автоматического определения столбцов с диагнозом и геном.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime
from difflib import SequenceMatcher
from rapidfuzz import fuzz

# Опциональный импорт aiohttp
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # Определяем как None для типизации
    if "--run-tests" not in sys.argv:
        print("Warning: aiohttp не установлен. Установите: pip install aiohttp")
        print("Для запуска тестов aiohttp не требуется.")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Установить DEBUG для отладки
# logger.setLevel(logging.DEBUG)


class ColumnMatcher:
    """Интеллектуальное определение столбцов с помощью точного и fuzzy matching"""
    
    # Точные совпадения для столбцов (приоритет)
    DIAGNOSIS_EXACT = [
        'диагноз', 'диагноз*', 'diagnosis', 'заключение'
    ]
    
    GENE_EXACT = [
        'ген (symbol)', 'ген', 'gene', 'gene symbol', 'gene name'
    ]
    
    # Слова для fuzzy matching (если точное совпадение не найдено)
    DIAGNOSIS_FUZZY_WORDS = ['диагноз', 'diagnosis']
    GENE_FUZZY_WORDS = ['ген', 'gene']
    
    def __init__(self, threshold: float = 80.0):
        """
        Args:
            threshold: Минимальный порог схожести для fuzzy matching (0-100)
        """
        self.threshold = threshold
        
    def find_diagnosis_column(self, columns: List[str]) -> Optional[str]:
        """Поиск столбца с диагнозом"""
        # Сначала ищем точное совпадение
        for col in columns:
            if col.lower() in self.DIAGNOSIS_EXACT:
                logger.info(f"Найдено точное совпадение для диагноза: '{col}'")
                return col
        
        # Если не нашли, используем fuzzy matching
        return self._fuzzy_find_column(columns, self.DIAGNOSIS_FUZZY_WORDS)
        
    def find_gene_column(self, columns: List[str]) -> Optional[str]:
        """Поиск столбца с геном"""
        # Сначала ищем точное совпадение
        for col in columns:
            if col.lower() in self.GENE_EXACT:
                logger.info(f"Найдено точное совпадение для гена: '{col}'")
                return col
        
        # Если не нашли, используем fuzzy matching
        return self._fuzzy_find_column(columns, self.GENE_FUZZY_WORDS)
        
    def _fuzzy_find_column(self, columns: List[str], search_words: List[str]) -> Optional[str]:
        """Fuzzy поиск столбца по ключевым словам"""
        best_match = None
        best_score = 0
        
        for column in columns:
            # Нормализация для сравнения
            normalized_column = column.lower().strip()
            
            for word in search_words:
                # Проверяем, содержит ли столбец искомое слово
                if word in normalized_column:
                    # Точное вхождение слова - высокий приоритет
                    score = 90
                    
                    # Снижаем score, если слово является частью другого слова
                    # Например, "генотип" содержит "ген"
                    if word == 'ген' and ('генотип' in normalized_column or 'генетич' in normalized_column):
                        score = 50
                    elif word == 'gene' and 'genetic' in normalized_column:
                        score = 50
                else:
                    # Используем fuzzy matching для неточных совпадений
                    score = fuzz.partial_ratio(word, normalized_column)
                
                if score > best_score and score >= self.threshold:
                    best_score = score
                    best_match = column
        
        if best_match:
            logger.info(f"Найден столбец '{best_match}' через fuzzy matching с оценкой {best_score:.1f}%")
        
        return best_match
        
    def _normalize_column_name(self, column: str) -> str:
        """Нормализация названия столбца для сравнения"""
        # Убираем звездочки
        normalized = column.replace('*', '')
        # Убираем содержимое в скобках
        if '(' in normalized and ')' in normalized:
            start = normalized.find('(')
            end = normalized.find(')')
            if start < end:
                normalized = normalized[:start] + normalized[end+1:]
        # Убираем лишние пробелы и приводим к нижнему регистру
        return normalized.strip().lower()


class ClinicalDataProcessor:
    """Обработчик клинических данных с автоматическим определением столбцов"""
    
    def __init__(self, api_url: str, max_concurrent: int = 5):
        self.api_url = api_url.rstrip('/')
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.column_matcher = ColumnMatcher()
        
    async def process_excel(self, file_path: Path, output_path: Optional[Path] = None,
                          test_columns: bool = False) -> Dict:
        """
        Обработка Excel файла
        
        Args:
            file_path: Путь к входному файлу
            output_path: Путь для сохранения результата
            test_columns: Только тестировать определение столбцов
            
        Returns:
            Словарь со статистикой обработки
        """
        logger.info(f"Обработка файла: {file_path}")
        
        # Чтение файла
        try:
            if file_path.suffix.lower() == '.csv':
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path, engine='openpyxl')
            logger.info(f"Прочитано {len(df)} строк")
            logger.info(f"Столбцы: {list(df.columns)}")
        except Exception as e:
            logger.error(f"Ошибка чтения файла: {e}")
            return {"error": str(e)}
            
        # Определение столбцов
        diagnosis_col = self.column_matcher.find_diagnosis_column(df.columns.tolist())
        gene_col = self.column_matcher.find_gene_column(df.columns.tolist())
        
        if not diagnosis_col:
            logger.error("Не найден столбец с диагнозом")
            return {"error": "Столбец с диагнозом не найден"}
            
        logger.info(f"Столбец диагноза: '{diagnosis_col}'")
        logger.info(f"Столбец гена: '{gene_col}' (найден: {gene_col is not None})")
        
        # Если только тестируем определение столбцов
        if test_columns:
            return {
                "diagnosis_column": diagnosis_col,
                "gene_column": gene_col,
                "columns": df.columns.tolist()
            }
        
        # Подготовка данных для обработки
        rows_to_process = self._prepare_rows(df, diagnosis_col, gene_col)
        
        # Обработка через API
        logger.info(f"Обработка {len([r for r in rows_to_process if not r['skip']])} диагнозов через API...")
        results = await self._process_batch(rows_to_process)
        
        # Добавление результатов в DataFrame
        df = self._add_results_to_dataframe(df, rows_to_process, results)
        
        # Сохранение результатов
        if output_path is None:
            if file_path.suffix.lower() == '.csv':
                output_path = file_path.parent / f"{file_path.stem}_processed.csv"
            else:
                output_path = file_path.parent / f"{file_path.stem}_processed.xlsx"
            
        # Сохранение в том же формате
        if file_path.suffix.lower() == '.csv':
            df.to_csv(output_path, index=False)
        else:
            df.to_excel(output_path, index=False, engine='openpyxl')
        logger.info(f"Результаты сохранены в: {output_path}")
        
        # Статистика
        stats = self._calculate_statistics(rows_to_process, results)
        self._print_statistics(stats)
        
        return stats
        
    def _prepare_rows(self, df: pd.DataFrame, diagnosis_col: str, gene_col: Optional[str]) -> List[Dict]:
        """Подготовка строк для обработки"""
        rows_to_process = []
        
        for idx, row in df.iterrows():
            diagnosis = str(row[diagnosis_col]) if pd.notna(row[diagnosis_col]) else ""
            gene = ""
            if gene_col and gene_col in row:
                gene = str(row[gene_col]) if pd.notna(row[gene_col]) else ""
            
            # Собираем полный контекст строки
            full_context_parts = []
            for col in df.columns:
                # Пропускаем столбцы с индексами типа "Unnamed: 0"
                if not col.startswith('Unnamed:'):
                    value = str(row[col]) if pd.notna(row[col]) else "<Пустая строка>"
                    full_context_parts.append(f"{col}: {value}")
            full_context = " | ".join(full_context_parts)
            
            # Проверка на пустой диагноз
            diagnosis_clean = diagnosis.strip()
            # Расширенный список значений, которые считаются пустыми
            empty_values = [
                "-", "–", "—", "nan", "NaN", "None", "null", "NULL", 
                "<NULL>", "<null>", "N/A", "n/a", "#N/A", "#VALUE!", 
                "<Пустая строка>", ""
            ]
            if not diagnosis_clean or diagnosis_clean in empty_values:
                rows_to_process.append({
                    'index': idx,
                    'diagnosis': "",
                    'gene': "",
                    'full_context': full_context,
                    'skip': True
                })
            else:
                rows_to_process.append({
                    'index': idx,
                    'diagnosis': diagnosis_clean,
                    'gene': gene.strip() if gene else "",
                    'full_context': full_context,
                    'skip': False
                })
                
        return rows_to_process
        
    async def _process_batch(self, rows: List[Dict]) -> Dict[int, Dict]:
        """Обработка батча диагнозов через API"""
        results = {}
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for row_data in rows:
                if not row_data['skip']:
                    task = self._process_single(
                        session, 
                        row_data['index'],
                        row_data['diagnosis'],
                        row_data['gene'],
                        row_data['full_context']
                    )
                    tasks.append(task)
                    
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for response in responses:
                if isinstance(response, Exception):
                    logger.error(f"Ошибка при обработке: {response}")
                elif response:
                    idx, result = response
                    results[idx] = result
                    # Выводим результат сразу как он приходит
                    diag = next(r['diagnosis'] for r in rows if r['index'] == idx)
                    logger.info(f"Обработано: {diag[:50]}... → OMIM: {result.get('omim_code', '-')}")
                    
        return results
        
    async def _process_single(self, session: "aiohttp.ClientSession", idx: int,
                            diagnosis: str, gene: str, full_context: str) -> Optional[Tuple[int, Dict]]:
        """Обработка одного диагноза"""
        async with self.semaphore:
            try:
                # Подготовка запроса
                payload = {
                    "text": diagnosis,
                    "language": "ru",
                    "full_context": full_context
                }
                if gene:
                    payload["gene"] = gene
                    
                # Отправка запроса
                async with session.post(
                    f"{self.api_url}/api/v1/match",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Извлечение результатов с умным выбором кодов
                        if data.get('results'):
                            results = data['results']
                            
                            # ВСЕГДА берем первый результат
                            first_result = results[0] if results else None
                            omim_code = first_result.get('omim_id') or '-' if first_result else '-'
                            mondo_code = first_result.get('mondo_id') or '-' if first_result else '-'
                            
                            # Получаем название заболевания с приоритетом MONDO
                            disease_name = '-'
                            
                            # Сначала ищем результат с MONDO кодом
                            mondo_result = None
                            for result in results:
                                if result.get('mondo_id'):
                                    mondo_result = result
                                    break
                            
                            # Если есть MONDO - берем его название, иначе - название из первого результата
                            if mondo_result:
                                disease_name = mondo_result.get('name', '-')
                            elif first_result:
                                disease_name = first_result.get('name', '-')
                                
                            clarification = '-'
                            
                            # Проверяем флаг requires_clarification из первого результата
                            if first_result and first_result.get('requires_clarification'):
                                reason = first_result.get('clarification_reason', 'Требуется клиническое уточнение')
                                clarification = reason
                            
                            # Если в первом результате нет OMIM
                            if omim_code == '-':
                                # Ищем ближайший OMIM в следующих результатах
                                for result in results[1:]:
                                    if result.get('omim_id'):
                                        name = result.get('name', '')[:25]
                                        if clarification == '-':
                                            clarification = f"OMIM не найден. Ближайший: {result['omim_id']}:{name}"
                                        else:
                                            clarification += f"; OMIM не найден. Ближайший: {result['omim_id']}:{name}"
                                        break
                                
                                if omim_code == '-' and "OMIM не найден" not in clarification:
                                    if clarification == '-':
                                        clarification = "OMIM не найден"
                                    else:
                                        clarification += "; OMIM не найден"
                            
                            # Если в первом результате нет MONDO
                            if mondo_code == '-':
                                # Ищем ближайший MONDO в следующих результатах
                                for result in results[1:]:
                                    if result.get('mondo_id'):
                                        if clarification == '-':
                                            clarification = f"MONDO не найден. Ближайший: {result['mondo_id']}"
                                        elif "OMIM не найден" in clarification:
                                            clarification += f", MONDO не найден. Ближайший: {result['mondo_id']}"
                                        break
                                
                                if mondo_code == '-' and "MONDO не найден" not in clarification:
                                    if clarification == '-':
                                        clarification = "MONDO не найден"
                                    else:
                                        clarification += ", MONDO не найден"
                            
                            return idx, {
                                'omim_code': omim_code,
                                'mondo_code': mondo_code,
                                'disease_name': disease_name,
                                'clarification': clarification
                            }
                        else:
                            return idx, {
                                'omim_code': 'Не найдено',
                                'mondo_code': 'Не найдено',
                                'disease_name': '-',
                                'clarification': 'Нет результатов'
                            }
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка API для '{diagnosis[:30]}...': {response.status}")
                        return idx, {
                            'omim_code': f'Ошибка {response.status}',
                            'mondo_code': f'Ошибка {response.status}',
                            'disease_name': '-',
                            'clarification': 'Ошибка API'
                        }
                        
            except asyncio.TimeoutError:
                logger.error(f"Таймаут для диагноза '{diagnosis[:30]}...'")
                return idx, {
                    'omim_code': 'Таймаут',
                    'mondo_code': 'Таймаут',
                    'disease_name': '-',
                    'clarification': 'Превышено время ожидания'
                }
            except Exception as e:
                logger.error(f"Ошибка обработки '{diagnosis[:30]}...': {e}")
                return idx, {
                    'omim_code': 'Ошибка',
                    'mondo_code': 'Ошибка',
                    'disease_name': '-',
                    'clarification': f'Ошибка: {str(e)[:50]}'
                }
                
    def _add_results_to_dataframe(self, df: pd.DataFrame, rows: List[Dict], 
                                 results: Dict[int, Dict]) -> pd.DataFrame:
        """Добавление результатов в DataFrame"""
        omim_codes = []
        mondo_codes = []
        disease_names = []
        clarifications = []
        
        for row_data in rows:
            idx = row_data['index']
            if row_data['skip']:
                omim_codes.append("-")
                mondo_codes.append("-")
                disease_names.append("-")
                clarifications.append("-")
            else:
                result = results.get(idx, {})
                omim_codes.append(result.get('omim_code', 'Ошибка'))
                mondo_codes.append(result.get('mondo_code', 'Ошибка'))
                disease_names.append(result.get('disease_name', '-'))
                clarifications.append(result.get('clarification', 'Ошибка обработки'))
        
        df['OMIM_код'] = omim_codes
        df['MONDO_код'] = mondo_codes
        df['Название_заболевания'] = disease_names
        df['Требует_уточнения'] = clarifications
        
        return df
        
    def _calculate_statistics(self, rows: List[Dict], results: Dict[int, Dict]) -> Dict:
        """Расчет статистики обработки"""
        total_rows = len(rows)
        processed = len([r for r in rows if not r['skip']])
        skipped = len([r for r in rows if r['skip']])
        
        # Подсчет ошибок
        errors = 0
        not_found = 0
        successful = 0
        
        for row_data in rows:
            if not row_data['skip']:
                result = results.get(row_data['index'], {})
                omim = result.get('omim_code', 'Ошибка')
                
                if 'Ошибка' in omim or 'Таймаут' in omim:
                    errors += 1
                elif omim == 'Не найдено':
                    not_found += 1
                elif omim and omim != '-':
                    successful += 1
                    
        return {
            'total_rows': total_rows,
            'processed': processed,
            'skipped': skipped,
            'successful': successful,
            'not_found': not_found,
            'errors': errors
        }
        
    def _print_statistics(self, stats: Dict):
        """Вывод статистики"""
        logger.info("\nСтатистика обработки:")
        logger.info(f"  - Всего строк: {stats['total_rows']}")
        logger.info(f"  - Обработано диагнозов: {stats['processed']}")
        logger.info(f"  - Пропущено (пустые): {stats['skipped']}")
        logger.info(f"  - Успешно найдено: {stats['successful']}")
        logger.info(f"  - Не найдено: {stats['not_found']}")
        logger.info(f"  - Ошибок при обработке: {stats['errors']}")


def test_column_detection():
    """Встроенные тесты для проверки определения столбцов"""
    logger.info("\n=== Тестирование определения столбцов ===")
    
    matcher = ColumnMatcher()
    
    # Тест 1: NGS формат
    logger.info("\nТест 1: NGS формат")
    columns1 = ["Идентификатор БТК", "Диагноз*", "Направительный диагноз", 
                "Хромосома*", "Ген (symbol)", "Комментарий"]
    
    diag1 = matcher.find_diagnosis_column(columns1)
    gene1 = matcher.find_gene_column(columns1)
    
    assert diag1 == "Диагноз*", f"Ожидался 'Диагноз*', получен '{diag1}'"
    assert gene1 == "Ген (symbol)", f"Ожидался 'Ген (symbol)', получен '{gene1}'"
    logger.info("✓ Тест 1 пройден")
    
    # Тест 2: WGS формат
    logger.info("\nТест 2: WGS формат")
    columns2 = ["Ген", "ПоложениеGRCh38hg18", "Генотип", "Эффект", 
                "Транскрипт", "Патогенность", "ОписанВЛитературе", "Диагноз"]
    
    diag2 = matcher.find_diagnosis_column(columns2)
    gene2 = matcher.find_gene_column(columns2)
    
    assert diag2 == "Диагноз", f"Ожидался 'Диагноз', получен '{diag2}'"
    assert gene2 == "Ген", f"Ожидался 'Ген', получен '{gene2}'"
    logger.info("✓ Тест 2 пройден")
    
    # Тест 3: Альтернативные названия
    logger.info("\nТест 3: Альтернативные названия")
    columns3 = ["ID", "Заключение", "Gene Symbol", "Variant", "Status"]
    
    diag3 = matcher.find_diagnosis_column(columns3)
    gene3 = matcher.find_gene_column(columns3)
    
    assert diag3 == "Заключение", f"Ожидался 'Заключение', получен '{diag3}'"
    assert gene3 == "Gene Symbol", f"Ожидался 'Gene Symbol', получен '{gene3}'"
    logger.info("✓ Тест 3 пройден")
    
    logger.info("\n✅ Все тесты пройдены успешно!")
    
    # Демонстрация работы с реальными примерами из файлов
    logger.info("\n=== Проверка на реальных примерах ===")
    
    # Пример 1: NGS
    logger.info("\nПример данных NGS:")
    logger.info("Диагноз*: несфероцитарной гемолитической анемии вследствие дефицита глюкозофосфат-изомеразы")
    logger.info("Ген (symbol): GPI")
    
    # Пример 2: WGS
    logger.info("\nПример данных WGS:")
    logger.info("Диагноз: Дисплазия соединительной ткани (M35 Другие системные поражения соединительной ткани)")
    logger.info("Ген: ABCD1")


async def main():
    parser = argparse.ArgumentParser(
        description='Обработка клинических Excel файлов через API матчинга заболеваний'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='Пути к Excel файлам для обработки'
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8002',
        help='URL API сервиса (по умолчанию: http://localhost:8002)'
    )
    parser.add_argument(
        '--output-dir',
        help='Директория для сохранения результатов'
    )
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=5,
        help='Максимальное количество параллельных запросов (по умолчанию: 5)'
    )
    parser.add_argument(
        '--test-columns',
        action='store_true',
        help='Только тестировать определение столбцов без обработки через API'
    )
    parser.add_argument(
        '--run-tests',
        action='store_true',
        help='Запустить встроенные тесты'
    )
    
    args = parser.parse_args()
    
    # Запуск тестов
    if args.run_tests:
        test_column_detection()
        return
        
    # Проверка наличия файлов
    if not args.files:
        logger.error("Не указаны файлы для обработки. Используйте --run-tests для запуска тестов.")
        parser.print_help()
        return
    
    # Создание процессора
    processor = ClinicalDataProcessor(
        api_url=args.api_url,
        max_concurrent=args.max_concurrent
    )
    
    # Обработка файлов
    for file_path in args.files:
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"Файл не найден: {file_path}")
            continue
            
        if not file_path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
            logger.error(f"Неподдерживаемый формат файла: {file_path}")
            continue
            
        # Определение пути для сохранения
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{file_path.stem}_processed.xlsx"
        else:
            output_path = None
            
        try:
            stats = await processor.process_excel(
                file_path, 
                output_path,
                test_columns=args.test_columns
            )
            
            if args.test_columns:
                logger.info(f"\nОпределены столбцы:")
                logger.info(f"  Диагноз: {stats.get('diagnosis_column', 'Не найден')}")
                logger.info(f"  Ген: {stats.get('gene_column', 'Не найден')}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки файла {file_path}: {e}")
            
    logger.info("\nОбработка завершена")


if __name__ == "__main__":
    asyncio.run(main())