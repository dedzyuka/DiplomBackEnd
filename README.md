# RabbitMQ Test - Messenger API

Современный мессенджер с REST API и WebSocket поддержкой, построенный на FastAPI, PostgreSQL и Redis.

## 🚀 Возможности

- **REST API** для управления пользователями, чатами, сообщениями и контактами
- **WebSocket** для real-time обмена сообщениями
- **PostgreSQL** с партиционированием для масштабируемости
- **Redis** для кэширования и управления сессиями
- **Аутентификация** через JWT токены
- **Партиционирование** таблиц по дате и хешу для оптимизации производительности
- **Row-Level Security** для безопасности данных

## 📋 Требования

- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- RabbitMQ (опционально)

## 🛠 Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd RabitmqTest
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или
.venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей

```bash
pip install -e .
```

Или используя uv (рекомендуется):

```bash
uv pip install -e .
```

### 4. Настройка базы данных

#### Создание базы данных PostgreSQL

```bash
createdb messenger_db
```

#### Настройка подключения

Отредактируйте файл `app/grpc_api_Rest/database.py` и укажите параметры подключения:

```python
DATABASE_URL = "postgresql+asyncpg://user:password@localhost/messenger_db"
```

Также обновите `alembic.ini`:

```ini
sqlalchemy.url = postgresql+asyncpg://user:password@localhost/messenger_db
```

#### Применение миграций

```bash
# Создание начальной миграции (если нужно)
alembic revision --autogenerate -m "Initial schema"

# Применение миграций
alembic upgrade head
```

Или используйте готовый SQL скрипт из `bd.txt`:

```bash
psql -U user -d messenger_db -f bd.txt
```

### 5. Настройка Redis

Убедитесь, что Redis запущен:

```bash
redis-server
```

По умолчанию Redis доступен на `localhost:6379`. При необходимости измените настройки в `app/websocketSide/config.py`.

### 6. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/messenger_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Application
DEBUG=True
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

## 🏃 Запуск

### REST API сервер

```bash
cd app/grpc_api_Rest
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API будет доступен по адресу: http://localhost:8000

Документация API (Swagger): http://localhost:8000/docs

### WebSocket сервер

```bash
cd app/websocketSide
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

WebSocket будет доступен по адресу: ws://localhost:8001/ws/chat/{user_id}

## 📁 Структура проекта

```
RabitmqTest/
├── alembic/                    # Миграции базы данных
│   ├── versions/              # Файлы миграций
│   ├── env.py                 # Конфигурация Alembic
│   └── script.py.mako         # Шаблон миграций
├── app/
│   ├── grpc_api_Rest/         # REST API приложение
│   │   ├── api/
│   │   │   └── endpoints/     # API эндпоинты
│   │   │       ├── auth.py    # Аутентификация
│   │   │       ├── users.py   # Пользователи
│   │   │       ├── chats.py   # Чаты
│   │   │       ├── messages.py # Сообщения
│   │   │       ├── contacts.py # Контакты
│   │   │       └── admin.py   # Админ панель
│   │   ├── core/
│   │   │   ├── config.py      # Конфигурация
│   │   │   └── security.py   # Безопасность (JWT)
│   │   ├── crud/              # CRUD операции
│   │   ├── models.py          # SQLAlchemy модели
│   │   ├── schemas.py         # Pydantic схемы
│   │   ├── enums.py           # Перечисления
│   │   ├── database.py        # Подключение к БД
│   │   ├── dependencies.py    # Зависимости FastAPI
│   │   └── main.py            # Точка входа REST API
│   └── websocketSide/         # WebSocket сервер
│       ├── main.py            # Точка входа WebSocket
│       ├── router.py          # WebSocket роуты
│       ├── manager.py         # Менеджер соединений
│       ├── redis_c.py         # Redis клиент
│       └── config.py          # Конфигурация
├── bd.txt                     # SQL скрипт создания БД
├── alembic.ini                # Конфигурация Alembic
├── pyproject.toml             # Зависимости проекта
└── README.md                  # Этот файл
```

## 🗄 База данных

### Основные таблицы

- **users** - Пользователи системы
- **chats** - Чаты (приватные, группы, каналы)
- **chat_members** - Участники чатов
- **messages** - Сообщения (партиционирована по дате)
- **message_statuses** - Статусы сообщений (партиционирована по хешу)
- **attachments** - Вложения к сообщениям
- **reactions** - Реакции на сообщения
- **mentions** - Упоминания пользователей
- **contacts** - Контакты пользователей
- **privacy_settings** - Настройки приватности
- **emoji** - Справочник emoji
- **session_events** - События сессий (партиционирована по дате)
- **audit_logs** - Логи безопасности (партиционирована по дате)

### Партиционирование

Для оптимизации производительности используются партиции:

- **messages** - по месяцам (RANGE)
- **message_statuses** - по хешу user_id (HASH, 8 партиций)
- **session_events** - по месяцам (RANGE)
- **audit_logs** - по месяцам (RANGE)

### Индексы

