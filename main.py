import logging
import os
import re
import json
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from dotenv import load_dotenv

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                    ReplyKeyboardMarkup, ReplyKeyboardRemove, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ConversationHandler, ContextTypes, MessageHandler, filters)

from vosk import Model, KaldiRecognizer
import wave
from pydub import AudioSegment
from groq import AsyncGroq

class SetEncoder(json.JSONEncoder):
    """
    Кастомный JSON-кодировщик, который преобразует множества (set) в списки (list).
    """
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

# --- НАСТРОЙКА И КОНСТАНТЫ ---

# Загрузка токена с поддержкой .env файла
load_dotenv() 
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 

# Инициализация клиента Groq
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Логгинг
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импорт модуля базы данных
import db

# Глобальные кэши для справочников
ALL_PRODUCTS_CACHE = set()
ALL_EQUIPMENT_CACHE = set()

# Константа для удаления клавиатуры
REMOVE_KEYBOARD = ReplyKeyboardRemove()

# Глобальная переменная для модели Vosk
VOSK_MODEL = None

# Состояния для ConversationHandler'ов
(
    MANAGE_STORAGE, ADD_PRODUCTS, REMOVE_PRODUCTS,
    MANAGE_EQUIPMENT, ADD_EQUIPMENT, REMOVE_EQUIPMENT,
    CHOOSE_RECIPE_TYPE, FILTER_BY_TIME
) = range(8)

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ГОЛОСОВЫМИ СООБЩЕНИЯМИ ---

def init_vosk_model():
    global VOSK_MODEL
    
    if VOSK_MODEL is not None:
        return True
    
    model_path = os.getenv("VOSK_MODEL_PATH", "vosk-model-small-ru-0.22")
    
    try:
        VOSK_MODEL = Model(model_path)
        logger.info(f"Модель загружена из {model_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при загрузке модели: {e}")
        return False

async def download_voice_file(voice_file, bot) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as tmp_file:
        file_path = tmp_file.name
        file = await bot.get_file(voice_file.file_id)
        await file.download_to_drive(file_path)
        return file_path

def convert_ogg_to_wav(ogg_path: str) -> str:
    wav_path = ogg_path.replace('.ogg', '.wav')
    audio = AudioSegment.from_ogg(ogg_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    audio.export(wav_path, format="wav")
    os.unlink(ogg_path)
    return wav_path

def recognize_speech(audio_path: str) -> str:
    try:
        wf = wave.open(audio_path, "rb")
        
        if wf.getnchannels() != 1 or wf.getcomptype() != "NONE":
            wf.close()
            return None
        
        rec = KaldiRecognizer(VOSK_MODEL, wf.getframerate())
        rec.SetWords(True)
        
        text_parts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result and result['text']:
                    text_parts.append(result['text'])
        
        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result and final_result['text']:
            text_parts.append(final_result['text'])
        
        wf.close()
        recognized_text = ' '.join(text_parts).strip()
        return recognized_text if recognized_text else None
        
    except Exception as e:
        logger.error(f"Ошибка при распознавании речи: {e}")
        return None
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)

async def process_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    voice = update.message.voice
    if not voice:
        return None
    
    try:
        ogg_path = await download_voice_file(voice, context.bot)
        wav_path = convert_ogg_to_wav(ogg_path)
        text = recognize_speech(wav_path)
        
        if text:
            logger.info(f"Распознано из голосового сообщения: {text}")
            return text
        else:
            await update.message.reply_text("Не удалось распознать речь. Попробуйте еще раз или введите текст.")
            return None
            
    except Exception as e:
        await update.message.reply_text("Произошла ошибка при обработке голосового сообщения. Попробуйте ввести текст.")
        return None

