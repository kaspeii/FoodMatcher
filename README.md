# FoodMatcher
@FoodMatcher_bot
## Ваш персональный шеф-повар, который знает, что лежит в вашем холодильнике
Перестаньте ломать голову над вопросом "Что приготовить?". Наш сервис анализирует ваши продукты, предпочтения и время, чтобы предложить идеальные рецепты. 
## Описание:
Знакомая ситуация? Холодильник не пустой, но вдохновение на нуле. Вы покупаете продукты, а потом они пропадают. Вы ищете рецепт, но на это уходит полчаса, а для готовки нужно еще 10 ингредиентов, которых нет.

Пора заканчивать с этим! Наш сервис - это интеллектуальный помощник, который превращает Ваши продукты в кулинарные шедевры без лишних хлопот. 
### Как это работает?
 - Внесите продукты в свой цифровой холодильник. Он запомнит их, и Вам не придется делать это заново
 - Настройте Ваши предпочтения
 - Получите персонализированную подборку рецептов - только те блюда, которые вы действительно можете и хотите приготовить

## Ключевые преимущества
 - Готовьте из того, что есть
 - Экономьте время
 - Ешьте по своим правилам
 - Храните все рецепты в одном месте
 - Планируйте с умом
 - Освободите свою голову
Хватит гадать, что приготовить! Добавьте свои первые продукты и начните готовить с удовольствием! 

## Команда проекта
 - Карсанов Тамерлан - TeamLead
 - Суслов Павел - Backend developer
 - Индусов Никита - Backend developer
 - Тряпицына Варвара - MLE
 - Рахимов Эмиль - DevOps



# Быстрый старт

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

[Презентация проекта](https://drive.google.com/file/d/1DAG1da3HlAzqMt-qG5YZ1SfSVDcsSLi_/view?usp=sharing)
