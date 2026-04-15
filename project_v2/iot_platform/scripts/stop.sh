#!/bin/bash

# Скрипт для остановки IoT Platform
# ВКР Макоев Р.А., группа БФИ2203
# Финансовый университет при Правительстве Российской Федерации, 2026

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода цветных сообщений
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка наличия Docker Compose
check_docker_compose() {
    print_info "Проверка наличия Docker Compose..."
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose не установлен."
        exit 1
    fi
    print_success "Docker Compose найден"
}

# Остановка контейнеров
stop_containers() {
    print_info "Остановка контейнеров..."
    docker compose down
    print_success "Контейнеры остановлены"
}

# Проверка статуса после остановки
check_status() {
    print_info "Проверка статуса контейнеров..."
    local running_containers=$(docker compose ps -q 2>/dev/null | wc -l | tr -d ' ')
    
    if [ "$running_containers" -eq 0 ]; then
        print_success "Все контейнеры остановлены"
    else
        print_warning "Некоторые контейнеры все еще работают"
        docker compose ps
    fi
}

# Основная функция
main() {
    echo ""
    print_info "=========================================="
    print_info "Остановка IoT Platform"
    print_info "=========================================="
    echo ""
    
    # Переход в директорию скрипта
    cd "$(dirname "$0")"
    
    # Выполнение проверок
    check_docker_compose
    
    # Остановка контейнеров
    stop_containers
    
    # Проверка статуса
    check_status
    
    echo ""
    print_success "=========================================="
    print_success "IoT Platform успешно остановлена!"
    print_success "=========================================="
    echo ""
    print_info "Для перезапуска используйте: ./start.sh"
    echo ""
}

# Запуск основной функции
main