# --- УНИВЕРСАЛЬНЫЕ ФУНКЦИИ И ГЛАВНОЕ МЕНЮ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    УНИВЕРСАЛЬНАЯ точка входа.
    Приветствует, принудительно завершает любой диалог и показывает главное меню.
    """
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} ({user.id}) запустил /start")
    db.ensure_user_exists(user.id, user.first_name)
    
    reply_keyboard = [
        ["Мой холодильник", "Мое оборудование"],
        ["Подобрать рецепт"],
        ["Помощь"],
    ]
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}! Я ваш кулинарный помощник. Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    УНИВЕРСАЛЬНАЯ точка сброса.
    Принудительно завершает любой диалог и показывает главное меню.
    """
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} ({user.id}) запустил /menu")
    db.ensure_user_exists(user.id, user.first_name)
    
    reply_keyboard = [
        ["Мой холодильник", "Мое оборудование"],
        ["Подобрать рецепт"],
        ["Помощь"],
    ]
    
    await update.message.reply_text(
        f"Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог и возвращает в главное меню."""
    await main_menu(update, context)
    return ConversationHandler.END

async def back_to_main_menu_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие inline-кнопки "Назад в меню".
    Редактирует сообщение, убирая кнопки.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Вы вернулись в главное меню.")

# --- УПРАВЛЕНИЕ ОБОРУДОВАНИЕМ ---

async def manage_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню управления оборудованием."""
    reply_keyboard = [
        ["Посмотреть оборудование"],
        ["Добавить оборудование", "Удалить оборудование"],
        ["Назад в меню"],
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return MANAGE_EQUIPMENT

async def view_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр списка оборудования."""
    user_id = update.message.from_user.id
    equipment = db.get_user_equipment(user_id)
    if equipment:
        await update.message.reply_text("Ваше оборудование:\n- " + "\n- ".join(sorted(list(equipment))))
    else:
        await update.message.reply_text("У вас не добавлено оборудование.")
    return MANAGE_EQUIPMENT

async def add_equipment_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите оборудование, которое хотите добавить, через запятую (или отправьте голосовое сообщение):",
        reply_markup=REMOVE_KEYBOARD
    )
    return ADD_EQUIPMENT

async def add_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление оборудования с валидацией."""
    text = None
    if update.message.voice:
        text = await process_voice_message(update, context)
        if not text:
            return ADD_EQUIPMENT
        await update.message.reply_text(f"🎤 Распознано: {text}")
    elif update.message.text:
        text = update.message.text
    
    if not text:
        await update.message.reply_text("Пожалуйста, введите текст или отправьте голосовое сообщение.")
        return ADD_EQUIPMENT
    
    user_id = update.message.from_user.id
    input_equipment = {e.strip().lower() for e in text.split(",") if e.strip()}
    
    valid_equipment = input_equipment.intersection(ALL_EQUIPMENT_CACHE)
    invalid_equipment = input_equipment.difference(ALL_EQUIPMENT_CACHE)
    
    if valid_equipment:
        db.add_user_equipment(user_id, valid_equipment)
        await update.message.reply_text(f"✅ Добавлено: {', '.join(sorted(valid_equipment))}")
    if invalid_equipment:
        await update.message.reply_text(f"❌ Не найдено в справочнике: {', '.join(sorted(invalid_equipment))}")

    return await manage_equipment(update, context)

async def remove_equipment_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите оборудование для удаления, через запятую (или отправьте голосовое сообщение):",
        reply_markup=REMOVE_KEYBOARD
    )
    return REMOVE_EQUIPMENT

async def remove_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаление оборудования с валидацией."""
    # Получаем текст из сообщения или из голосового распознавания
    text = None
    if update.message.voice:
        text = await process_voice_message(update, context)
        if not text:
            return REMOVE_EQUIPMENT
        await update.message.reply_text(f"🎤 Распознано: {text}")
    elif update.message.text:
        text = update.message.text
    
    if not text:
        await update.message.reply_text("Пожалуйста, введите текст или отправьте голосовое сообщение.")
        return REMOVE_EQUIPMENT
    
    user_id = update.message.from_user.id
    input_equipment = {e.strip().lower() for e in text.split(",") if e.strip()}
    
    valid_equipment = input_equipment.intersection(ALL_EQUIPMENT_CACHE)
    invalid_equipment = input_equipment.difference(ALL_EQUIPMENT_CACHE)
    
    if valid_equipment:
        db.remove_user_equipment(user_id, valid_equipment)
        await update.message.reply_text(f"✅ Удалено: {', '.join(sorted(valid_equipment))}")
    
    if invalid_equipment:
        await update.message.reply_text(f"❌ Не найдено в справочнике: {', '.join(sorted(invalid_equipment))}")

    return await manage_equipment(update, context)

# --- УПРАВЛЕНИЕ ХОЛОДИЛЬНИКОМ ---

