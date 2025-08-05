import os
import re
import json
import logging
from typing import Dict, List, Tuple, Set, Optional
from pathlib import Path

from .models import Disease

logger = logging.getLogger(__name__)


class DataLoader:
    """Загрузчик данных из OMIM и MONDO с расширенной поддержкой синонимов"""
    
    def __init__(self, data_dir: str = "../datasets"):
        self.data_dir = Path(data_dir)
        self.diseases: Dict[str, Disease] = {}
        self.gene_to_diseases: Dict[str, Set[str]] = {}
        self.omim_to_mondo: Dict[str, str] = {}
        self.mondo_to_omim: Dict[str, str] = {}
        
    def load_all(self) -> Dict[str, Disease]:
        """Загрузить все данные"""
        logger.info("Loading OMIM data...")
        self._load_omim()
        
        logger.info("Loading MONDO data...")
        self._load_mondo()
        
        logger.info(f"Loaded {len(self.diseases)} diseases")
        logger.info(f"Cross-references: {len(self.omim_to_mondo)} OMIM->MONDO mappings")
        
        # Обогащаем заболевания генами из gene_to_diseases
        self._enrich_diseases_with_genes()
        
        return self.diseases
    
    def _load_omim(self):
        """Загрузить данные OMIM"""
        # Загрузка mimTitles.txt
        mim_titles_path = self.data_dir / "OMIM" / "mimTitles.txt"
        if not mim_titles_path.exists():
            logger.warning(f"OMIM mimTitles.txt not found at {mim_titles_path}")
            return
            
        with open(mim_titles_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                    
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    prefix = parts[0]
                    mim_number = parts[1]
                    preferred_title = parts[2]
                    
                    # ВАЖНО: Фильтруем только записи заболеваний/фенотипов
                    # Asterisk (*) - гены, пропускаем
                    # Number Sign (#) - заболевания с известной молекулярной основой
                    # Percent (%) - заболевания с неясным типом наследования
                    # Plus (+) - локусы, пропускаем
                    # Caret (^) - устаревшие записи, пропускаем
                    
                    if prefix not in ['Number Sign', 'Percent']:
                        continue
                    
                    # Парсинг альтернативных названий
                    alternative_titles = []
                    if len(parts) > 3 and parts[3]:
                        # Удаляем символы в конце названий
                        alt_titles = re.sub(r'[;,]\s*$', '', parts[3])
                        alternative_titles = [t.strip() for t in re.split(r';;|;', alt_titles)]
                    
                    # Извлечение названия без символов генов
                    clean_name = re.sub(r';.*$', '', preferred_title).strip()
                    
                    disease = Disease(
                        id=f"OMIM:{mim_number}",
                        name=clean_name,
                        alternative_names=alternative_titles,
                        genes=[],
                        source="OMIM",
                        exact_synonyms=[],  # OMIM не различает типы синонимов
                        related_synonyms=[],
                        subsets=[],
                        cross_references={}
                    )
                    self.diseases[disease.id] = disease
        
        # Загрузка genemap2.txt для связей с генами
        genemap_path = self.data_dir / "OMIM" / "genemap2.txt"
        if not genemap_path.exists():
            # Пробуем альтернативный путь
            genemap_path = Path("data/genemap2.txt")
            
        if genemap_path.exists():
            self._load_omim_genes(genemap_path)
        else:
            logger.warning(f"genemap2.txt not found at {genemap_path}")
            
    def _load_omim_genes(self, genemap_path: Path):
        """Загрузить связи генов из genemap2"""
        with open(genemap_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                    
                parts = line.strip().split('\t')
                if len(parts) >= 13:
                    mim_number = parts[5]
                    gene_symbols = parts[6]
                    approved_symbol = parts[8]
                    phenotypes = parts[12]
                    
                    # Собираем все гены для этой записи
                    all_genes = []
                    if gene_symbols and gene_symbols != '-':
                        all_genes.extend([g.strip() for g in re.split(r'[,;]', gene_symbols) if g.strip()])
                    
                    if approved_symbol and approved_symbol != '-' and approved_symbol not in all_genes:
                        all_genes.append(approved_symbol)
                    
                    # Обрабатываем фенотипы и создаем заболевания из них
                    if phenotypes and phenotypes != '-':
                        # Парсим фенотипы используя regex для извлечения названия и OMIM ID
                        # Формат: "Disease name, OMIM_ID (confidence), inheritance"
                        phenotype_matches = re.findall(r'([^{]*?),\s*(\d{6})\s*\([^)]+\)', phenotypes)
                        
                        for disease_name, pheno_mim in phenotype_matches:
                            pheno_id = f"OMIM:{pheno_mim}"
                            
                            # Создаем заболевание если его еще нет
                            if pheno_id not in self.diseases:
                                self.diseases[pheno_id] = Disease(
                                    id=pheno_id,
                                    name=disease_name.strip(),
                                    alternative_names=[],
                                    genes=[],
                                    source="OMIM",
                                    exact_synonyms=[],
                                    related_synonyms=[],
                                    subsets=[],
                                    cross_references={}
                                )
                            
                            # Добавляем гены к заболеванию
                            for gene in all_genes:
                                if gene not in self.diseases[pheno_id].genes:
                                    self.diseases[pheno_id].genes.append(gene)
                                
                                # Обновляем маппинг ген -> заболевания
                                if gene not in self.gene_to_diseases:
                                    self.gene_to_diseases[gene] = set()
                                self.gene_to_diseases[gene].add(pheno_id)
    
    def _load_mondo(self):
        """Загрузить данные MONDO с расширенной информацией"""
        mondo_json_path = self.data_dir / "mondo" / "mondo.json"
        mondo_obo_path = self.data_dir / "mondo" / "mondo.obo"
        
        if mondo_json_path.exists():
            self._load_mondo_json(mondo_json_path)
        elif mondo_obo_path.exists():
            self._load_mondo_obo(mondo_obo_path)
        else:
            logger.warning("MONDO data not found")
            
    def _load_mondo_json(self, mondo_path: Path):
        """Загрузить MONDO из JSON с полной информацией о синонимах"""
        try:
            with open(mondo_path, 'r', encoding='utf-8') as f:
                mondo_data = json.load(f)
                
            # Парсим nodes/terms
            if 'graphs' in mondo_data:
                for graph in mondo_data['graphs']:
                    if 'nodes' in graph:
                        for node in graph['nodes']:
                            node_id = node.get('id', '')
                            # Check for MONDO IDs in URL format
                            if 'MONDO_' in node_id:
                                # Extract MONDO ID from URL format
                                if node_id.startswith('http://purl.obolibrary.org/obo/MONDO_'):
                                    mondo_id = node_id.replace('http://purl.obolibrary.org/obo/', '').replace('_', ':')
                                else:
                                    continue
                                    
                                name = node.get('lbl', '')
                                
                                # Skip obsolete terms
                                if name.startswith('obsolete'):
                                    continue
                                
                                # Получаем все типы синонимов
                                exact_synonyms = []
                                related_synonyms = []
                                alternative_names = []
                                
                                if 'meta' in node:
                                    # Обрабатываем синонимы
                                    if 'synonyms' in node['meta']:
                                        for syn in node['meta']['synonyms']:
                                            if 'val' in syn:
                                                syn_value = syn['val']
                                                syn_pred = syn.get('pred', '')
                                                
                                                if 'hasExactSynonym' in syn_pred:
                                                    exact_synonyms.append(syn_value)
                                                elif 'hasRelatedSynonym' in syn_pred:
                                                    related_synonyms.append(syn_value)
                                                else:
                                                    alternative_names.append(syn_value)
                                    
                                    # Получаем subsets
                                    subsets = []
                                    if 'subsets' in node['meta']:
                                        subsets = [s.split('/')[-1] for s in node['meta']['subsets']]
                                
                                # Объединяем все синонимы для alternative_names
                                all_alternative_names = list(set(alternative_names + exact_synonyms + related_synonyms))
                                
                                disease = Disease(
                                    id=mondo_id,
                                    name=name,
                                    alternative_names=all_alternative_names,
                                    genes=[],
                                    source="MONDO",
                                    exact_synonyms=exact_synonyms,
                                    related_synonyms=related_synonyms,
                                    subsets=subsets,
                                    cross_references={}
                                )
                                self.diseases[disease.id] = disease
                                
                                # Extract OMIM cross-references
                                if 'meta' in node and 'xrefs' in node['meta']:
                                    for xref in node['meta']['xrefs']:
                                        xref_val = xref.get('val', '')
                                        if xref_val.startswith('OMIM:'):
                                            omim_id = xref_val
                                            self.omim_to_mondo[omim_id] = mondo_id
                                            self.mondo_to_omim[mondo_id] = omim_id
                                            disease.cross_references[omim_id] = mondo_id
                                            
                                            # Если есть соответствующее OMIM заболевание, добавляем кросс-ссылку
                                            if omim_id in self.diseases:
                                                self.diseases[omim_id].cross_references[mondo_id] = omim_id
                                                # Копируем гены из OMIM в MONDO
                                                disease.genes = self.diseases[omim_id].genes.copy()
                                
        except Exception as e:
            logger.error(f"Error loading MONDO JSON: {e}")
            
    def _load_mondo_obo(self, mondo_path: Path):
        """Загрузить MONDO из OBO формата (fallback)"""
        # Упрощенный парсер OBO
        try:
            with open(mondo_path, 'r', encoding='utf-8') as f:
                current_term = None
                
                for line in f:
                    line = line.strip()
                    
                    if line.startswith('[Term]'):
                        if current_term:
                            # Сохраняем предыдущий термин
                            if 'id' in current_term and 'name' in current_term:
                                mondo_id = current_term['id']
                                if mondo_id.startswith('MONDO:'):
                                    disease = Disease(
                                        id=mondo_id,
                                        name=current_term['name'],
                                        alternative_names=current_term.get('synonyms', []),
                                        genes=[],
                                        source="MONDO",
                                        exact_synonyms=current_term.get('exact_synonyms', []),
                                        related_synonyms=current_term.get('related_synonyms', []),
                                        subsets=current_term.get('subsets', []),
                                        cross_references={}
                                    )
                                    self.diseases[disease.id] = disease
                                    
                                    # Обрабатываем xrefs
                                    for xref in current_term.get('xrefs', []):
                                        if xref.startswith('OMIM:'):
                                            self.omim_to_mondo[xref] = mondo_id
                                            self.mondo_to_omim[mondo_id] = xref
                                            disease.cross_references[xref] = mondo_id
                        
                        current_term = {'synonyms': [], 'exact_synonyms': [], 
                                      'related_synonyms': [], 'xrefs': [], 'subsets': []}
                    
                    elif current_term is not None:
                        if line.startswith('id: '):
                            current_term['id'] = line[4:]
                        elif line.startswith('name: '):
                            current_term['name'] = line[6:]
                        elif line.startswith('synonym: '):
                            # Парсим синонимы с типами
                            match = re.match(r'synonym: "(.*)" (EXACT|RELATED|NARROW|BROAD)', line)
                            if match:
                                syn_text = match.group(1)
                                syn_type = match.group(2)
                                
                                if syn_type == 'EXACT':
                                    current_term['exact_synonyms'].append(syn_text)
                                elif syn_type == 'RELATED':
                                    current_term['related_synonyms'].append(syn_text)
                                
                                current_term['synonyms'].append(syn_text)
                        elif line.startswith('xref: '):
                            current_term['xrefs'].append(line[6:])
                        elif line.startswith('subset: '):
                            current_term['subsets'].append(line[8:])
                            
        except Exception as e:
            logger.error(f"Error loading MONDO OBO: {e}")
            
    def get_disease_by_id(self, disease_id: str) -> Optional[Disease]:
        """Получить заболевание по ID"""
        return self.diseases.get(disease_id)
        
    def get_diseases_by_gene(self, gene: str) -> List[Disease]:
        """Получить заболевания связанные с геном"""
        diseases = []
        gene_upper = gene.upper()
        
        # Прямой поиск в gene_to_diseases
        if gene_upper in self.gene_to_diseases:
            for disease_id in self.gene_to_diseases[gene_upper]:
                if disease_id in self.diseases:
                    diseases.append(self.diseases[disease_id])
                    
        # Также ищем в самих заболеваниях
        for disease in self.diseases.values():
            if gene_upper in [g.upper() for g in disease.genes]:
                if disease not in diseases:
                    diseases.append(disease)
                    
        return diseases
        
    def get_cross_reference(self, disease_id: str) -> Optional[str]:
        """Получить кросс-ссылку между OMIM и MONDO"""
        if disease_id.startswith('OMIM:') and disease_id in self.omim_to_mondo:
            return self.omim_to_mondo[disease_id]
        elif disease_id.startswith('MONDO:') and disease_id in self.mondo_to_omim:
            return self.mondo_to_omim[disease_id]
        return None
    
    def _enrich_diseases_with_genes(self):
        """Обогатить заболевания генами из gene_to_diseases маппинга"""
        logger.info("Enriching diseases with gene information...")
        
        enriched_count = 0
        for gene, disease_ids in self.gene_to_diseases.items():
            for disease_id in disease_ids:
                if disease_id in self.diseases:
                    disease = self.diseases[disease_id]
                    if gene not in disease.genes:
                        disease.genes.append(gene)
                        enriched_count += 1
        
        logger.info(f"Enriched {enriched_count} disease-gene associations")