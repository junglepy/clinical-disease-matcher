#!/bin/bash
set -e

echo "🏥 Установка Clinical Matcher CLI..."
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Определяем директории
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLI_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
VENV_DIR="$HOME/.clinical-matcher-venv"

# Функция определения оболочки
detect_shell() {
    if [ -n "$BASH_VERSION" ]; then
        echo "bash"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "zsh"
    else
        # Fallback to checking SHELL variable
        case "$SHELL" in
            */bash) echo "bash" ;;
            */zsh) echo "zsh" ;;
            */fish) echo "fish" ;;
            *) echo "unknown" ;;
        esac
    fi
}

# Функция получения конфигурационного файла
get_shell_config() {
    local shell_type="$1"
    case "$shell_type" in
        bash)
            if [[ "$OSTYPE" == "darwin"* ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        zsh)
            echo "$HOME/.zshrc"
            ;;
        fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Определяем текущую оболочку
CURRENT_SHELL=$(detect_shell)
SHELL_CONFIG=$(get_shell_config "$CURRENT_SHELL")

# Проверяем Python
echo "🔍 Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден!"
    echo "   Установите Python 3.7 или выше"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "   Найден Python $PYTHON_VERSION"

# Проверяем минимальную версию Python
MIN_VERSION="3.7"
if [ "$(printf '%s\n' "$MIN_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$MIN_VERSION" ]; then
    echo "❌ Требуется Python $MIN_VERSION или выше!"
    exit 1
fi

# Создаем виртуальное окружение
echo ""
echo "📦 Создание виртуального окружения..."
if [ -d "$VENV_DIR" ]; then
    echo "   Удаление старого окружения..."
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"
echo "   Виртуальное окружение создано в $VENV_DIR"

# Обновляем pip
echo ""
echo "📥 Обновление pip..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip

# Устанавливаем пакет
echo ""
echo "📥 Установка зависимостей..."
cd "$CLI_DIR"
"$VENV_DIR/bin/pip" install -e .

# Создаем wrapper скрипт
echo ""
echo "🔧 Создание исполняемого файла..."
mkdir -p "$HOME/bin"

cat > "$HOME/bin/clinical-matcher" << 'EOF'
#!/bin/bash
# Wrapper для Clinical Matcher CLI

# Определяем путь к виртуальному окружению
VENV_DIR="$HOME/.clinical-matcher-venv"

# Проверяем, что виртуальное окружение существует
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Виртуальное окружение не найдено!"
    echo "   Запустите скрипт установки заново"
    exit 1
fi

# Запускаем CLI
exec "$VENV_DIR/bin/python" -m clinical_matcher "$@"
EOF

chmod +x "$HOME/bin/clinical-matcher"
echo "   Создан файл $HOME/bin/clinical-matcher"

# Создаем конфигурацию
echo ""
echo "⚙️  Настройка конфигурации..."
mkdir -p "$HOME/.config/clinical-matcher"

if [ ! -f "$HOME/.config/clinical-matcher/config.json" ]; then
    cat > "$HOME/.config/clinical-matcher/config.json" << 'EOF'
{
  "api_url": "http://localhost:8002",
  "max_concurrent": 5,
  "timeout": 60
}
EOF
    echo "   Создана конфигурация по умолчанию"
else
    echo "   Существующая конфигурация сохранена"
fi

# Проверяем PATH
echo ""
if [[ ":$PATH:" == *":$HOME/bin:"* ]]; then
    echo -e "${GREEN}✅ $HOME/bin уже в PATH${NC}"
else
    echo -e "${YELLOW}⚠️  $HOME/bin не найден в PATH${NC}"
    echo ""
    
    # Предлагаем добавить в PATH
    if [ "$CURRENT_SHELL" != "unknown" ] && [ -n "$SHELL_CONFIG" ]; then
        echo -e "${BOLD}Обнаружена оболочка: $CURRENT_SHELL${NC}"
        echo -e "${BOLD}Файл конфигурации: $SHELL_CONFIG${NC}"
        echo ""
        
        # Команда для добавления в PATH в зависимости от оболочки
        if [ "$CURRENT_SHELL" == "fish" ]; then
            PATH_CMD="set -gx PATH \$HOME/bin \$PATH"
        else
            PATH_CMD='export PATH="$HOME/bin:$PATH"'
        fi
        
        echo "Варианты добавления в PATH:"
        echo ""
        echo "1) Автоматически добавить в $SHELL_CONFIG (рекомендуется)"
        echo "2) Добавить вручную"
        echo "3) Пропустить (использовать полный путь)"
        echo ""
        read -p "Выберите вариант [1-3]: " choice
        
        case $choice in
            1)
                # Проверяем, не добавлено ли уже
                if grep -q "\$HOME/bin" "$SHELL_CONFIG" 2>/dev/null; then
                    echo -e "${YELLOW}PATH уже настроен в $SHELL_CONFIG${NC}"
                else
                    echo "" >> "$SHELL_CONFIG"
                    echo "# Clinical Matcher CLI" >> "$SHELL_CONFIG"
                    echo "$PATH_CMD" >> "$SHELL_CONFIG"
                    echo -e "${GREEN}✅ PATH добавлен в $SHELL_CONFIG${NC}"
                    echo -e "${YELLOW}   Перезапустите терминал или выполните:${NC}"
                    echo -e "${BLUE}   source $SHELL_CONFIG${NC}"
                fi
                ;;
            2)
                echo ""
                echo "Добавьте следующую строку в $SHELL_CONFIG:"
                echo -e "${BLUE}$PATH_CMD${NC}"
                echo ""
                echo "Затем перезапустите терминал или выполните:"
                echo -e "${BLUE}source $SHELL_CONFIG${NC}"
                ;;
            3)
                echo ""
                echo -e "${YELLOW}Вы сможете запускать программу через полный путь:${NC}"
                echo -e "${BLUE}$HOME/bin/clinical-matcher${NC}"
                ;;
            *)
                echo -e "${RED}Неверный выбор. Используйте полный путь для запуска.${NC}"
                ;;
        esac
    else
        echo "Добавьте в конфигурационный файл вашей оболочки:"
        echo -e "${BLUE}export PATH=\"\$HOME/bin:\$PATH\"${NC}"
        echo ""
        echo "Или используйте полный путь:"
        echo -e "${BLUE}$HOME/bin/clinical-matcher${NC}"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}✅ Установка завершена!${NC}"
echo ""

# Проверяем, можно ли запустить команду
if command -v clinical-matcher &> /dev/null; then
    echo -e "${GREEN}✅ Команда clinical-matcher доступна${NC}"
    CMD_PREFIX=""
else
    echo -e "${YELLOW}⚠️  Используйте полный путь для запуска:${NC}"
    CMD_PREFIX="$HOME/bin/"
fi

echo ""
echo -e "${BOLD}📘 Использование:${NC}"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher --help${NC}              # Справка"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher configure${NC}           # Настройка API"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher process файл.xlsx${NC}   # Обработка файла"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher test${NC}                # Запуск тестов"
echo ""
echo -e "${BOLD}🔧 Первый шаг - настройте API сервер:${NC}"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher configure --api-url http://your-server:8002${NC}"
echo ""
echo -e "${BOLD}📖 Примеры обработки файлов:${NC}"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher process diagnoses.xlsx${NC}"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher process --output-dir results/ file1.csv file2.xlsx${NC}"
echo -e "  ${BLUE}${CMD_PREFIX}clinical-matcher test-columns data.xlsx${NC}  # Проверить определение столбцов"