async def manage_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню управления холодильником."""
    reply_keyboard = [
        ["Посмотреть продукты"],
        ["Добавить продукты", "Удалить продукты"],
        ["Назад в меню"],
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return MANAGE_STORAGE


async def view_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр списка продуктов с количеством."""
    user_id = update.message.from_user.id
    products = db.get_user_products(user_id)
    if products:
        lines = []
        for name, data in sorted(products.items()):
            if data['quantity'] is not None:
                qty_str = f"{data['quantity']:.10f}".rstrip('0').rstrip('.')
                unit_str = f" {data['unit']}" if data['unit'] else ""
                lines.append(f"- {name.capitalize()}: {qty_str}{unit_str}")
            else:
                lines.append(f"- {name.capitalize()}")
        await update.message.reply_text("Твои продукты:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("Твой холодильник пуст.")
    return MANAGE_STORAGE

def parse_products_with_quantity(text: str) -> list:
    """
    Парсит строку вида "продукт1 100 г, продукт2, продукт3 1.5 шт"
    Если запятых нет (голосовой ввод), пытается умно разделить по пробелам,
    проверяя комбинации слов на соответствие продуктам из справочника
    Возвращает список словарей: [{'name': ..., 'quantity': ..., 'unit': ...}]
    """
    parsed_products = []
    
    # Если есть запятые, разделяем по запятым
    if ',' in text:
        items = [item.strip() for item in text.split(',') if item.strip()]
    else:
        words = text.strip().split()
        items = []
        i = 0
        
        while i < len(words):
            if re.match(r'^\d+\.?\d*$', words[i]):
                if i + 1 < len(words) and len(words[i + 1]) <= 5:
                    i += 2
                    continue
                else:
                    i += 1
                    continue
            
            # Пытаемся найти продукт, начиная с самых длинных комбинаций (3, 2, 1 слово)
            found = False
            for length in [3, 2, 1]:
                if i + length <= len(words):
                    candidate = ' '.join(words[i:i+length]).lower()
                    if candidate in ALL_PRODUCTS_CACHE:
                        items.append(candidate)
                        i += length
                        found = True
                        break
            
            # Если не нашли комбинацию, проверяем, может быть следующее слово даст результат
            if not found:
                next_found = False
                for length in [2, 1]:
                    if i + 1 + length <= len(words):
                        candidate = ' '.join(words[i+1:i+1+length]).lower()
                        if candidate in ALL_PRODUCTS_CACHE:
                            i += 1 + length
                            next_found = True
                            break
                
                if not next_found:
                    items.append(words[i].lower())
                    i += 1
    
    # Регулярное выражение для поиска количества и единицы измерения в конце строки
    # (.+?)           - (Группа 1: Название) Любые символы, нежадно
    # \s+             - Пробел
    # (\d+\.?\d*)     - (Группа 2: Количество) Цифры, возможно с точкой
    # \s*             - Опциональный пробел
    # (\w+)?          - (Группа 3: Ед. изм.) Опциональное слово
    # $               - Конец строки
    pattern = re.compile(r"(.+?)\s+(\d+\.?\d*)\s*(\w+)?$")

    for item in items:
        match = pattern.match(item)
        if match:
            name = match.group(1).strip().lower()
            try:
                quantity = Decimal(match.group(2))
                unit = match.group(3)
                if unit:
                    unit = unit.lower()
            except InvalidOperation:
                name = item.lower()
                quantity = None
                unit = None
        else:
            name = item.lower()
            quantity = None
            unit = None
        
        parsed_products.append({'name': name, 'quantity': quantity, 'unit': unit})
        
    return parsed_products

async def add_products_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите продукты для добавления через запятую (или отправьте голосовое сообщение):",
        reply_markup=REMOVE_KEYBOARD
    )
    return ADD_PRODUCTS

