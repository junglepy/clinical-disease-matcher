import json
import logging
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI

from .config import Settings

logger = logging.getLogger(__name__)


class LLMQueryGenerator:
    """Генератор поисковых запросов через LLM для русских диагнозов"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        # Поддержка custom base_url для OpenRouter/Ollama
        client_params = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_params["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**client_params)
        self.model = settings.openai_model
        self.temperature = 0.3  # Низкая температура для консистентности
        self.max_queries = 5  # Максимум запросов для генерации
        
    def _get_system_prompt(self) -> str:
        """Системный промпт для генерации запросов"""
        return """You are a medical terminology expert specializing in translating and expanding Russian disease names to English.

Your task is to generate multiple English search queries for a given Russian disease description.

Guidelines:
1. Provide the most accurate medical translation
2. Include common alternative names and synonyms
3. Include both formal medical terms and commonly used names
4. If abbreviations exist, include both the abbreviation and full form
5. Consider different naming conventions (American vs British English)
6. For genetic conditions, include inheritance patterns if mentioned
7. CRITICAL: Always preserve numbers in disease names (e.g., "24", "26", "type 2", "type 13")

You must respond with a JSON array of search queries.

Examples:

Input: "мышечная дистрофия Дюшенна"
Output: ["Duchenne muscular dystrophy", "DMD", "Duchenne's muscular dystrophy", "Duchenne dystrophy", "pseudohypertrophic muscular dystrophy"]

Input: "Преждевременная недостаточность яичников 24"
Output: ["Premature ovarian failure 24", "POF24", "Premature ovarian insufficiency 24", "POI24", "Premature ovarian failure type 24"]

