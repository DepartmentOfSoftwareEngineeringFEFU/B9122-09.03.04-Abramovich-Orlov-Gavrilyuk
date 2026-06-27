# Инструкция по запуску проекта (для Windows)

## 1. Установка PostgreSQL
Если база данных ещё не установлена:
1. Скачайте PostgreSQL для Windows (например, с [enterprisedb.com](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)).
2. Установите. **Запомните пароль** суперпользователя (обычно `postgres`).
3. Запустите **pgAdmin** (устанавливается вместе с Postgres) или используйте командную строку(psql -U postgres).
4. Создайте новую базу данных с именем `diplom3d`.
   - В pgAdmin: Правый клик по `Databases` -> `Create` -> `Database...` -> Name: `diplom3d` -> Save.
   - В командной строке: create database diplom3d;

## 2. Настройка Backend

1. Перейдите в папку `backend`.
2. Скопируйте файл `.env.example` в новый файл `.env`.
   ```powershell
   copy .env.example .env
   ```
3. Откройте `.env` в блокноте. Найдите строку `DATABASE_URL`.
   Она должна выглядеть вот так:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/diplom3d
   ```
   Если ваш пароль от Postgres отличается от `postgres`, замените второй `postgres` на свой пароль.
   Формат: `...://пользователь:ПАРОЛЬ@хост:порт/имя_базы`

## 3. Установка библиотек и Базы Данных

В терминале (Powershell) в папке `backend`:

1. Создайте виртуальное окружение (если нет):
   ```powershell
   python -m venv venv
   ```
2. Активируйте:
   ```powershell
   .\venv\Scripts\activate
   ```
3. Установите зависимости:
   ```powershell
   pip install -r requirements.txt
   ```
4. **Примените миграции (создание таблиц):**
   ```powershell
   alembic upgrade head
   ```
   *(Если ошибок нет, таблицы созданы).*

5. Создайте администратора (создатся с Логин: admin Пароль: admin):
   ```powershell
   python create_admin.py
   ```

## 4. Запуск

**Backend:**
```powershell
uvicorn main:app --reload
```
(Должен писать: `Uvicorn running on http://127.0.0.1:8000`)

**Frontend:**
Параллельно в соседнем терминале в папке `frontend`:
```powershell
npm install (при первом  запуске)
npm run dev
```

## 5. Решение проблем

- **Ошибка 403 Forbidden при загрузке**: Вы не авторизованы.
  - Решение: Зайдите на сайт, нажмите "Войти", затем "Зарегистрироваться". Создайте нового пользователя.
- **Connection refused (DB)**: Проверьте, запущен ли сервис PostgreSQL (в службах Windows) и правильный ли пароль в `.env`.