async def add_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление продуктов. Поддерживает текст и голосовые сообщения."""
    # Получаем текст из сообщения или из голосового распознавания
    text = None
    if update.message.voice:
        text = await process_voice_message(update, context)
        if not text:
            return ADD_PRODUCTS
        await update.message.reply_text(f"🎤 Распознано: {text}")
    elif update.message.text:
        text = update.message.text
    
    if not text:
        await update.message.reply_text("Пожалуйста, введите текст или отправьте голосовое сообщение.")
        return ADD_PRODUCTS
    
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(text)
    if not parsed_input:
        await update.message.reply_text("Пожалуйста, введите названия продуктов.")
        return await manage_storage(update, context)

    current_fridge = db.get_user_products(user_id)
    
    products_to_upsert = []
    report_added = []
    report_updated = []
    report_invalid = []

    for p_in in parsed_input:
        name = p_in['name']
        
        if name not in ALL_PRODUCTS_CACHE:
            report_invalid.append(name)
            continue

        existing_product = current_fridge.get(name)
        new_quantity = p_in['quantity']
        new_unit = p_in['unit']

        if existing_product and existing_product['quantity'] is not None and new_quantity is not None:
            final_quantity = existing_product['quantity'] + new_quantity
            final_unit = new_unit if new_unit else existing_product['unit']
            report_updated.append(f"{name} (+{new_quantity})")
        else:
            final_quantity = new_quantity
            final_unit = new_unit
            report_added.append(f"{name} ({'количество не указано' if final_quantity is None else final_quantity})")
        
        products_to_upsert.append({'name': name, 'quantity': final_quantity, 'unit': final_unit})

    if products_to_upsert:
        db.upsert_products_to_user(user_id, products_to_upsert)

    response_parts = []
    if report_added:
        response_parts.append(f"✅ Добавлено/обновлено: {', '.join(report_added)}.")
    if report_updated:
        response_parts.append(f"🔄 Количество увеличено: {', '.join(report_updated)}.")
    if report_invalid:
        response_parts.append(f"❌ Не найдены в справочнике: {', '.join(report_invalid)}.")
    
    await update.message.reply_text("\n".join(response_parts))
    return await manage_storage(update, context)



async def remove_products_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите продукты для удаления через запятую (или отправьте голосовое сообщение):",
        reply_markup=REMOVE_KEYBOARD
    )
    return REMOVE_PRODUCTS

async def remove_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаление продуктов. Поддерживает текст и голосовые сообщения."""
    # Получаем текст из сообщения или из голосового распознавания
    text = None
    if update.message.voice:
        text = await process_voice_message(update, context)
        if not text:
            return REMOVE_PRODUCTS
        await update.message.reply_text(f"🎤 Распознано: {text}")
    elif update.message.text:
        text = update.message.text
    
    if not text:
        await update.message.reply_text("Пожалуйста, введите текст или отправьте голосовое сообщение.")
        return REMOVE_PRODUCTS
    
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(text)
    if not parsed_input:
        await update.message.reply_text("Пожалуйста, введите названия продуктов.")
        return await manage_storage(update, context)
        
    current_fridge = db.get_user_products(user_id)

    products_to_delete = []
    products_to_update = []
    report_deleted = []
    report_reduced = []
    report_not_found = []

    for p_in in parsed_input:
        name = p_in['name']
        
        if name not in current_fridge:
            report_not_found.append(name)
            continue

        existing_product = current_fridge[name]
        quantity_to_remove = p_in['quantity']

        if quantity_to_remove is None:
            products_to_delete.append(name)
            report_deleted.append(name)
        elif existing_product['quantity'] is not None:
            new_quantity = existing_product['quantity'] - quantity_to_remove
            if new_quantity <= 0:
                products_to_delete.append(name)
                report_deleted.append(f"{name} (полностью)")
            else:
                products_to_update.append({'name': name, 'quantity': new_quantity, 'unit': existing_product['unit']})
                report_reduced.append(f"{name} (-{quantity_to_remove})")
        else:
            report_not_found.append(f"{name} (нельзя вычесть количество, т.к. оно не было задано)")


    if products_to_delete:
        db.remove_products_from_user(user_id, products_to_delete)
    if products_to_update:
        db.upsert_products_to_user(user_id, products_to_update)

    response_parts = []
    if report_deleted:
        response_parts.append(f"✅ Удалено: {', '.join(report_deleted)}.")
    if report_reduced:
        response_parts.append(f"🔄 Количество уменьшено: {', '.join(report_reduced)}.")
    if report_not_found:
        response_parts.append(f"❌ Не найдены или операция невозможна: {', '.join(report_not_found)}.")

    await update.message.reply_text("\n".join(response_parts))
    return await manage_storage(update, context)


# --- Подбор рецепта ---
async def prompt_recipe_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 1: Спрашивает, как подбирать рецепт."""
    reply_keyboard = [
        ["Только из имеющихся продуктов"],
        ["Добавить 1-2 недостающих ингредиента"],
    ]
    await update.message.reply_text(
        "Как будем подбирать рецепт?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return CHOOSE_RECIPE_TYPE

async def prompt_for_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 2: Получает тип подбора, сохраняет его и спрашивает про время."""
    context.user_data["recipe_type"] = update.message.text
    
    time_keyboard = ReplyKeyboardMarkup([["Неважно"]], one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Введите максимальное время приготовления в минутах или нажмите кнопку.",
        reply_markup=time_keyboard
    )
    return FILTER_BY_TIME

