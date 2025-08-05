import re
from pathlib import Path
from typing import List, Dict, Set, Optional
import logging

from .models import OmimDisease

logger = logging.getLogger(__name__)


class GeneToOmimLookup:
    """Традиционный поиск заболеваний по гену через genemap2.txt"""
    
    def __init__(self, genemap_path: str):
        self.genemap_path = Path(genemap_path)
        self.gene_to_diseases: Dict[str, List[OmimDisease]] = {}
        self.gene_aliases: Dict[str, str] = {}  # alias -> primary gene symbol
        self._load_genemap()
        
    def _load_genemap(self):
        """Загрузка и парсинг genemap2.txt"""
        if not self.genemap_path.exists():
            raise FileNotFoundError(f"genemap2.txt not found at {self.genemap_path}")
            
        logger.info(f"Loading genemap from {self.genemap_path}")
        
        with open(self.genemap_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                    
                parts = line.strip().split('\t')
                if len(parts) >= 13:
                    # Извлекаем данные
                    mim_number = parts[5]
                    gene_symbols = parts[6]  # Может содержать несколько символов через запятую
                    approved_symbol = parts[8]
                    phenotypes = parts[12]
                    
                    # Обрабатываем символы генов
                    all_symbols = set()
                    
                    if approved_symbol and approved_symbol != '-':
                        all_symbols.add(approved_symbol.upper())
                        
                    if gene_symbols and gene_symbols != '-':
                        for symbol in gene_symbols.split(','):
                            symbol = symbol.strip().upper()
                            if symbol:
                                all_symbols.add(symbol)
                                # Сохраняем алиасы
                                if approved_symbol and approved_symbol != '-':
                                    self.gene_aliases[symbol] = approved_symbol.upper()
                    
                    # Парсим фенотипы
                    if phenotypes and phenotypes != '-':
                        diseases = self._parse_phenotypes(phenotypes, mim_number, list(all_symbols))
                        # Отладка для гена ABCD1
                        if 'ABCD1' in all_symbols:
                            logger.info(f"DEBUG: Parsing ABCD1 - gene MIM: {mim_number}, phenotypes: {phenotypes[:100]}...")
                            logger.info(f"DEBUG: Found {len(diseases)} diseases")
                        
                        # Добавляем заболевания для каждого гена
                        for gene in all_symbols:
                            if gene not in self.gene_to_diseases:
                                self.gene_to_diseases[gene] = []
                            self.gene_to_diseases[gene].extend(diseases)
                            
        logger.info(f"Loaded {len(self.gene_to_diseases)} genes with disease associations")
        
    def _parse_phenotypes(self, phenotypes_str: str, gene_mim: str, genes: List[str]) -> List[OmimDisease]:
        """Парсинг колонки с фенотипами"""
        diseases = []
        
        # Два формата фенотипов в genemap2.txt:
        # 1. С фигурными скобками: {Disease name}, 123456 (confidence)
        # 2. Без скобок: Disease name, 123456 (confidence)
        
        # Сначала пробуем формат с фигурными скобками
        pattern_braces = r'\{([^}]+)\},\s*(\d{6})'
        matches = re.findall(pattern_braces, phenotypes_str)
        
        # Если не нашли, пробуем формат без скобок
        if not matches:
            # Паттерн: название до последней запятой перед 6-значным номером
            # Изменено с [^,;]+? на (.+?) чтобы захватывать полные названия типа "Spherocytosis, type 1"
            # Ищем любой текст до ", XXXXXX (" где XXXXXX - 6-значный номер
            pattern_no_braces = r'(.+?),\s*(\d{6})\s*\('
            matches = re.findall(pattern_no_braces, phenotypes_str)
        
        for phenotype_name, phenotype_mim in matches:
            disease = OmimDisease(
                omim_id=phenotype_mim,
                name=phenotype_name.strip(),
                genes=genes,
                phenotypes=[phenotype_name.strip()]
            )
            diseases.append(disease)
            
        # Если не нашли фенотипы в фигурных скобках, пробуем другой формат
        # ВАЖНО: НЕ используем gene_mim как ID заболевания - это ID гена!
        # Этот блок закомментирован, так как создавал неправильные записи
        # if not diseases and gene_mim and gene_mim.isdigit():
        #     # Иногда заболевание указано просто через MIM номер гена
        #     disease_name = phenotypes_str.split(',')[0].strip() if ',' in phenotypes_str else phenotypes_str.strip()
        #     if disease_name and not disease_name.startswith('{'):
        #         disease = OmimDisease(
        #             omim_id=gene_mim,  # ОШИБКА: это ID гена, а не заболевания!
        #             name=disease_name,
        #             genes=genes,
        #             phenotypes=[disease_name]
        #         )
        #         diseases.append(disease)
                
        return diseases
        
    def search_by_gene(self, gene_symbol: str, include_aliases: bool = True) -> List[OmimDisease]:
        """Поиск заболеваний по символу гена"""
        gene_upper = gene_symbol.upper()
        results = []
        
        # Прямой поиск
        if gene_upper in self.gene_to_diseases:
            results.extend(self.gene_to_diseases[gene_upper])
            
        # Поиск через алиасы
        if include_aliases and gene_upper in self.gene_aliases:
            primary_gene = self.gene_aliases[gene_upper]
            if primary_gene in self.gene_to_diseases:
                results.extend(self.gene_to_diseases[primary_gene])
                
        # Также проверяем, не является ли данный ген primary для других
        if include_aliases:
            for alias, primary in self.gene_aliases.items():
                if primary == gene_upper and alias in self.gene_to_diseases:
                    results.extend(self.gene_to_diseases[alias])
                    
        # Убираем дубликаты по OMIM ID
        seen_ids = set()
        unique_results = []
        for disease in results:
            if disease.omim_id not in seen_ids:
                seen_ids.add(disease.omim_id)
                unique_results.append(disease)
                
        logger.info(f"Found {len(unique_results)} diseases for gene {gene_symbol}")
        return unique_results
        
    def get_gene_aliases(self, gene_symbol: str) -> List[str]:
        """Получить все известные алиасы гена"""
        gene_upper = gene_symbol.upper()
        aliases = set()
        
        # Добавляем сам ген
        aliases.add(gene_upper)
        
        # Если это алиас, добавляем primary
        if gene_upper in self.gene_aliases:
            aliases.add(self.gene_aliases[gene_upper])
            
        # Находим все алиасы для данного primary гена
        for alias, primary in self.gene_aliases.items():
            if primary == gene_upper or (gene_upper in self.gene_aliases and primary == self.gene_aliases[gene_upper]):
                aliases.add(alias)
                
        return list(aliases)
        
    def get_all_genes(self) -> List[str]:
        """Получить список всех известных генов"""
        return list(self.gene_to_diseases.keys())
        
    def get_statistics(self) -> Dict[str, int]:
        """Получить статистику по загруженным данным"""
        total_diseases = sum(len(diseases) for diseases in self.gene_to_diseases.values())
        unique_diseases = len(set(
            disease.omim_id 
            for diseases in self.gene_to_diseases.values() 
            for disease in diseases
        ))
        
        return {
            "total_genes": len(self.gene_to_diseases),
            "total_aliases": len(self.gene_aliases),
            "total_disease_associations": total_diseases,
            "unique_diseases": unique_diseases
        }