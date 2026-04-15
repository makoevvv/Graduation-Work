#!/bin/bash

# Скрипт для остановки IoT Platform и очистки базы данных
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

# Подтверждение действия
confirm_action() {
    echo ""
    print_warning "ВНИМАНИЕ: Это действие удалит все данные из базы данных!"
    print_warning "Включая пользователей, предприятия, группы, устройства, датчики и показания."
    echo ""
    read -p "Вы уверены, что хотите продолжить? (yes/no): " confirmation
    
    if [ "$confirmation" != "yes" ]; then
        print_info "Операция отменена"
        exit 0
    fi
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

# Удаление volumes с данными
remove_volumes() {
    print_info "Удаление volumes с данными..."
    docker compose down -v
    print_success "Volumes удалены"
}

# Удаление образов (опционально)
remove_images() {
    print_info "Удаление Docker образов..."
    docker compose down -v --rmi all
    print_success "Docker образы удалены"
}

# Очистка неиспользуемых ресурсов
cleanup_system() {
    print_info "Очистка неиспользуемых Docker ресурсов..."
    docker system prune -f
    print_success "Неиспользуемые ресурсы очищены"
}

# Проверка статуса после очистки
check_status() {
    print_info "Проверка статуса..."
    local running_containers=$(docker compose ps -q 2>/dev/null | wc -l | tr -d ' ')
    
    if [ "$running_containers" -eq 0 ]; then
        print_success "Все контейнеры остановлены"
    else
        print_warning "Некоторые контейнеры все еще работают"
        docker compose ps
    fi
    
    # Проверка volumes
    local volumes=$(docker volume ls -q | grep -E "postgres_data|blackbox_models" | wc -l | tr -d ' ')
    if [ "$volumes" -eq 0 ]; then
        print_success "Volumes удалены"
    else
        print_warning "Некоторые volumes все еще существуют"
        docker volume ls | grep -E "postgres_data|blackbox_models" || true
    fi
}

# Основная функция
main() {
    echo ""
    print_info "=========================================="
    print_info "Остановка и очистка IoT Platform"
    print_info "=========================================="
    echo ""
    
    # Переход в директорию скрипта
    cd "$(dirname "$0")"
    
    # Подтверждение действия
    confirm_action
    
    # Выполнение проверок
    check_docker_compose
    
    # Остановка контейнеров
    stop_containers
    
    # Удаление volumes с данными
    remove_volumes
    
    # Очистка неиспользуемых ресурсов
    cleanup_system
    
    # Проверка статуса
    check_status
    
    echo ""
    print_success "=========================================="
    print_success "IoT Platform остановлена и очищена!"
    print_success "=========================================="
    echo ""
    print_info "Удалено:"
    echo "  - Все контейнеры"
    echo "  - Все volumes с данными (postgres_data, blackbox_models)"
    echo "  - Неиспользуемые Docker ресурсы"
    echo ""
    print_info "Для запуска с чистой базой данных используйте: ./start.sh"
    echo ""
}

# Запуск основной функции
main
