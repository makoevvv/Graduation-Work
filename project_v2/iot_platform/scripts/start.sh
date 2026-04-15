#!/bin/bash

# Скрипт для запуска IoT Platform

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

# Проверка наличия Docker
check_docker() {
    print_info "Проверка наличия Docker..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker не установлен. Пожалуйста, установите Docker перед запуском."
        exit 1
    fi
    print_success "Docker найден: $(docker --version)"
}

# Проверка наличия Docker Compose
check_docker_compose() {
    print_info "Проверка наличия Docker Compose..."
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose не установлен. Пожалуйста, установите Docker Compose v2 перед запуском."
        exit 1
    fi
    print_success "Docker Compose найден: $(docker compose version)"
}

# Проверка наличия .env файла
check_env_file() {
    print_info "Проверка наличия .env файла..."
    if [ ! -f .env ]; then
        print_error "Файл .env не найден. Создайте его на основе .env.example или используйте значения по умолчанию."
        exit 1
    fi
    print_success "Файл .env найден"
}

# Остановка существующих контейнеров
stop_containers() {
    print_info "Остановка существующих контейнеров..."
    docker compose down 2>/dev/null || true
    print_success "Контейнеры остановлены"
}

# Сборка и запуск контейнеров
start_containers() {
    print_info "Сборка и запуск контейнеров..."
    docker compose up --build -d
    print_success "Контейнеры запущены"
}

# Ожидание готовности сервисов
wait_for_services() {
    print_info "Ожидание готовности сервисов..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))
        
        # Проверка PostgreSQL
        if docker compose exec -T postgres pg_isready -U iot_user -d iot_db &> /dev/null; then
            print_success "PostgreSQL готов"
            break
        fi
        
        print_info "Ожидание PostgreSQL... (попытка $attempt/$max_attempts)"
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        print_error "PostgreSQL не запустился за отведенное время"
        exit 1
    fi
    
    # Дополнительное ожидание для других сервисов
    print_info "Ожидание запуска остальных сервисов..."
    sleep 10
}

# Проверка статуса сервисов
check_services_status() {
    print_info "Проверка статуса сервисов..."
    docker compose ps
}

# Вывод информации о доступных сервисах
print_access_info() {
    echo ""
    print_success "=========================================="
    print_success "IoT Platform успешно запущена!"
    print_success "=========================================="
    echo ""
    print_info "Доступные сервисы:"
    echo ""
    echo -e "  ${GREEN}Backend API:${NC}        http://localhost:8000"
    echo -e "  ${GREEN}API Документация:${NC}    http://localhost:8000/docs"
    echo -e "  ${GREEN}BlackBox ML:${NC}        http://localhost:8001"
    echo -e "  ${GREEN}ML API Документация:${NC} http://localhost:8001/docs"
    echo -e "  ${GREEN}Frontend:${NC}           http://localhost:3000"
    echo -e "  ${GREEN}Симулятор:${NC}          http://localhost:5001"
    echo -e "  ${GREEN}PostgreSQL:${NC}         localhost:5432"
    echo ""
    print_info "Полезные команды:"
    echo ""
    echo "  Просмотр логов:          docker compose logs -f"
    echo "  Остановка сервисов:      docker compose down"
    echo "  Перезапуск сервисов:     docker compose restart"
    echo "  Статус сервисов:         docker compose ps"
    echo ""
    print_info "Для проверки работоспособности:"
    echo ""
    echo "  curl http://localhost:8000/health"
    echo "  curl http://localhost:8001/"
    echo ""
}

# Основная функция
main() {
    echo ""
    print_info "=========================================="
    print_info "Запуск IoT Platform"
    print_info "=========================================="
    echo ""
    
    # Переход в директорию скрипта
    cd "$(dirname "$0")"
    
    # Выполнение проверок
    check_docker
    check_docker_compose
    check_env_file
    
    # Остановка существующих контейнеров
    stop_containers
    
    # Запуск контейнеров
    start_containers
    
    # Ожидание готовности сервисов
    wait_for_services
    
    # Проверка статуса
    check_services_status
    
    # Вывод информации о доступе
    print_access_info
}

# Обработка сигналов прерывания
trap 'print_warning "Прерывание выполнения..."; docker compose down; exit 1' INT TERM

# Запуск основной функции
main
