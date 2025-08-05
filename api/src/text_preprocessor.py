import re
import string
from typing import List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """Препроцессор текста для медицинских терминов"""
    
    def __init__(self):
        # Медицинские аббревиатуры и их расшифровки
        self.medical_abbreviations = {
            'DMD': 'Duchenne muscular dystrophy',
            'BMD': 'Becker muscular dystrophy',
            'SMA': 'spinal muscular atrophy',
            'ALS': 'amyotrophic lateral sclerosis',
            'CMT': 'Charcot-Marie-Tooth',
            'LGMD': 'limb-girdle muscular dystrophy',
            'FSHD': 'facioscapulohumeral dystrophy',
            'DM': 'myotonic dystrophy',
            'CMD': 'congenital muscular dystrophy',
            'EDMD': 'Emery-Dreifuss muscular dystrophy',
            'OPMD': 'oculopharyngeal muscular dystrophy',
            'CF': 'cystic fibrosis',
            'HD': 'Huntington disease',
            'PD': 'Parkinson disease',
            'AD': 'Alzheimer disease',
            'MS': 'multiple sclerosis',
            'MD': 'muscular dystrophy',
            'CP': 'cerebral palsy',
            'DS': 'Down syndrome',
            'FXS': 'fragile X syndrome',
            'PWS': 'Prader-Willi syndrome',
            'AS': 'Angelman syndrome',
            'TSC': 'tuberous sclerosis complex',
            'NF': 'neurofibromatosis',
            'VHL': 'von Hippel-Lindau',
            'MEN': 'multiple endocrine neoplasia',
            'FAP': 'familial adenomatous polyposis',
            'HNPCC': 'hereditary nonpolyposis colorectal cancer',
            'PKD': 'polycystic kidney disease',
            'SCD': 'sickle cell disease',
            'SCID': 'severe combined immunodeficiency',
            'CGD': 'chronic granulomatous disease',
            'XLA': 'X-linked agammaglobulinemia',
            'CVID': 'common variable immunodeficiency',
            'DiGS': 'DiGeorge syndrome',
            'WAS': 'Wiskott-Aldrich syndrome',
            'AT': 'ataxia telangiectasia',
            'FA': 'Fanconi anemia',
            'BS': 'Bloom syndrome',
            'XP': 'xeroderma pigmentosum',
            'ARVC': 'arrhythmogenic right ventricular cardiomyopathy',
            'HCM': 'hypertrophic cardiomyopathy',
            'DCM': 'dilated cardiomyopathy',
            'LQTS': 'long QT syndrome',
            'CPVT': 'catecholaminergic polymorphic ventricular tachycardia',
            'WPW': 'Wolff-Parkinson-White syndrome',
            'MVP': 'mitral valve prolapse',
            'BAV': 'bicuspid aortic valve',
            'PDA': 'patent ductus arteriosus',
            'VSD': 'ventricular septal defect',
            'ASD': 'atrial septal defect',
            'TOF': 'tetralogy of Fallot',
            'TGA': 'transposition of great arteries',
            'HLHS': 'hypoplastic left heart syndrome',
            'OI': 'osteogenesis imperfecta',
            'EDS': 'Ehlers-Danlos syndrome',
            'MFS': 'Marfan syndrome',
            'ACH': 'achondroplasia',
            'OA': 'osteoarthritis',
            'RA': 'rheumatoid arthritis',
            'SLE': 'systemic lupus erythematosus',
            'JIA': 'juvenile idiopathic arthritis',
            'FMF': 'familial Mediterranean fever',
            'CAPS': 'cryopyrin-associated periodic syndromes',
            'TRAPS': 'TNF receptor-associated periodic syndrome',
            'MKD': 'mevalonate kinase deficiency',
            'PFAPA': 'periodic fever, aphthous stomatitis, pharyngitis, adenitis',
            'T1D': 'type 1 diabetes',
            'T2D': 'type 2 diabetes',
            'MODY': 'maturity-onset diabetes of the young',
            'DI': 'diabetes insipidus',
            'CAH': 'congenital adrenal hyperplasia',
            'GHD': 'growth hormone deficiency',
            'PHP': 'pseudohypoparathyroidism',
            'MTC': 'medullary thyroid carcinoma',
            'PTC': 'papillary thyroid carcinoma',
            'IBD': 'inflammatory bowel disease',
            'CD': 'Crohn disease',
            'UC': 'ulcerative colitis',
            'IBS': 'irritable bowel syndrome',
            'GERD': 'gastroesophageal reflux disease',
            'PBC': 'primary biliary cholangitis',
            'PSC': 'primary sclerosing cholangitis',
            'NAFLD': 'non-alcoholic fatty liver disease',
            'NASH': 'non-alcoholic steatohepatitis',
            'HCC': 'hepatocellular carcinoma',
            'CCA': 'cholangiocarcinoma',
            'ALL': 'acute lymphoblastic leukemia',
            'AML': 'acute myeloid leukemia',
            'CLL': 'chronic lymphocytic leukemia',
            'CML': 'chronic myeloid leukemia',
            'MM': 'multiple myeloma',
            'HL': 'Hodgkin lymphoma',
            'NHL': 'non-Hodgkin lymphoma',
            'MDS': 'myelodysplastic syndrome',
            'PV': 'polycythemia vera',
            'ET': 'essential thrombocythemia',
            'PMF': 'primary myelofibrosis',
            'ITP': 'immune thrombocytopenic purpura',
            'TTP': 'thrombotic thrombocytopenic purpura',
            'HUS': 'hemolytic uremic syndrome',
            'DIC': 'disseminated intravascular coagulation',
            'VWD': 'von Willebrand disease',
            'IPF': 'idiopathic pulmonary fibrosis',
            'COPD': 'chronic obstructive pulmonary disease',
            'PAH': 'pulmonary arterial hypertension',
            'LAM': 'lymphangioleiomyomatosis',
            'BPD': 'bronchopulmonary dysplasia',
            'RDS': 'respiratory distress syndrome',
            'ARDS': 'acute respiratory distress syndrome',
            'OSA': 'obstructive sleep apnea',
            'PLMD': 'periodic limb movement disorder',
            'RLS': 'restless legs syndrome',
            'CKD': 'chronic kidney disease',
            'ESRD': 'end-stage renal disease',
            'FSGS': 'focal segmental glomerulosclerosis',
            'IgAN': 'IgA nephropathy',
            'MCD': 'minimal change disease',
            'RPGN': 'rapidly progressive glomerulonephritis',
            'ATN': 'acute tubular necrosis',
            'AKI': 'acute kidney injury',
            'UTI': 'urinary tract infection',
            'BPH': 'benign prostatic hyperplasia',
            'PCOS': 'polycystic ovary syndrome',
            'POF': 'premature ovarian failure',
            'PID': 'pelvic inflammatory disease',
            'HPV': 'human papillomavirus',
            'HSV': 'herpes simplex virus',
            'VZV': 'varicella-zoster virus',
            'EBV': 'Epstein-Barr virus',
            'CMV': 'cytomegalovirus',
            'HIV': 'human immunodeficiency virus',
            'HBV': 'hepatitis B virus',
            'HCV': 'hepatitis C virus',
            'TB': 'tuberculosis',
            'NTM': 'non-tuberculous mycobacteria',
            'MAC': 'Mycobacterium avium complex',
            'PCP': 'Pneumocystis pneumonia',
            'RSV': 'respiratory syncytial virus',
            'ASD': 'autism spectrum disorder',
            'ADHD': 'attention deficit hyperactivity disorder',
            'ID': 'intellectual disability',
            'LD': 'learning disability',
            'MDD': 'major depressive disorder',
            'BD': 'bipolar disorder',
            'SCZ': 'schizophrenia',
            'OCD': 'obsessive-compulsive disorder',
            'PTSD': 'post-traumatic stress disorder',
            'GAD': 'generalized anxiety disorder',
            'PD': 'panic disorder',
            'SAD': 'social anxiety disorder',
            'AN': 'anorexia nervosa',
            'BN': 'bulimia nervosa',
            'BED': 'binge eating disorder',
            'SUD': 'substance use disorder',
            'AUD': 'alcohol use disorder',
            'TBI': 'traumatic brain injury',
            'SCI': 'spinal cord injury',
            'CVA': 'cerebrovascular accident',
            'TIA': 'transient ischemic attack',
            'SAH': 'subarachnoid hemorrhage',
            'SDH': 'subdural hematoma',
            'EDH': 'epidural hematoma',
            'GBM': 'glioblastoma multiforme',
            'LGG': 'low-grade glioma',
            'DIPG': 'diffuse intrinsic pontine glioma'
        }
        
        # Стоп-слова для медицинских текстов
        self.medical_stopwords = {
            'disease', 'disorder', 'syndrome', 'condition', 'illness',
            'patient', 'patients', 'case', 'cases', 'report', 'reports',
            'study', 'studies', 'clinical', 'diagnosis', 'treatment',
            'therapy', 'management', 'prognosis', 'outcome', 'outcomes'
        }
        
    def clean_disease_name(self, text: str) -> str:
        """Очистка названия заболевания от лишних символов"""
        # Удаляем информацию о наследовании в скобках
        text = re.sub(r'\s*\([^)]*\)$', '', text)
        
        # Удаляем числовые коды в конце
        text = re.sub(r'\s*,?\s*\d+$', '', text)
        
        # Удаляем специальные символы в конце
        text = re.sub(r'[;,\s]+$', '', text)
        
        # Нормализуем пробелы
        text = ' '.join(text.split())
        
        return text.strip()
    
    def normalize_gene_symbol(self, gene: str) -> str:
        """Нормализация символа гена"""
        # Убираем пробелы и приводим к верхнему регистру
        gene = gene.strip().upper()
        
        # Удаляем специальные символы кроме дефиса
        gene = re.sub(r'[^A-Z0-9\-]', '', gene)
        
        return gene
    
    def expand_abbreviations(self, text: str) -> str:
        """Расширение медицинских аббревиатур"""
        # Создаем копию текста для изменений
        expanded_text = text
        
        # Ищем аббревиатуры как отдельные слова
        for abbr, full_form in self.medical_abbreviations.items():
            # Паттерн для поиска аббревиатуры как отдельного слова
            pattern = r'\b' + re.escape(abbr) + r'\b'
            expanded_text = re.sub(pattern, full_form, expanded_text, flags=re.IGNORECASE)
            
        return expanded_text
    
    def preprocess(self, text: str, language: str = 'en') -> str:
        """Базовая предобработка текста"""
        # Приводим к нижнему регистру
        text = text.lower()
        
        # Расширяем аббревиатуры
        text = self.expand_abbreviations(text)
        
        # Удаляем пунктуацию кроме дефиса
        text = re.sub(r'[^\w\s\-]', ' ', text)
        
        # Нормализуем пробелы
        text = ' '.join(text.split())
        
        # Удаляем стоп-слова (опционально)
        # words = text.split()
        # words = [w for w in words if w not in self.medical_stopwords]
        # text = ' '.join(words)
        
        return text.strip()
    
    def extract_medical_entities(self, text: str) -> dict:
        """Извлечение медицинских сущностей из текста"""
        entities = {
            'genes': [],
            'abbreviations': [],
            'numbers': []
        }
        
        # Извлекаем гены (слова в верхнем регистре из 2-6 букв/цифр)
        gene_pattern = r'\b[A-Z][A-Z0-9]{1,5}\b'
        genes = re.findall(gene_pattern, text)
        entities['genes'] = list(set(genes))
        
        # Извлекаем известные аббревиатуры
        for abbr in self.medical_abbreviations:
            if re.search(r'\b' + re.escape(abbr) + r'\b', text, re.IGNORECASE):
                entities['abbreviations'].append(abbr)
                
        # Извлекаем числа (могут быть важны для возраста начала и т.д.)
        numbers = re.findall(r'\b\d+\b', text)
        entities['numbers'] = numbers
        
        return entities
    
    def tokenize(self, text: str) -> List[str]:
        """Простая токенизация текста"""
        # Разделяем по пробелам и пунктуации
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def is_gene_symbol(self, text: str) -> bool:
        """Проверка, является ли текст символом гена"""
        # Гены обычно: 2-6 символов, заглавные буквы и цифры
        gene_pattern = r'^[A-Z][A-Z0-9]{1,5}$'
        return bool(re.match(gene_pattern, text.upper()))
    
    def clean_for_search(self, text: str) -> str:
        """Очистка текста для поиска"""
        # Удаляем все специальные символы кроме пробелов и дефисов
        text = re.sub(r'[^\w\s\-]', ' ', text)
        
        # Нормализуем множественные пробелы
        text = ' '.join(text.split())
        
        return text.strip()