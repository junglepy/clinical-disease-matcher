import re
from typing import List, Optional, Tuple, Dict
import logging
from pathlib import Path

from .models import VariantInfo, VariantAnnotation, RegionType

logger = logging.getLogger(__name__)

# Проверяем доступность pyensembl
try:
    from pyensembl import EnsemblRelease
    PYENSEMBL_AVAILABLE = True
except ImportError:
    logger.warning("pyensembl not installed. Using fallback gene coordinates.")
    PYENSEMBL_AVAILABLE = False


class VariantAnnotator:
    """Аннотация генетических вариантов с определением генов и типа региона"""
    
    def __init__(self, ensembl_release: int = 106):
        self.ensembl_release = ensembl_release
        self.ensembl = None
        
        if PYENSEMBL_AVAILABLE:
            try:
                self.ensembl = EnsemblRelease(ensembl_release)
                # Проверяем, загружены ли данные
                if not self.ensembl.gtf_path_or_url_exists():
                    logger.info(f"Downloading Ensembl release {ensembl_release} data...")
                    self.ensembl.download()
                    self.ensembl.index()
                logger.info(f"Using Ensembl release {ensembl_release}")
            except Exception as e:
                logger.error(f"Failed to initialize Ensembl: {e}")
                self.ensembl = None
        
        # Fallback координаты для основных генов (GRCh38)
        self.fallback_gene_coords = {
            "DMD": {"chr": "X", "start": 31137344, "end": 33229673, "strand": "-"},
            "F8": {"chr": "X", "start": 154250998, "end": 154426786, "strand": "+"},
            "F9": {"chr": "X", "start": 138612889, "end": 138643668, "strand": "+"},
            "BRCA1": {"chr": "17", "start": 43044294, "end": 43125483, "strand": "-"},
            "BRCA2": {"chr": "13", "start": 32315507, "end": 32400266, "strand": "+"},
            "APP": {"chr": "21", "start": 25880253, "end": 26170538, "strand": "-"},
            "CFTR": {"chr": "7", "start": 117480095, "end": 117667689, "strand": "+"},
            "HBB": {"chr": "11", "start": 5225464, "end": 5227071, "strand": "-"},
            "PAH": {"chr": "12", "start": 102958306, "end": 103087319, "strand": "+"},
            "FBN1": {"chr": "15", "start": 48408313, "end": 48645708, "strand": "+"},
            "NF1": {"chr": "17", "start": 31094927, "end": 31377677, "strand": "+"},
            "COL3A1": {"chr": "2", "start": 188974372, "end": 189012746, "strand": "-"},
            "TP53": {"chr": "17", "start": 7668402, "end": 7687550, "strand": "-"},
            "MLH1": {"chr": "3", "start": 36993365, "end": 37050845, "strand": "+"},
            "MSH2": {"chr": "2", "start": 47403067, "end": 47483140, "strand": "+"},
            "APC": {"chr": "5", "start": 112707498, "end": 112846239, "strand": "+"},
            "PTEN": {"chr": "10", "start": 87863113, "end": 87971930, "strand": "+"},
            "RB1": {"chr": "13", "start": 48303747, "end": 48481890, "strand": "+"},
            "VHL": {"chr": "3", "start": 10141722, "end": 10153668, "strand": "-"},
            "SMN1": {"chr": "5", "start": 70924941, "end": 70953015, "strand": "-"}
        }
        
    def parse_variant(self, variant_str: str) -> Optional[VariantInfo]:
        """
        Парсинг координат вариантов в разных форматах:
        - chr1:12345678-A>G или chrX:154250998-C>T
        - 1:12345678:A:G или X:154250998:C:G
        - chr1:g.12345678A>G
        """
        if not variant_str:
            return None
            
        variant_str = variant_str.strip()
        
        # Паттерны для разных форматов
        patterns = [
            # chr1:12345678-A>G или X:154250998-C>T
            (r'^(chr)?([0-9XY]+):(\d+)[-_]([ACGT])>([ACGT])$', [1, 2, 3, 4]),
            # 1:12345678:A:G
            (r'^(chr)?([0-9XY]+):(\d+):([ACGT]):([ACGT])$', [1, 2, 3, 4]),
            # chr1:g.12345678A>G
            (r'^(chr)?([0-9XY]+):g\.(\d+)([ACGT])>([ACGT])$', [1, 2, 3, 4]),
            # Более гибкий паттерн для разных разделителей
            (r'^(chr)?([0-9XY]+)[:_](\d+)[:_\-]([ACGT])[>:/]([ACGT])$', [1, 2, 3, 4])
        ]
        
        for pattern, indices in patterns:
            match = re.match(pattern, variant_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                chr_num = groups[indices[0]].upper() if groups[indices[0]] else groups[indices[1]].upper()
                
                # Нормализуем хромосому
                if not chr_num.startswith('CHR'):
                    chr_num = f"{chr_num}"  # Для pyensembl нужно без префикса chr
                else:
                    chr_num = chr_num[3:]  # Убираем префикс chr
                
                variant = VariantInfo(
                    chromosome=chr_num,
                    position=int(groups[indices[2]]),
                    reference=groups[indices[3]].upper(),
                    alternative=groups[indices[4]].upper()
                )
                
                logger.debug(f"Parsed variant: {variant.to_string()}")
                return variant
        
        logger.warning(f"Could not parse variant: {variant_str}")
        return None
        
    def annotate_variant(self, variant: VariantInfo, window: int = 5000) -> VariantAnnotation:
        """Аннотировать вариант с определением генов и типа региона"""
        annotation = VariantAnnotation(variant=variant)
        
        if self.ensembl:
            # Используем pyensembl для точной аннотации
            annotation = self._annotate_with_ensembl(variant, window)
        else:
            # Fallback на предопределенные координаты
            annotation = self._annotate_with_fallback(variant, window)
            
        return annotation
        
    def _annotate_with_ensembl(self, variant: VariantInfo, window: int) -> VariantAnnotation:
        """Аннотация с использованием pyensembl"""
        annotation = VariantAnnotation(variant=variant)
        
        try:
            # Получаем гены в точной позиции
            genes_at_position = self.ensembl.genes_at_locus(
                contig=variant.chromosome,
                position=variant.position
            )
            
            if genes_at_position:
                # Вариант попадает в ген
                gene = genes_at_position[0]  # Берем первый ген
                annotation.genes = [gene.gene_name]
                annotation.distance_to_gene = 0
                
                # Определяем тип региона
                annotation.region_type = self._determine_region_type_ensembl(variant, gene)
                
            else:
                # Ищем ближайшие гены в окне
                nearby_genes = self.ensembl.genes_overlapping_interval(
                    contig=variant.chromosome,
                    start=max(1, variant.position - window),
                    end=variant.position + window
                )
                
                if nearby_genes:
                    # Сортируем по расстоянию
                    gene_distances = []
                    for gene in nearby_genes:
                        if variant.position < gene.start:
                            distance = gene.start - variant.position
                        elif variant.position > gene.end:
                            distance = variant.position - gene.end
                        else:
                            distance = 0
                        gene_distances.append((gene, distance))
                    
                    gene_distances.sort(key=lambda x: x[1])
                    closest_gene, min_distance = gene_distances[0]
                    
                    annotation.genes = [closest_gene.gene_name]
                    annotation.distance_to_gene = min_distance
                    
                    # Определяем тип региона для ближайшего гена
                    if min_distance <= 2000:  # В пределах промоторной области
                        if variant.position < closest_gene.start:
                            annotation.region_type = RegionType.PROMOTER
                        else:
                            annotation.region_type = RegionType.INTERGENIC
                    else:
                        annotation.region_type = RegionType.INTERGENIC
                        
        except Exception as e:
            logger.error(f"Error in Ensembl annotation: {e}")
            # Fallback на базовую аннотацию
            return self._annotate_with_fallback(variant, window)
            
        return annotation
        
    def _determine_region_type_ensembl(self, variant: VariantInfo, gene) -> RegionType:
        """Определить тип региона внутри гена используя Ensembl"""
        try:
            # Получаем транскрипты гена
            transcripts = self.ensembl.transcripts_by_gene_id(gene.gene_id)
            
            for transcript in transcripts:
                # Проверяем экзоны
                for exon in transcript.exons:
                    if exon.start <= variant.position <= exon.end:
                        # Проверяем, кодирующий ли это экзон
                        if transcript.contains_start_codon and transcript.contains_stop_codon:
                            if (transcript.start_codon_positions[0] <= variant.position <= 
                                transcript.stop_codon_positions[-1]):
                                return RegionType.EXONIC
                        else:
                            return RegionType.EXONIC
                
                # Если не в экзоне, значит в интроне
                if transcript.start <= variant.position <= transcript.end:
                    return RegionType.INTRONIC
                    
                # Проверяем UTR регионы
                if hasattr(transcript, 'five_prime_utr_start'):
                    if (transcript.five_prime_utr_start <= variant.position < 
                        transcript.start_codon_positions[0]):
                        return RegionType.UTR
                        
                if hasattr(transcript, 'three_prime_utr_end'):
                    if (transcript.stop_codon_positions[-1] < variant.position <= 
                        transcript.three_prime_utr_end):
                        return RegionType.UTR
                        
        except Exception as e:
            logger.debug(f"Could not determine exact region type: {e}")
            
        return RegionType.UNKNOWN
        
    def _annotate_with_fallback(self, variant: VariantInfo, window: int) -> VariantAnnotation:
        """Fallback аннотация используя предопределенные координаты"""
        annotation = VariantAnnotation(variant=variant)
        
        # Нормализуем хромосому для сравнения
        chr_normalized = variant.chromosome.replace('chr', '').replace('CHR', '')
        
        # Ищем гены в позиции или рядом
        genes_found = []
        min_distance = float('inf')
        
        for gene_name, coords in self.fallback_gene_coords.items():
            gene_chr = coords["chr"].replace('chr', '').replace('CHR', '')
            
            if gene_chr == chr_normalized:
                # Проверяем попадание в ген
                if coords["start"] <= variant.position <= coords["end"]:
                    genes_found.append((gene_name, 0))
                    min_distance = 0
                else:
                    # Вычисляем расстояние до гена
                    if variant.position < coords["start"]:
                        distance = coords["start"] - variant.position
                    else:
                        distance = variant.position - coords["end"]
                        
                    if distance <= window:
                        genes_found.append((gene_name, distance))
                        min_distance = min(min_distance, distance)
        
        if genes_found:
            # Сортируем по расстоянию
            genes_found.sort(key=lambda x: x[1])
            
            # Берем ближайший ген
            closest_gene, distance = genes_found[0]
            annotation.genes = [closest_gene]
            annotation.distance_to_gene = distance
            
            # Определяем тип региона
            if distance == 0:
                # Грубая оценка - считаем что попадание в ген = экзон
                # В реальности нужна более точная информация
                annotation.region_type = RegionType.EXONIC
            elif distance <= 2000:
                gene_coords = self.fallback_gene_coords[closest_gene]
                if variant.position < gene_coords["start"]:
                    annotation.region_type = RegionType.PROMOTER
                else:
                    annotation.region_type = RegionType.INTERGENIC
            else:
                annotation.region_type = RegionType.INTERGENIC
        else:
            annotation.region_type = RegionType.INTERGENIC
            
        return annotation
        
    def get_genes_in_region(self, chromosome: str, position: int, window: int = 5000) -> List[Tuple[str, int]]:
        """Получить все гены в заданном регионе с расстояниями"""
        genes_with_distances = []
        
        if self.ensembl:
            try:
                # Нормализуем хромосому для Ensembl (без префикса chr)
                chr_normalized = chromosome.replace('chr', '').replace('CHR', '')
                
                genes = self.ensembl.genes_overlapping_interval(
                    contig=chr_normalized,
                    start=max(1, position - window),
                    end=position + window
                )
                
                for gene in genes:
                    if position < gene.start:
                        distance = gene.start - position
                    elif position > gene.end:
                        distance = position - gene.end
                    else:
                        distance = 0
                    genes_with_distances.append((gene.gene_name, distance))
                    
            except Exception as e:
                logger.error(f"Error getting genes in region: {e}")
                # Fallback на предопределенные координаты
                return self._get_genes_in_region_fallback(chromosome, position, window)
        else:
            return self._get_genes_in_region_fallback(chromosome, position, window)
            
        return sorted(genes_with_distances, key=lambda x: x[1])
        
    def _get_genes_in_region_fallback(self, chromosome: str, position: int, window: int) -> List[Tuple[str, int]]:
        """Fallback метод для получения генов в регионе"""
        genes_with_distances = []
        chr_normalized = chromosome.replace('chr', '').replace('CHR', '')
        
        for gene_name, coords in self.fallback_gene_coords.items():
            gene_chr = coords["chr"].replace('chr', '').replace('CHR', '')
            
            if gene_chr == chr_normalized:
                if coords["start"] <= position <= coords["end"]:
                    distance = 0
                elif position < coords["start"]:
                    distance = coords["start"] - position
                else:
                    distance = position - coords["end"]
                    
                if distance <= window:
                    genes_with_distances.append((gene_name, distance))
                    
        return sorted(genes_with_distances, key=lambda x: x[1])