# FoodMatcher
## Описание:
Telegram-бот для удобного подбора рецептов на основе продуктов, которые есть у пользователя. Бот позволяет добавлять продукты в свой виртуальный холодильник. Система запоминает добавленные продукты и подбирает рецепты из базы данных, учитывая их наличие.
Имя - FoodMatcher
ID - @test43267724bot (поменять на нормальное?)

## Быстрый старт

### 1. Подготовка окружения
- Установите зависимости: `pip install -r requirements.txt`
- Создайте файл `.env` в корне проекта (если его нет) и заполните токены:
  ```
  TELEGRAM_TOKEN=...
  GROQ_API_KEY=...
  VOSK_MODEL_PATH=/home/USERNAME/FoodMatcher/vosk-model-small-ru-0.22
  DATABASE_URL=postgresql://foodmatcher:1234@127.0.0.1:5432/foodmatcher
  ```
  Замените `USERNAME` и остальные значения на свои.

### 2. Развёртывание базы данных
```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE foodmatcher LOGIN PASSWORD '1234';
CREATE DATABASE foodmatcher OWNER foodmatcher;
GRANT ALL PRIVILEGES ON DATABASE foodmatcher TO foodmatcher;
\c foodmatcher
GRANT USAGE ON SCHEMA public TO foodmatcher;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO foodmatcher;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO foodmatcher;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO foodmatcher;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO foodmatcher;
SQL
```

После выдачи прав загрузите структуру и данные:
```bash
psql -U foodmatcher -h 127.0.0.1 -d foodmatcher -f foodmatcher.sql
```

### 3. Установка модели Vosk (голосовой ввод)
```bash
cd /home/USERNAME/FoodMatcher
wget https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
unzip vosk-model-small-ru-0.22.zip
rm vosk-model-small-ru-0.22.zip
```
Пропишите абсолютный путь к распакованной модели в переменной `VOSK_MODEL_PATH`.

### 4. Запуск бота
```bash
python main.py
```

## TODO Бэк:
1) Нормальный Парсер ввода продуктов
2) Учет испорченности продуктов
3) Вывод всех картинок
4) Починить голосовой ввод?