# def _calculate_preference_score(recipe: dict, preferences: dict) -> int:
    """Вспомогательная функция для подсчета 'очков' рецепта для сортировки."""
    score = 0
    recipe_ingredients = {ing.lower() for ing in recipe.get('ingredients', {}).keys()}
    score += len(recipe_ingredients.intersection(preferences.get('like', set())))
    score -= len(recipe_ingredients.intersection(preferences.get('avoid', set())))
    return score

def _parse_recipe_quantity(description: str) -> Decimal | None:
    """
    Извлекает первое число (целое или с точкой) из строки ингредиента.
    Возвращает Decimal или None, если число не найдено.
    """
    if not description:
        return None
    match = re.search(r'(\d+\.?\d*)', description)
    if match:
        try:
            return Decimal(match.group(1))
        except InvalidOperation:
            return None
    return None


# def find_matching_recipes(user_products: dict, user_equipment: set, forbidden_products: set, recipe_type: str, max_time: int, all_recipes: list) -> list:
    """
    Логика поиска рецептов с учетом количества продуктов. (БУДЕТ ЗАМЕНЕНО ВЫЗОВОМ LLM)
    """
    matched_recipes = []
    
    for recipe in all_recipes:
        # 1. Фильтр по оборудованию (жесткий)
        required_equipment_str = recipe.get("equipment", "")
        required_equipment = {e.strip().lower() for e in required_equipment_str.split(',') if e.strip()}
        if not required_equipment.issubset(user_equipment):
            continue

        # 2. Фильтр по ограничениям/аллергиям (жесткий)
        recipe_ingredient_names = {ing.lower() for ing in recipe.get("ingredients", {}).keys()}
        if not forbidden_products.isdisjoint(recipe_ingredient_names):
            continue

        # 3. Фильтр по наличию продуктов (гибкий)
        recipe_ingredients = recipe.get("ingredients", {})
        missing_ingredients = []

        for required_name, required_desc in recipe_ingredients.items():
            required_name = required_name.lower()
            
            if required_name not in user_products:
                missing_ingredients.append(required_name)
                continue

            user_has = user_products[required_name]
            user_quantity = user_has.get('quantity')

            if user_quantity is None:
                continue

            required_quantity = _parse_recipe_quantity(required_desc)

            if required_quantity is None:
                continue
            
            if user_quantity < required_quantity:
                missing_ingredients.append(required_name)
        
        if recipe_type == "Только из имеющихся продуктов" and missing_ingredients:
            continue
        if recipe_type == "Добавить 1-2 недостающих ингредиента" and len(missing_ingredients) > 2:
            continue

        # 4. Фильтр по времени
        cooking_time = recipe.get("cooking_time_minutes", 0)
        if max_time > 0 and cooking_time > max_time:
            continue
            
        matched_recipes.append(recipe)

    return matched_recipes

# ПЕРЕНЕСТИ НА СТОРОНУ БД
def preliminary_filter_recipes(user_products: dict, recipe_type: str, max_time: int, all_recipes: list) -> list:
    """
    Предварительная фильтрация рецептов по жестким критериям, которые легко проверить кодом:
    - Нехватка ингредиентов (в зависимости от выбора пользователя)
    - Максимальное время приготовления
    """
    matched_recipes = []
    
    for recipe in all_recipes:
        # 1. Фильтр по нехватке продуктов
        recipe_ingredients = recipe.get("ingredients", {})
        missing_ingredients = []

        for required_name, required_desc in recipe_ingredients.items():
            required_name = required_name.lower()
            
            if required_name not in user_products:
                missing_ingredients.append(required_name)
                continue

            user_has = user_products[required_name]
            user_quantity = user_has.get('quantity')

            if user_quantity is None:
                continue

            required_quantity = _parse_recipe_quantity(required_desc)

            if required_quantity is None:
                continue
            
            if user_quantity < required_quantity:
                missing_ingredients.append(required_name)
        
        if recipe_type == "Только из имеющихся продуктов" and missing_ingredients:
            continue
        if recipe_type == "Добавить 1-2 недостающих ингредиента" and len(missing_ingredients) > 2:
            continue

        # 2. Фильтр по времени
        cooking_time = recipe.get("cooking_time_minutes", 0)
        if max_time > 0 and cooking_time > max_time:
            continue
            
        matched_recipes.append(recipe)

    return matched_recipes