Созданы индексы для оптимизации запросов:
- По email, phone, nick_name для пользователей
- По chat_id и created_at для сообщений
- GIN индексы для полнотекстового поиска и JSON полей
- Триграммные индексы для поиска по именам

## 🔐 Аутентификация

API использует JWT токены для аутентификации:

1. **Регистрация**: `POST /auth/register`
2. **Вход**: `POST /auth/login`
3. **Обновление токена**: `POST /auth/refresh`
4. **Выход**: `POST /auth/logout`

Токены передаются в заголовке `Authorization: Bearer <token>`

## 📡 API Endpoints

### Аутентификация
- `POST /auth/register` - Регистрация пользователя
- `POST /auth/login` - Вход в систему
- `POST /auth/refresh` - Обновление токена
- `POST /auth/logout` - Выход из системы
- `GET /auth/sessions` - Получить активные сессии

### Пользователи
- `GET /users/me` - Получить текущего пользователя
- `PUT /users/me` - Обновить профиль
- `GET /users/{user_id}` - Получить пользователя по ID
- `GET /users/` - Поиск пользователей
- `DELETE /users/me` - Удалить аккаунт

### Чаты
- `GET /chats/` - Список чатов пользователя
- `POST /chats/` - Создать чат
- `GET /chats/{chat_id}` - Получить чат
- `PUT /chats/{chat_id}` - Обновить чат
- `DELETE /chats/{chat_id}` - Удалить чат
- `GET /chats/{chat_id}/members` - Участники чата
- `POST /chats/{chat_id}/members` - Добавить участника
- `DELETE /chats/{chat_id}/members/{user_id}` - Удалить участника
- `PATCH /chats/{chat_id}/members/{user_id}` - Изменить роль участника

### Сообщения
- `GET /chats/{chat_id}/messages/` - Получить сообщения чата
- `POST /chats/{chat_id}/messages/` - Отправить сообщение
- `GET /chats/{chat_id}/messages/{message_id}` - Получить сообщение
- `PUT /chats/{chat_id}/messages/{message_id}` - Редактировать сообщение
- `DELETE /chats/{chat_id}/messages/{message_id}` - Удалить сообщение
- `POST /chats/{chat_id}/messages/{message_id}/reactions` - Добавить реакцию
- `DELETE /chats/{chat_id}/messages/{message_id}/reactions` - Удалить реакцию

### Контакты
- `GET /contacts/` - Список контактов
- `GET /contacts/requests` - Входящие запросы
- `POST /contacts/` - Добавить контакт
- `PUT /contacts/{contact_user_id}` - Обновить статус контакта
- `DELETE /contacts/{contact_user_id}` - Удалить контакт

### Админ
- `GET /admin/users` - Список всех пользователей
- `POST /admin/users/{user_id}/block` - Заблокировать пользователя
- `GET /admin/audit-logs` - Логи безопасности

## 🔌 WebSocket

### Подключение

```
ws://localhost:8001/ws/chat/{user_id}
```

### Формат сообщений

**Отправка сообщения:**
```json
{
  "chat_id": "uuid",
  "sender_id": "uuid",
  "content": "Текст сообщения",
  "type": "text",
  "metadata": {}
}
```

**Получение сообщения:**
```json
{
  "message_id": 123,
  "chat_id": "uuid",
  "sender_id": "uuid",
  "content": "Текст сообщения",
  "type": "text",
  "metadata": {},
  "created_at": "2026-02-18T12:00:00Z"
}
```

## 🧪 Тестирование

### Запуск тестов

```bash
pytest
```

### Проверка API через Swagger

Откройте http://localhost:8000/docs в браузере для интерактивной документации API.

## 📝 Миграции

### Создание новой миграции

```bash
alembic revision --autogenerate -m "Описание изменений"
```

### Применение миграций

```bash
alembic upgrade head
```

### Откат миграции

```bash
alembic downgrade -1
```

## 🔧 Разработка

### Добавление нового эндпоинта

1. Создайте файл в `app/grpc_api_Rest/api/endpoints/`
2. Определите роутер с эндпоинтами
3. Подключите роутер в `app/grpc_api_Rest/main.py`

### Добавление новой модели

1. Добавьте модель в `app/grpc_api_Rest/models.py`
2. Создайте Pydantic схемы в `app/grpc_api_Rest/schemas.py`
3. Создайте CRUD операции в `app/grpc_api_Rest/crud/`
4. Создайте миграцию: `alembic revision --autogenerate -m "Add new model"`

## 🐛 Отладка

### Логи

Логи выводятся в консоль. Для production рекомендуется настроить логирование в файл.

### Проверка подключения к БД

```bash
psql -U user -d messenger_db -c "SELECT COUNT(*) FROM users;"
```

### Проверка Redis

```bash
redis-cli ping
```

## 📄 Лицензия

[Укажите лицензию]

## 👥 Авторы

[Укажите авторов]

## 🤝 Вклад

[Инструкции по внесению вклада]

## 📞 Поддержка

[Контактная информация]
