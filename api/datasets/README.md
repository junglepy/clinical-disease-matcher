# Datasets для Clinical Disease Matcher

Этот каталог содержит данные OMIM и MONDO, необходимые для работы системы.

## Структура каталога

```
api/datasets/
├── OMIM/
│   ├── mimTitles.txt    # Названия заболеваний OMIM
│   └── genemap2.txt     # Генно-фенотипические связи
└── mondo/
    └── mondo.json       # Онтология заболеваний MONDO
```

## Получение данных

### Вариант 1: Автоматическая загрузка (рекомендуется)

```bash
# Из корня проекта clinical-disease-matcher
./scripts/download-datasets.sh
```

### Вариант 2: Ручная загрузка

1. **OMIM данные**:
   - Зарегистрируйтесь на https://omim.org/downloads
   - Скачайте файлы `mimTitles.txt` и `genemap2.txt`
   - Поместите в `api/datasets/OMIM/`

2. **MONDO данные**:
   ```bash
   # Скачать последнюю версию
   wget https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.json -O api/datasets/mondo/mondo.json
   ```

## Проверка данных

После загрузки выполните:
```bash
# Проверить наличие файлов
ls -la api/datasets/OMIM/
ls -la api/datasets/mondo/

# Проверить размеры (примерные)
# mimTitles.txt: ~2.7MB
# genemap2.txt: ~5.8MB  
# mondo.json: ~140MB
```

## Примечание

Файлы данных не включены в репозиторий из-за их размера и лицензионных ограничений. Обязательно загрузите их перед использованием системы.