async def filter_recipes_with_llm(recipes_to_filter: list, equipment_constraints: set, strict_constraints: set, soft_constraints: dict) -> list[str]:
    """
    Отправляет список рецептов и ограничения пользователя в LLM для фильтрации и сортировки.
    Возвращает отсортированный список названий рецептов.
    """
    if not recipes_to_filter:
        return []

    preferences_text_parts = []
    if soft_constraints.get('like'):
        preferences_text_parts.append(f"Пользователь любит: {', '.join(soft_constraints['like'])}")
    if soft_constraints.get('avoid'):
        preferences_text_parts.append(f"Пользователь НЕ любит: {', '.join(soft_constraints['avoid'])}")
    preferences_text = ". ".join(preferences_text_parts) if preferences_text_parts else "Нет особых предпочтений."

    recipes_json = json.dumps(recipes_to_filter, ensure_ascii=False, indent=2, cls=SetEncoder)

    prompt = f"""
[ЗАДАЧА] Отфильтруй список рецептов по предпочтениям пользователя.

[СТРОГИЕ ОГРАНИЧЕНИЯ - НЕЛЬЗЯ НАРУШАТЬ]:
- Медицинские ограничения
{list(strict_constraints)}
- У пользователя есть только
{list(equipment_constraints)}

[ПРЕДПОЧТЕНИЯ - ЖЕЛАТЕЛЬНО УЧЕСТЬ]:
{preferences_text}

[ИНСТРУКЦИИ]:
1. Сначала исключи все рецепты, нарушающие СТРОГИЕ ограничения
2. Затем отсортируй оставшиеся по соответствию ПРЕДПОЧТЕНИЯМ по убыванию
3. Верни JSON-объект с **единственным** ключом "recipes". Значением этого ключа должен быть массив, содержащий **названия** (поле "name") до 5 наиболее подходящих рецептов. Ответ должен быть строго в указанном формате JSON-объекта.
Пример: {{"recipes": ["Название рецепта 1", "Название рецепта 2"]}}

[СПИСОК РЕЦЕПТОВ ДЛЯ ФИЛЬТРАЦИИ]:
{recipes_json}"""

    try:
        logger.info("Отправка запроса к LLM для фильтрации рецептов...")
        completion = await groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — ассистент, который фильтрует рецепты по правилам. Твой ответ — это всегда JSON-массив с названиями рецептов. Никакого другого текста."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        response_content = completion.choices[0].message.content
        logger.info(f"Ответ от LLM получен: {response_content}")

        parsed_json = json.loads(response_content)
        
        # Ищем список внутри JSON
        if isinstance(parsed_json, list):
            recipe_names = parsed_json
        elif isinstance(parsed_json, dict):
            recipe_names = next((v for v in parsed_json.values() if isinstance(v, list)), [])
        else:
            recipe_names = []
            
        if not all(isinstance(name, str) for name in recipe_names):
             logger.error("LLM вернула JSON, но он не является массивом строк.")
             return []

        return recipe_names

    except Exception as e:
        logger.error(f"Ошибка при обращении к LLM или парсинге ответа: {e}")
        return []