IMPORTANT: Return ONLY the JSON array, no additional text."""
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def generate_queries(self, russian_text: str, context: Optional[str] = None) -> List[str]:
        """
        Генерация поисковых запросов для русского текста
        
        Args:
            russian_text: Текст диагноза на русском языке
            context: Дополнительный контекст (например, ген или возраст)
            
        Returns:
            Список поисковых запросов на английском
        """
        try:
            # Формируем пользовательский промпт
            user_prompt = f"Disease description in Russian: {russian_text}"
            if context:
                user_prompt += f"\nAdditional context: {context}"
                
            # Запрос к OpenAI
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=500
            )
            
            # Парсим ответ
            content = response.choices[0].message.content
            logger.debug(f"LLM response for query generation: {content}")
            
            # Пробуем распарсить как JSON
            try:
                data = json.loads(content)
                
                # Новый формат с thinking блоком
                if isinstance(data, dict) and 'search_queries' in data:
                    queries = data['search_queries']
                    # Логируем thinking для отладки
                    if 'thinking' in data:
                        logger.debug(f"LLM thinking: {data['thinking']}")
                # Старый формат - просто массив
                elif isinstance(data, list):
                    queries = data
                # Альтернативный формат с ключом queries
                elif isinstance(data, dict) and 'queries' in data:
                    queries = data['queries']
                else:
                    # Если структура неожиданная, берем все массивы строк
                    queries = []
                    for v in data.values():
                        if isinstance(v, list) and all(isinstance(item, str) for item in v):
                            queries = v
                            break
            except json.JSONDecodeError:
                # Если не JSON, пробуем извлечь строки из текста
                queries = self._extract_queries_from_text(content)
                
            # Фильтруем и ограничиваем количество
            queries = [q.strip() for q in queries if q and isinstance(q, str)]
            queries = queries[:self.max_queries]
            
            # Если ничего не получилось, делаем простой перевод
            if not queries:
                logger.warning(f"Failed to generate queries for: {russian_text}")
                queries = [self._simple_translation(russian_text)]
                
            logger.info(f"Generated {len(queries)} queries for '{russian_text}': {queries}")
            return queries
            
        except Exception as e:
            logger.error(f"Error generating queries: {e}")
            # Возвращаем простой перевод как fallback
            return [self._simple_translation(russian_text)]
            
    def _extract_queries_from_text(self, text: str) -> List[str]:
        """Извлечение запросов из неструктурированного текста"""
        # Ищем строки в кавычках
        import re
        queries = re.findall(r'"([^"]+)"', text)
        if not queries:
            # Пробуем найти строки между квадратными скобками
            bracket_content = re.search(r'\[([^\]]+)\]', text)
            if bracket_content:
                # Разделяем по запятым и очищаем
                queries = [q.strip(' "\'') for q in bracket_content.group(1).split(',')]
        return queries
        
    def _simple_translation(self, russian_text: str) -> str:
        """Простой перевод как fallback"""
        # Словарь базовых переводов
        translations = {
            'мышечная дистрофия': 'muscular dystrophy',
            'дюшенна': 'duchenne',
            'беккера': 'becker',
            'синдром': 'syndrome',
            'болезнь': 'disease',
            'дауна': 'down',
            'вильсона': 'wilson',
            'паркинсона': 'parkinson',
            'альцгеймера': 'alzheimer',
            'хантингтона': 'huntington',
            'гоше': 'gaucher',
            'помпе': 'pompe',
            'фабри': 'fabry',
            'ниманна-пика': 'niemann-pick',
            'тея-сакса': 'tay-sachs',
            'краббе': 'krabbe',
            'метахроматическая лейкодистрофия': 'metachromatic leukodystrophy',
            'адренолейкодистрофия': 'adrenoleukodystrophy',
            'муковисцидоз': 'cystic fibrosis',
            'фенилкетонурия': 'phenylketonuria',
            'галактоземия': 'galactosemia',
            'гомоцистинурия': 'homocystinuria',
            'тирозинемия': 'tyrosinemia',
            'кленового сиропа': 'maple syrup urine',
            'глутаровая ацидурия': 'glutaric aciduria',
            'метилмалоновая ацидемия': 'methylmalonic acidemia',
            'пропионовая ацидемия': 'propionic acidemia',
            'изовалериановая ацидемия': 'isovaleric acidemia',
            'дефицит биотинидазы': 'biotinidase deficiency',
            'карнитиновая недостаточность': 'carnitine deficiency',
            'митохондриальная': 'mitochondrial',
            'лизосомная': 'lysosomal',
            'пероксисомная': 'peroxisomal',
            'гликогеноз': 'glycogen storage disease',
            'порфирия': 'porphyria',
            'гемофилия': 'hemophilia',
            'талассемия': 'thalassemia',
            'серповидноклеточная': 'sickle cell',
            'анемия': 'anemia',
            'тромбоцитопения': 'thrombocytopenia',
            'нейтропения': 'neutropenia',
            'иммунодефицит': 'immunodeficiency',
            'аутоиммунный': 'autoimmune',
            'ревматоидный артрит': 'rheumatoid arthritis',
            'системная красная волчанка': 'systemic lupus erythematosus',
            'склеродермия': 'scleroderma',
            'дерматомиозит': 'dermatomyositis',
            'полимиозит': 'polymyositis',
            'васкулит': 'vasculitis',
            'гранулематоз': 'granulomatosis',
            'саркоидоз': 'sarcoidosis',
            'амилоидоз': 'amyloidosis',
            'муковисцидоз': 'cystic fibrosis',
            'бронхиальная астма': 'bronchial asthma',
            'хроническая обструктивная болезнь легких': 'chronic obstructive pulmonary disease',
            'идиопатический легочный фиброз': 'idiopathic pulmonary fibrosis',
            'легочная гипертензия': 'pulmonary hypertension',
            'апноэ сна': 'sleep apnea',
            'нарколепсия': 'narcolepsy',
            'эпилепсия': 'epilepsy',
            'мигрень': 'migraine',
            'рассеянный склероз': 'multiple sclerosis',
            'боковой амиотрофический склероз': 'amyotrophic lateral sclerosis',
            'спинальная мышечная атрофия': 'spinal muscular atrophy',
            'миастения': 'myasthenia gravis',
            'периферическая нейропатия': 'peripheral neuropathy',
            'синдром гийена-барре': 'guillain-barre syndrome',
            'хроническая воспалительная демиелинизирующая полинейропатия': 'chronic inflammatory demyelinating polyneuropathy',
            'наследственная': 'hereditary',
            'врожденная': 'congenital',
            'приобретенная': 'acquired',
            'идиопатическая': 'idiopathic',
            'первичная': 'primary',
            'вторичная': 'secondary',
            'острая': 'acute',
            'хроническая': 'chronic',
            'прогрессирующая': 'progressive',
            'рецидивирующая': 'relapsing',
            'ремиттирующая': 'remitting',
            'злокачественная': 'malignant',
            'доброкачественная': 'benign',
            'метастатическая': 'metastatic',
            'инвазивная': 'invasive',
            'карцинома': 'carcinoma',
            'саркома': 'sarcoma',
            'лимфома': 'lymphoma',
            'лейкемия': 'leukemia',
            'меланома': 'melanoma',
            'глиома': 'glioma',
            'астроцитома': 'astrocytoma',
            'медуллобластома': 'medulloblastoma',
            'нейробластома': 'neuroblastoma',
            'ретинобластома': 'retinoblastoma',
            'гепатобластома': 'hepatoblastoma',
            'нефробластома': 'nephroblastoma',
            'тератома': 'teratoma',
            'хориокарцинома': 'choriocarcinoma',
            'аденома': 'adenoma',
            'папиллома': 'papilloma',
            'фиброма': 'fibroma',
            'липома': 'lipoma',
            'гемангиома': 'hemangioma',
            'невус': 'nevus',
            'кератоз': 'keratosis',
            'псориаз': 'psoriasis',
            'экзема': 'eczema',
            'атопический дерматит': 'atopic dermatitis',
            'себорейный дерматит': 'seborrheic dermatitis',
            'контактный дерматит': 'contact dermatitis',
            'крапивница': 'urticaria',
            'ангионевротический отек': 'angioedema',
            'анафилаксия': 'anaphylaxis',
            'пищевая аллергия': 'food allergy',
            'лекарственная аллергия': 'drug allergy',
            'поллиноз': 'hay fever',
            'бронхиальная астма': 'bronchial asthma',
            'аллергический ринит': 'allergic rhinitis',
            'аллергический конъюнктивит': 'allergic conjunctivitis'
        }
        
        # Простой перевод по словам
        words = russian_text.lower().split()
        translated_words = []
        
        for word in words:
            if word in translations:
                translated_words.append(translations[word])
            else:
                # Проверяем, есть ли слово в составных терминах
                found = False
                for ru_term, en_term in translations.items():
                    if word in ru_term.split():
                        translated_words.append(en_term.split()[ru_term.split().index(word)])
                        found = True
                        break
                if not found:
                    # Оставляем как есть (может быть имя собственное)
                    translated_words.append(word)
                    
        return ' '.join(translated_words)
    
    async def generate_queries_for_symptoms(self, symptoms: List[str], language: str = 'ru') -> List[str]:
        """Генерация запросов для списка симптомов"""
        if language == 'en':
            # Для английского просто возвращаем как есть
            return symptoms
            
        # Для русского генерируем запросы для каждого симптома
        all_queries = []
        for symptom in symptoms[:3]:  # Ограничиваем количество для экономии
            queries = await self.generate_queries(symptom)
            all_queries.extend(queries)
            
        # Убираем дубликаты
        return list(dict.fromkeys(all_queries))[:self.max_queries * 2]