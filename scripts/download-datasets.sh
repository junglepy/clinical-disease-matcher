#!/bin/bash

# Скрипт для загрузки необходимых датасетов
# Запускать из корня проекта clinical-disease-matcher

set -e

echo "=== Загрузка датасетов для Clinical Disease Matcher ==="

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка что мы в правильной директории
if [ ! -f "api/main.py" ]; then
    echo -e "${RED}Ошибка: Запустите скрипт из корня проекта clinical-disease-matcher${NC}"
    exit 1
fi

# Создание директорий
echo "1. Создание директорий..."
mkdir -p api/datasets/OMIM api/datasets/mondo

# Загрузка MONDO
echo -e "\n2. Загрузка MONDO..."
if [ -f "api/datasets/mondo/mondo.json" ]; then
    echo -e "${YELLOW}MONDO уже загружен. Пропускаем.${NC}"
else
    echo "Загрузка mondo.json..."
    wget -q --show-progress https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.json \
         -O api/datasets/mondo/mondo.json
    echo -e "${GREEN}✓ MONDO загружен${NC}"
fi

# OMIM требует регистрацию
echo -e "\n3. OMIM данные"
if [ -f "api/datasets/OMIM/mimTitles.txt" ] && [ -f "api/datasets/OMIM/genemap2.txt" ]; then
    echo -e "${YELLOW}OMIM файлы уже существуют. Пропускаем.${NC}"
else
    echo -e "${YELLOW}ВНИМАНИЕ: OMIM требует регистрацию для загрузки данных${NC}"
    echo "Для получения OMIM данных:"
    echo "1. Зарегистрируйтесь на https://omim.org/downloads"
    echo "2. Скачайте файлы mimTitles.txt и genemap2.txt"
    echo "3. Поместите их в api/datasets/OMIM/"
    echo ""
    echo "Альтернатива: Если у вас есть путь к существующим файлам, укажите его:"
    read -p "Путь к папке с OMIM файлами (или Enter для пропуска): " omim_path
    
    if [ ! -z "$omim_path" ] && [ -d "$omim_path" ]; then
        if [ -f "$omim_path/mimTitles.txt" ] && [ -f "$omim_path/genemap2.txt" ]; then
            cp "$omim_path/mimTitles.txt" api/datasets/OMIM/
            cp "$omim_path/genemap2.txt" api/datasets/OMIM/
            echo -e "${GREEN}✓ OMIM файлы скопированы${NC}"
        else
            echo -e "${RED}Файлы не найдены в указанной директории${NC}"
        fi
    fi
fi

# Проверка результатов
echo -e "\n=== Проверка датасетов ==="

check_file() {
    if [ -f "$1" ]; then
        size=$(ls -lh "$1" | awk '{print $5}')
        echo -e "${GREEN}✓${NC} $1 (${size})"
        return 0
    else
        echo -e "${RED}✗${NC} $1 - не найден"
        return 1
    fi
}

all_good=true
check_file "api/datasets/OMIM/mimTitles.txt" || all_good=false
check_file "api/datasets/OMIM/genemap2.txt" || all_good=false
check_file "api/datasets/mondo/mondo.json" || all_good=false

if $all_good; then
    echo -e "\n${GREEN}Все датасеты загружены успешно!${NC}"
else
    echo -e "\n${YELLOW}Некоторые датасеты отсутствуют. Проверьте инструкции выше.${NC}"
    exit 1
fi