async def find_and_show_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 3: Получает время, ищет, сортирует и отображает рецепты."""
    user_input = update.message.text
    if user_input == "Неважно":
        max_time = 0
    else:
        try:
            max_time = int(user_input)
        except (ValueError, TypeError):
            await update.message.reply_text("Это не похоже на число. Пожалуйста, введите время в минутах или нажмите 'Неважно'.")
            return FILTER_BY_TIME
    
    user_id = update.message.from_user.id
    
    user_products = db.get_user_products(user_id)
    user_equipment = db.get_user_equipment(user_id)
    food_constraints = db.get_user_food_constraints(user_id)
    user_preferences = db.get_user_product_preferences(user_id)
    all_recipes = db.get_all_recipes()
    recipe_type = context.user_data.get("recipe_type")
    
    pre_filtered_recipes = preliminary_filter_recipes(user_products, recipe_type, max_time, all_recipes)
    # recipes.sort(key=lambda r: _calculate_preference_score(r, user_preferences), reverse=True)

    if not pre_filtered_recipes:
        await main_menu(update, context)
        await update.message.reply_text("К сожалению, подходящих рецептов не найдено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    # 2. Финальная фильтрация и сортировка с помощью LLM
    final_recipe_names = await filter_recipes_with_llm(
        recipes_to_filter=pre_filtered_recipes,
        equipment_constraints=user_equipment,
        strict_constraints=food_constraints,
        soft_constraints=user_preferences
    )
    
    await main_menu(update, context) 

    if not final_recipe_names:
        await update.message.reply_text("К сожалению, не удалось подобрать рецепты по твоим ограничениям.")
    else:
        recipes_map = {recipe['name']: recipe for recipe in pre_filtered_recipes}
        final_recipes = [recipes_map[name] for name in final_recipe_names if name in recipes_map]

        if not final_recipes:
            await update.message.reply_text("Произошла ошибка при сопоставлении рецептов. Попробуй еще раз.")
            context.user_data.clear()
            return ConversationHandler.END

        keyboard = []
        for recipe in final_recipes: 
            button = [InlineKeyboardButton(recipe["name"], callback_data=f"recipe_{recipe['id']}")]
            keyboard.append(button)
            
        keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu_back")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Вот что я нашел:", reply_markup=reply_markup)
    
    context.user_data.clear()
    return ConversationHandler.END


# --- ДЕТАЛИ РЕЦЕПТА И ГОТОВКА ---

async def recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображение полной информации о рецепте с кнопками действий."""
    query = update.callback_query
    await query.answer()
    
    recipe_id = int(query.data.split("_")[1])
    recipe = db.get_recipe_by_id(recipe_id)
    
    if not recipe:
        await query.edit_message_text(text="Извините, этот рецепт не найден.")
        return

    ingredients_list = "\n".join(
        f"- {name.capitalize()}: {amount}" for name, amount in recipe["ingredients"].items()
    )
    
    kbju_info = recipe.get("kbju", {})
    kbju_text = (f"Калории: {kbju_info.get('calories', 'N/A')} ккал\n"
                 f"Белки: {kbju_info.get('proteins', 'N/A')} г\n"
                 f"Жиры: {kbju_info.get('fats', 'N/A')} г\n"
                 f"Углеводы: {kbju_info.get('carbohydrates', 'N/A')} г")
    
    instructions_text = '\n'.join(recipe['instructions'].splitlines())

    text = (
        f"*{recipe['name']}*\n\n"
        f"_{recipe['description']}_\n\n"
        f"*Ингредиенты:*\n{ingredients_list}\n\n"
        f"*Способ приготовления:*\n{instructions_text}\n\n" 
        f"*Время приготовления:* {recipe['cooking_time_minutes']} мин.\n\n"
        f"*Оборудование:* {recipe['equipment']}\n"
        # f"*КБЖУ:*\n{kbju_text}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Приготовить (списать ингредиенты)", callback_data=f"cook_{recipe_id}")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu_back")]
    ])

    await query.edit_message_text(text=text, parse_mode='Markdown', reply_markup=keyboard)
    
async def cook_recipe_and_update_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки "Приготовить" и списывает ингредиенты."""
    query = update.callback_query
    await query.answer(text="Списываю продукты...")

    user_id = query.from_user.id
    recipe_id = int(query.data.split("_")[1])
    recipe = db.get_recipe_by_id(recipe_id)

    if not recipe:
        await query.edit_message_text(text="Ошибка: рецепт для списания не найден.")
        return

    current_fridge = db.get_user_products(user_id)
    required_ingredients = recipe.get("ingredients", {})

    products_to_delete = []
    products_to_update = []
    report_lines = ["Обращаю Ваше внимание, что закончились следующие продукты:"]

    for name, desc in required_ingredients.items():
        name = name.lower()
        
        if name not in current_fridge:
            # report_lines.append(f"⚠️ {name.capitalize()}: не найден в холодильнике.")
            continue

        user_has = current_fridge[name]
        user_quantity = user_has.get('quantity')
        
        if user_quantity is None:
            continue

        required_quantity = _parse_recipe_quantity(desc)

        if required_quantity is None:
            continue
        
        new_quantity = user_quantity - required_quantity
        if new_quantity <= 0:
            products_to_delete.append(name)
            report_lines.append(f"🗑️ {name.capitalize()}: использован полностью.")
        else:
            products_to_update.append({'name': name, 'quantity': new_quantity, 'unit': user_has['unit']})
            # report_lines.append(f"🔄 {name.capitalize()}: осталось {new_quantity:.10f}".rstrip('0').rstrip('.'))

    if products_to_delete:
        db.remove_products_from_user(user_id, products_to_delete)
    if products_to_update:
        db.upsert_products_to_user(user_id, products_to_update)

    if len(report_lines) == 1:
        final_report = "Все необходимые продукты были в достаточном количестве."
    else:
        final_report = "\n".join(report_lines)
        
    await query.edit_message_text(
        text=f"*{recipe['name']}*\n\n{final_report}\n\nПриятного аппетита!",
        parse_mode='Markdown'
    )

# --- Вспомогательные функции ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение."""
    help_text = (
        "🤖 *Я ваш кулинарный помощник! Вот что я умею:*\n\n"
        "● *Мой холодильник* - управляйте списком продуктов, которые у вас есть. Добавляйте и удаляйте их, чтобы я знал, из чего вам готовить.\n\n"
        "● *Мое оборудование* - укажите, какая кухонная техника у вас есть (духовка, блендер и т.д.), чтобы я подбирал рецепты, которые вы точно сможете приготовить.\n\n"
        "● *Подобрать рецепт* - главный раздел! Я найду лучшие блюда на основе ваших продуктов, оборудования и предпочтений, хранящихся в базе данных.\n\n"
        "Для начала работы используйте кнопки в меню ниже."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main() -> None:
    """Основная функция для запуска бота."""
    
    global ALL_PRODUCTS_CACHE, ALL_EQUIPMENT_CACHE
    ALL_PRODUCTS_CACHE = db.get_all_product_names()
    ALL_EQUIPMENT_CACHE = db.get_all_equipment_names()
    logger.info(f"Загружено {len(ALL_PRODUCTS_CACHE)} продуктов и {len(ALL_EQUIPMENT_CACHE)} единиц оборудования.")

    # Инициализация модели Vosk для распознавания речи
    if init_vosk_model():
        logger.info("Модель Vosk успешно инициализирована. Голосовые сообщения доступны.")
    else:
        logger.warning("Модель Vosk не инициализирована. Голосовые сообщения будут недоступны.")

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    common_fallbacks = [
        CommandHandler("start", start),
        CommandHandler("menu", main_menu),
        CommandHandler("cancel", cancel), # Добавляем нашу новую команду
        MessageHandler(filters.Regex("^Назад в меню$"), main_menu) # Ваш надежный выход по кнопке
    ]

    # Ветка 1: Управление холодильником
    storage_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Мой холодильник$"), manage_storage)],
        states={
            MANAGE_STORAGE: [
                MessageHandler(filters.Regex("^Посмотреть продукты$"), view_products),
                MessageHandler(filters.Regex("^Добавить продукты$"), add_products_prompt),
                MessageHandler(filters.Regex("^Удалить продукты$"), remove_products_prompt),
            ],
            ADD_PRODUCTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_products),
                MessageHandler(filters.VOICE, add_products),
            ],
            REMOVE_PRODUCTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, remove_products),
                MessageHandler(filters.VOICE, remove_products),
            ],
        },
        fallbacks=common_fallbacks,
    )
    
    # Ветка 2: Управление оборудованием
    equipment_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Мое оборудование$"), manage_equipment)],
        states={
            MANAGE_EQUIPMENT: [
                MessageHandler(filters.Regex("^Посмотреть оборудование$"), view_equipment),
                MessageHandler(filters.Regex("^Добавить оборудование$"), add_equipment_prompt),
                MessageHandler(filters.Regex("^Удалить оборудование$"), remove_equipment_prompt),
            ],
            ADD_EQUIPMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_equipment),
                MessageHandler(filters.VOICE, add_equipment),
            ],
            REMOVE_EQUIPMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, remove_equipment),
                MessageHandler(filters.VOICE, remove_equipment),
            ],
        },
        fallbacks=common_fallbacks,
    )
    
    # Ветка 3: Подбор рецепта
    recipe_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Подобрать рецепт$"), prompt_recipe_type)],
        states={
            CHOOSE_RECIPE_TYPE: [MessageHandler(filters.Regex("^(Только из имеющихся продуктов|Добавить 1-2 недостающих ингредиента)$"), prompt_for_time)],
            FILTER_BY_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_and_show_recipes)],
        },
        fallbacks=common_fallbacks,
    )
    
    # Регистрация всех обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", main_menu))
    application.add_handler(MessageHandler(filters.Regex("^Помощь$"), help_command))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(storage_conv)
    application.add_handler(equipment_conv)
    application.add_handler(recipe_conv)

    application.add_handler(CallbackQueryHandler(recipe_details, pattern="^recipe_"))
    application.add_handler(CallbackQueryHandler(cook_recipe_and_update_storage, pattern="^cook_"))
    application.add_handler(CallbackQueryHandler(back_to_main_menu_inline, pattern="^main_menu_back$"))

    application.run_polling()

if __name__ == "__main__":
    main()
