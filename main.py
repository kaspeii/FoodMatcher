import logging
import os
import re
import json
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Tuple, List, Dict, Any, Set
from globals import *
from thefuzz import process

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
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
ALL_PRODUCTS_CACHE = {}
ALL_EQUIPMENT_CACHE = set()

# Константа для удаления клавиатуры
REMOVE_KEYBOARD = ReplyKeyboardRemove()

# Глобальная переменная для модели Vosk
VOSK_MODEL = None

# Состояния для ConversationHandler'ов
(
    MANAGE_STORAGE, ADD_PRODUCTS, REMOVE_PRODUCTS,
    MANAGE_EQUIPMENT, ADD_EQUIPMENT, REMOVE_EQUIPMENT,
    SELECTING_EQUIPMENT_KEYBOARD, SELECTING_EQUIPMENT_FOR_REMOVAL,
    CHOOSE_RECIPE_TYPE, FILTER_BY_TIME,
    MANAGE_PREFERENCES, 
    ADD_PREFERENCE, ADD_CONSTRAINT, 
    CHOOSE_DELETE_TYPE, AWAIT_PREFERENCE_DELETION, AWAIT_CONSTRAINT_DELETION
) = range(16)

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
            await update.message.reply_text("Не удалось распознать речь. Попробуй еще раз или введи текст.")
            return None
            
    except Exception as e:
        await update.message.reply_text("Произошла ошибка при обработке голосового сообщения. Попробуй ввести текст.")
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
        ["Предпочтения и ограничения"],
        ["Подобрать рецепт"],
        ["Помощь"],
    ]
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}! Я твой кулинарный помощник. Выбери действие:",
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
        ["Предпочтения и ограничения"],
        ["Подобрать рецепт"],
        ["Помощь"],
    ]
    
    await update.message.reply_text(
        f"Выбери действие:",
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
    if query.message.photo:
        await query.edit_message_caption(caption="Ты вернулся в главное меню.", reply_markup=None)
    else:
        await query.edit_message_text(text="Ты вернулся в главное меню.", reply_markup=None)

# --- УПРАВЛЕНИЕ ОБОРУДОВАНИЕМ ---

async def manage_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню управления оборудованием."""
    reply_keyboard = [
        ["Посмотреть оборудование"],
        ["Добавить оборудование", "Удалить оборудование"],
        ["Назад в меню"],
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return MANAGE_EQUIPMENT

async def view_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр списка оборудования."""
    user_id = update.message.from_user.id
    equipment = db.get_user_equipment(user_id)
    if equipment:
        await update.message.reply_text("Твое оборудование:\n- " + "\n- ".join(sorted(list(equipment))))
    else:
        await update.message.reply_text("У тебя не добавлено оборудование.")
    return MANAGE_EQUIPMENT

def build_equipment_keyboard(selected_items: set) -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру с кнопками оборудования."""
    keyboard = []
    row = []
    for equipment in EQUIPMENT_LIST:
        text = f"✅ {equipment.capitalize()}" if equipment in selected_items else equipment.capitalize()
        row.append(InlineKeyboardButton(text, callback_data=f"equip_{equipment}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="equip_done")])
    return InlineKeyboardMarkup(keyboard)

async def add_equipment_interactive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс добавления оборудования с помощью инлайн-кнопок."""
    context.user_data['selected_equipment'] = set()

    keyboard = build_equipment_keyboard(context.user_data['selected_equipment'])
    await update.message.reply_text(
        "Выбери свое оборудование. Нажми на предмет еще раз, чтобы убрать его.\n"
        "Когда закончишь, нажми 'Готово'.",
        reply_markup=keyboard
    )
    
    return SELECTING_EQUIPMENT_KEYBOARD

async def select_equipment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия на кнопки выбора оборудования."""
    query = update.callback_query
    await query.answer() 
    
    selected_item = query.data.split('_', 1)[1]
    
    user_selection = context.user_data.get('selected_equipment', set())

    if selected_item in user_selection:
        user_selection.remove(selected_item)
    else:
        user_selection.add(selected_item)
        
    context.user_data['selected_equipment'] = user_selection

    keyboard = build_equipment_keyboard(user_selection)
    await query.edit_message_reply_markup(reply_markup=keyboard)

    return SELECTING_EQUIPMENT_KEYBOARD

async def done_selecting_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает выбор и сохраняет оборудование."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    selected_equipment = context.user_data.get('selected_equipment')

    if selected_equipment:
        db.add_user_equipment(user_id, selected_equipment)
        
        await query.edit_message_text(
            text=f"✅ Оборудование сохранено: {', '.join(sorted(list(selected_equipment)))}"
        )
    else:
        await query.edit_message_text(text="Ты ничего не выбрал.")

    context.user_data.pop('selected_equipment', None)
    
    await manage_equipment(update.callback_query, context)
    return MANAGE_EQUIPMENT

def build_remove_equipment_keyboard(user_equipment: list, selected_for_removal: set) -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру из оборудования, которое есть у пользователя."""
    keyboard = []
    row = []
    for equipment in sorted(user_equipment):
        text = f"❌ {equipment.capitalize()}" if equipment in selected_for_removal else equipment.capitalize()
        row.append(InlineKeyboardButton(text, callback_data=f"del_equip_{equipment}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🗑️ Удалить выбранное", callback_data="del_equip_done")])
    return InlineKeyboardMarkup(keyboard)

async def remove_equipment_interactive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс удаления оборудования с помощью инлайн-кнопок."""
    user_id = update.message.from_user.id
    user_equipment = list(db.get_user_equipment(user_id))

    if not user_equipment:
        await update.message.reply_text("У тебя нет оборудования для удаления.")
        return MANAGE_EQUIPMENT

    context.user_data['user_equipment_list'] = user_equipment
    context.user_data['equipment_to_remove'] = set()

    keyboard = build_remove_equipment_keyboard(user_equipment, set())
    await update.message.reply_text(
        "Выбери оборудование, которое хочешь удалить:",
        reply_markup=keyboard
    )
    
    return SELECTING_EQUIPMENT_FOR_REMOVAL

async def select_equipment_for_removal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия на кнопки выбора оборудования для удаления."""
    query = update.callback_query
    await query.answer()

    selected_item = query.data.split('_', 2)[2]
    
    selection_set = context.user_data.get('equipment_to_remove', set())
    
    if selected_item in selection_set:
        selection_set.remove(selected_item)
    else:
        selection_set.add(selected_item)
    
    context.user_data['equipment_to_remove'] = selection_set
    
    # Обновляем клавиатуру с новым выбором
    user_equipment = context.user_data.get('user_equipment_list', [])
    keyboard = build_remove_equipment_keyboard(user_equipment, selection_set)
    await query.edit_message_reply_markup(reply_markup=keyboard)

    return SELECTING_EQUIPMENT_FOR_REMOVAL

async def done_removing_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает выбор и удаляет оборудование."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    equipment_to_remove = context.user_data.get('equipment_to_remove')

    if equipment_to_remove:
        db.remove_user_equipment(user_id, equipment_to_remove)
        await query.edit_message_text(
            text=f"✅ Удалено: {', '.join(sorted(list(equipment_to_remove)))}"
        )
    else:
        await query.edit_message_text(text="Ничего не было удалено.")

    # Очистка временных данных
    context.user_data.pop('user_equipment_list', None)
    context.user_data.pop('equipment_to_remove', None)
    
    await manage_equipment(update.callback_query, context)
    return MANAGE_EQUIPMENT

# --- УПРАВЛЕНИЕ ХОЛОДИЛЬНИКОМ ---

async def manage_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню управления холодильником."""
    reply_keyboard = [
        ["Посмотреть продукты"],
        ["Добавить продукты", "Удалить продукты"],
        ["Назад в меню"],
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return MANAGE_STORAGE


async def view_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр списка продуктов с количеством."""
    user_id = update.message.from_user.id
    products = db.get_user_products(user_id)
    if products:
        lines = []
        sorted_products = sorted(
            products.items(),
            key=lambda item: item[1].get('db_name', item[0])
        )
        for name_key, data in sorted_products:
            display_name = data.get('db_name') or name_key
            if data['quantity'] is not None:
                qty_str = f"{data['quantity']:.10f}".rstrip('0').rstrip('.')
                unit_str = f" {data['unit']}" if data['unit'] else ""
                lines.append(f"- {display_name}: {qty_str}{unit_str}")
            else:
                lines.append(f"- {display_name}")
        await update.message.reply_text("Твои продукты:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("Твой холодильник пуст.")
    return MANAGE_STORAGE

def normalize_unit(unit_str: Optional[str]) -> Optional[str]:
    """
    Приводит строку с единицей измерения к стандартному виду.
    """
    if not unit_str:
        return None
    
    processed_unit = unit_str.lower().strip().strip('.')
    
    return UNIT_NORMALIZATION_MAP.get(processed_unit, processed_unit)

def _is_number(s: str) -> bool:
    """Проверяет, можно ли строку превратить в число."""
    try:
        Decimal(s.replace(',', '.'))
        return True
    except InvalidOperation:
        return False

def parse_products_with_quantity(text: str, all_product_names: Set[str], score_cutoff: int = 85) -> List[Dict[str, Any]]:
    """
    Разбирает строку, используя словарь известных продуктов для корректного
    определения границ названий.
    """
    # 1. Подготовка и токенизация
    processed_text = text.lower().replace(',', ' ')
    # Это одно выражение, состоящее из двух частей, соединенных оператором | (ИЛИ):
    #
    # 1. (?<=[а-я])(?=\d) - находит границу "буква, а затем цифра".
    #    (?<=[а-я]) - "Просмотр назад": проверяет, что слева от текущей позиции есть буква, не захватывая её.
    #    (?=\d)     - "Просмотр вперед": проверяет, что справа от текущей позиции есть цифра, не захватывая её.
    #
    # 2. (?<=\d)(?=[а-я]) - находит границу "цифра, а затем буква".
    #    (?<=\d)     - Проверяет, что слева стоит цифра.
    #    (?=[а-я]) - Проверяет, что справа стоит буква.
    #
    # Поскольку выражение находит только "нулевую" границу между символами, а не сами символы,
    # замена на ' ' просто вставляет пробел в эту позицию.
    processed_text = re.sub(r'(?<=[а-я])(?=\d)|(?<=\d)(?=[а-я])', r' ', processed_text)
    tokens = processed_text.split()
        
    parsed_products = []
    i = 0
    while i < len(tokens):
        best_match = None
        best_score = 0
        tokens_consumed = 0
        
        # 2. Поиск наилучшего многословного совпадения с опечатками
        current_candidate = ""
        for j in range(i, len(tokens)):
            current_candidate = (current_candidate + " " + tokens[j]).strip()
            
            if _is_number(tokens[j]):
                break

            match, score = process.extractOne(current_candidate, all_product_names)
            
            if score > best_score:
                best_score = score
                best_match = match
                tokens_consumed = j - i + 1

        # 3. Принятие решения на основе лучшего найденного совпадения
        if best_score >= score_cutoff:
            found_product = best_match
            i += tokens_consumed
            
            quantity = None
            unit = None
            if i < len(tokens) and _is_number(tokens[i]):
                quantity = Decimal(tokens[i].replace(',', '.'))
                i += 1
                if i < len(tokens):
                    normalized = normalize_unit(tokens[i])
                    if normalized != tokens[i] or normalized in ['г', 'кг', 'л', 'мл', 'шт']:
                        unit = normalized
                        i += 1
            
            parsed_products.append({'name': found_product, 'quantity': quantity, 'unit': unit})
        else:
            i += 1
            
    return parsed_products

def convert_to_standard_unit(quantity: Decimal, unit: Optional[str], product_info: dict) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Конвертирует количество продукта в его стандартную единицу измерения.
    """
    if quantity is None:
        return None, None
        

    if unit is None:
        return quantity, "г"

    if unit in ["г","мл","шт"]:
        return quantity, unit

    if unit not in CONVERSION_FACTORS:
        return None, None 

    multiplier, unit_base_type = CONVERSION_FACTORS[unit]
    

    return quantity * multiplier, unit_base_type

async def add_products_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введи продукты для добавления через запятую (или отправь голосовое сообщение):",
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
        await update.message.reply_text("Пожалуйста, введи текст или отправь голосовое сообщение.")
        return ADD_PRODUCTS
    
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(text, set(ALL_PRODUCTS_CACHE.keys()))
    if not parsed_input:
        await update.message.reply_text("Пожалуйста, введи названия продуктов.")
        return await manage_storage(update, context)

    current_fridge = db.get_user_products(user_id)
    
    products_to_upsert = []
    report_added = []
    report_updated = []
    report_invalid = []
    report_incompatible_units = []

    def format_decimal(value: Decimal) -> str:
        return f"{value:.10f}".rstrip('0').rstrip('.')

    for p_in in parsed_input:
        name = p_in['name']
        
        product_info = ALL_PRODUCTS_CACHE.get(name)
        if not product_info:
            report_invalid.append(name)
            continue
        
        product_id = product_info.get('id')
        db_name = product_info.get('db_name', name)
        
        new_quantity, new_unit = convert_to_standard_unit(
            p_in['quantity'], p_in['unit'], product_info
        )
        
        if new_quantity is None and p_in['quantity'] is not None:
            report_incompatible_units.append(f"{db_name} ({p_in['quantity']} {p_in['unit'] or ''})")
            continue
        
        existing_product = current_fridge.get(name)

        if existing_product and existing_product['quantity'] is not None and new_quantity is not None:
            final_quantity = existing_product['quantity'] + new_quantity
            unit_to_store = new_unit or existing_product.get('unit')
            quantity_text = format_decimal(final_quantity)
            unit_suffix = f" {unit_to_store}" if unit_to_store else ""
            report_updated.append(f"{db_name}: {quantity_text}{unit_suffix}")
            products_to_upsert.append({
                'product_id': product_id,
                'quantity': final_quantity,
                'unit': unit_to_store
            })
        else:
            if new_quantity is not None:
                quantity_text = format_decimal(new_quantity)
                unit_suffix = f" {new_unit}" if new_unit else ""
                report_added.append(f"{db_name} ({quantity_text}{unit_suffix})")
            else:
                report_added.append(f"{db_name} (количество не указано)")
            products_to_upsert.append({
                'product_id': product_id,
                'quantity': new_quantity,
                'unit': new_unit
            })


    if products_to_upsert:
        db.upsert_products_to_user(user_id, products_to_upsert)

    response_parts = []
    if report_added:
        response_parts.append(f"✅ Добавлено: {', '.join(report_added)}.")
    if report_updated:
        response_parts.append(f"🔄 Количество увеличено: {', '.join(report_updated)}.")
    if report_invalid:
        response_parts.append(f"❌ Не найдены в справочнике: {', '.join(report_invalid)}.")
    if report_incompatible_units:
        response_parts.append(f"⚠️ Не удалось конвертировать: {', '.join(report_incompatible_units)}.")
    
    if not response_parts:
        await update.message.reply_text("Ничего не было добавлено. Возможно, вы не указали продукты?")
    else:
        await update.message.reply_text("\n".join(response_parts))
        
    return await manage_storage(update, context)



async def remove_products_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введи продукты для удаления через запятую (или отправь голосовое сообщение):",
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
        await update.message.reply_text("Пожалуйста, введи текст или отправь голосовое сообщение.")
        return REMOVE_PRODUCTS
    
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(text, set(ALL_PRODUCTS_CACHE.keys()))
    if not parsed_input:
        await update.message.reply_text("Пожалуйста, введи названия продуктов.")
        return await manage_storage(update, context)
        
    current_fridge = db.get_user_products(user_id)

    products_to_delete = []
    products_to_update = []
    report_deleted = []
    report_reduced = []
    report_not_found = []

    def format_decimal(value: Decimal) -> str:
        return f"{value:.10f}".rstrip('0').rstrip('.')

    for p_in in parsed_input:
        name = p_in['name']
        
        existing_product = current_fridge.get(name)
        if not existing_product:
            product_info = ALL_PRODUCTS_CACHE.get(name)
            display_name = product_info.get('db_name', name) if product_info else name
            report_not_found.append(display_name)
            continue

        display_name = existing_product.get('db_name', name)
        quantity_to_remove = p_in['quantity']

        if quantity_to_remove is None:
            products_to_delete.append(existing_product['product_id'])
            report_deleted.append(display_name)
        elif existing_product['quantity'] is not None:
            new_quantity = existing_product['quantity'] - quantity_to_remove
            if new_quantity <= 0:
                products_to_delete.append(existing_product['product_id'])
                report_deleted.append(f"{display_name} (полностью)")
            else:
                products_to_update.append({
                    'product_id': existing_product['product_id'],
                    'quantity': new_quantity,
                    'unit': existing_product['unit']
                })
                qty_text = format_decimal(quantity_to_remove)
                unit_suffix = f" {existing_product['unit']}" if existing_product['unit'] else ""
                report_reduced.append(f"{display_name} (-{qty_text}{unit_suffix})")
        else:
            report_not_found.append(f"{display_name} (нельзя вычесть количество, т.к. оно не было задано)")


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

# Управление предпочтениями и ограничениям

async def manage_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Главное меню для предпочтений и ограничений."""
    reply_keyboard = [
        ["Посмотреть мои данные"],
        ["Добавить предпочтение", "Добавить ограничение"],
        ["Удалить запись"],
        ["Назад в меню"],
    ]
    await update.message.reply_text(
        "Здесь ты можешь указать свои вкусовые предпочтения и ограничения (например, аллергии) в свободной форме.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    return MANAGE_PREFERENCES

async def view_preferences_and_constraints(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает все предпочтения и ограничения пользователя в виде нумерованного списка."""
    user_id = update.message.from_user.id
    preferences = db.get_user_preferences_with_ids(user_id)
    constraints = db.get_user_food_constraints_with_ids(user_id)
    
    parts = []
    if preferences:
        pref_list = "\n".join([f"{i+1}. {p['note']}" for i, p in enumerate(preferences)])
        parts.append(f"👍 *Твои предпочтения:*\n{pref_list}")
    else:
        parts.append("👍 *Твои предпочтения:*\n(пусто)")

    if constraints:
        const_list = "\n".join([f"{i+1}. {c['note']}" for i, c in enumerate(constraints)])
        parts.append(f"🚫 *Твои ограничения:*\n{const_list}")
    else:
        parts.append("🚫 *Твои ограничения:*\n(пусто)")
        
    await update.message.reply_text("\n\n".join(parts), parse_mode='Markdown')
    return MANAGE_PREFERENCES

async def add_preference_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Напиши, что ты любишь или недолюбливаешь в еде:", reply_markup=REMOVE_KEYBOARD)
    return ADD_PREFERENCE

async def add_constraint_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Напиши, что тебе нельзя или что ты не любишь:", reply_markup=REMOVE_KEYBOARD)
    return ADD_CONSTRAINT

async def add_preference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет одно или несколько предпочтений, введенных через запятую."""
    text_input = update.message.text
    user_id = update.message.from_user.id

    notes_to_add = [note.strip() for note in text_input.split(',') if len(note.strip()) >= 3]

    if not notes_to_add:
        await update.message.reply_text("Не удалось распознать корректные предпочтения. Попробуй еще раз, длина каждого пункта должна быть не менее 3 символов.")
        return ADD_PREFERENCE

    for note in notes_to_add:
        db.add_user_preference(user_id, note)
    
    added_list_str = "\n- ".join(notes_to_add)
    await update.message.reply_text(f"✅ Добавлено предпочтений: {len(notes_to_add)}\n- {added_list_str}")
    
    return await manage_preferences(update, context)

async def add_constraint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет одно или несколько ограничений, введенных через запятую."""
    text_input = update.message.text
    user_id = update.message.from_user.id

    constraints_to_add = [constraint.strip() for constraint in text_input.split(',') if len(constraint.strip()) >= 3]

    if not constraints_to_add:
        await update.message.reply_text("Не удалось распознать корректные ограничения. Попробуй еще раз, длина каждого пункта должна быть не менее 3 символов.")
        return ADD_CONSTRAINT

    for constraint in constraints_to_add:
        db.add_user_food_constraint(user_id, constraint)

    added_list_str = "\n- ".join(constraints_to_add)
    await update.message.reply_text(f"✅ Добавлено ограничений: {len(constraints_to_add)}\n- {added_list_str}")

    return await manage_preferences(update, context)

async def delete_type_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Спрашивает, что удалять: предпочтения или ограничения."""
    reply_keyboard = [["Предпочтения"], ["Ограничения"], ["Отмена"]]
    await update.message.reply_text(
        "Записи из какого списка ты хочешь удалить?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return CHOOSE_DELETE_TYPE

async def list_preferences_for_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает список предпочтений для удаления."""
    user_id = update.message.from_user.id
    preferences = db.get_user_preferences_with_ids(user_id)
    if not preferences:
        await update.message.reply_text("Список предпочтений пуст. Нечего удалять.", reply_markup=REMOVE_KEYBOARD)
        return await manage_preferences(update, context)

    # Сохраняем карту "порядковый номер -> id в базе"
    context.user_data['id_map'] = {i + 1: p['id'] for i, p in enumerate(preferences)}
    
    pref_list = "\n".join([f"{i+1}. {p['note']}" for i, p in enumerate(preferences)])
    await update.message.reply_text(
        f"Твои предпочтения:\n{pref_list}\n\n"
        "Введи номера записей для удаления (например: 2, 4) или 'все' для очистки.",
        reply_markup=REMOVE_KEYBOARD
    )
    return AWAIT_PREFERENCE_DELETION

async def list_constraints_for_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает список ограничений для удаления."""
    user_id = update.message.from_user.id
    constraints = db.get_user_food_constraints_with_ids(user_id)
    if not constraints:
        await update.message.reply_text("Список ограничений пуст. Нечего удалять.", reply_markup=REMOVE_KEYBOARD)
        return await manage_preferences(update, context)

    context.user_data['id_map'] = {i + 1: c['id'] for i, c in enumerate(constraints)}
    
    const_list = "\n".join([f"{i+1}. {c['note']}" for i, c in enumerate(constraints)])
    await update.message.reply_text(
        f"Твои ограничения:\n{const_list}\n\n"
        "Введи номера записей для удаления (например: 2, 4) или 'все' для очистки.",
        reply_markup=REMOVE_KEYBOARD
    )
    return AWAIT_CONSTRAINT_DELETION

async def delete_preferences_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод номеров для удаления предпочтений."""
    user_id = update.message.from_user.id
    text = update.message.text.lower().strip()

    if text == 'все':
        db.clear_user_preferences(user_id)
        await update.message.reply_text("✅ Все предпочтения удалены.")
        return await manage_preferences(update, context)

    try:
        # Парсим номера, введенные пользователем
        input_numbers = {int(n.strip()) for n in text.replace(',', ' ').split()}
        id_map = context.user_data.get('id_map', {})
        
        # Преобразуем порядковые номера в реальные ID из базы
        ids_to_delete = [id_map[num] for num in input_numbers if num in id_map]
        
        if not ids_to_delete:
            await update.message.reply_text("Не найдено записей с такими номерами. Попробуй еще раз.")
            return AWAIT_PREFERENCE_DELETION
            
        db.delete_user_preferences_by_ids(user_id, ids_to_delete)
        await update.message.reply_text(f"✅ Записи с номерами {', '.join(map(str, sorted(input_numbers)))} удалены.")

    except ValueError:
        await update.message.reply_text("Пожалуйста, введи числа, разделенные запятой, или слово 'все'.")
        return AWAIT_PREFERENCE_DELETION
    finally:
        context.user_data.pop('id_map', None)
        
    return await manage_preferences(update, context)

async def delete_constraints_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод номеров для удаления ограничений."""
    user_id = update.message.from_user.id
    text = update.message.text.lower().strip()

    if text == 'все':
        db.clear_user_food_constraints(user_id)
        await update.message.reply_text("✅ Все ограничения удалены.")
        return await manage_preferences(update, context)

    try:
        input_numbers = {int(n.strip()) for n in text.replace(',', ' ').split()}
        id_map = context.user_data.get('id_map', {})
        ids_to_delete = [id_map[num] for num in input_numbers if num in id_map]
        
        if not ids_to_delete:
            await update.message.reply_text("Не найдено записей с такими номерами. Попробуй еще раз.")
            return AWAIT_CONSTRAINT_DELETION
            
        db.delete_user_food_constraints_by_ids(user_id, ids_to_delete)
        await update.message.reply_text(f"✅ Записи с номерами {', '.join(map(str, sorted(input_numbers)))} удалены.")

    except ValueError:
        await update.message.reply_text("Пожалуйста, введи числа, разделенные запятой, или слово 'все'.")
        return AWAIT_CONSTRAINT_DELETION
    finally:
        context.user_data.pop('id_map', None)
        
    return await manage_preferences(update, context)

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
        "Введи максимальное время приготовления в минутах или нажми кнопку.",
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

# def preliminary_filter_recipes(user_products: dict, recipe_type: str, max_time: int, all_recipes: list) -> list:
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


async def filter_recipes_with_llm(recipes_to_filter: list, equipment_constraints: set, strict_constraints: list, soft_constraints: list) -> list[str]:
    """
    Отправляет список рецептов и ограничения пользователя в LLM для фильтрации и сортировки.
    Возвращает отсортированный список названий рецептов.
    """
    if not recipes_to_filter:
        return []

    recipes_json = json.dumps(recipes_to_filter, ensure_ascii=False, indent=2, cls=SetEncoder)

    prompt = f"""
[ЗАДАЧА] Отфильтруй список рецептов по предпочтениям пользователя.

[СТРОГИЕ ОГРАНИЧЕНИЯ - НЕЛЬЗЯ НАРУШАТЬ]:
- Медицинские ограничения
{strict_constraints}
- У пользователя есть только
{list(equipment_constraints)}

[ПРЕДПОЧТЕНИЯ - ЖЕЛАТЕЛЬНО УЧЕСТЬ]:
{soft_constraints}

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
            model="llama-3.3-70b-versatile",
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
            await update.message.reply_text("Это не похоже на число. Пожалуйста, введи время в минутах или нажми 'Неважно'.")
            return FILTER_BY_TIME
    
    user_id = update.message.from_user.id
    
    user_equipment = db.get_user_equipment(user_id)
    constraints_from_db  = db.get_user_food_constraints_with_ids(user_id)
    preferences_from_db  = db.get_user_preferences_with_ids(user_id)
    recipe_type = context.user_data.get("recipe_type")
    
    user_preferences = [p['note'] for p in preferences_from_db]
    food_constraints = [c['note'] for c in constraints_from_db]
    
    pre_filtered_recipes = db.preliminary_filter_recipes_db(user_id, recipe_type, max_time)
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
        await query.edit_message_text(text="Извини, этот рецепт не найден.")
        return

    main_image_url = db.get_recipe_main_image(recipe_id)
    nutrition_info = db.get_recipe_nutrition(recipe_id)
    
    ingredients_list = "\n".join(
        f"- {name.capitalize()}: {amount}" for name, amount in recipe["ingredients"].items()
    )
    
    if nutrition_info:
        def format_decimal(d_val):
            """Красиво форматирует число, убирая лишние нули."""
            return f"{d_val:.2f}".rstrip('0').rstrip('.')

        kbju_text = (f"  - Калории: {format_decimal(nutrition_info['calories'])} ккал\n"
                     f"  - Белки: {format_decimal(nutrition_info['protein'])} г\n"
                     f"  - Жиры: {format_decimal(nutrition_info['fat'])} г\n"
                     f"  - Углеводы: {format_decimal(nutrition_info['carbs'])} г")
        
    
    instructions_text = '\n'.join(recipe['instructions'].splitlines())

    text = (
        f"*{recipe['name']}*\n\n"
        f"_{recipe['description']}_\n\n"
        f"*Ингредиенты:*\n{ingredients_list}\n\n"
        f"*Способ приготовления:*\n{instructions_text}\n\n" 
        f"*Время приготовления:* {recipe['cooking_time_minutes']} мин.\n\n"
        f"*Оборудование:* {recipe['equipment']}\n"
        f"*КБЖУ на 100г:*\n{kbju_text}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Приготовить (списать ингредиенты)", callback_data=f"cook_{recipe_id}")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu_back")]
    ])

    if main_image_url:
        # ПРАВИЛЬНЫЙ СПОСОБ: Редактируем сообщение, заменяя его содержимое на фото с подписью
        media = InputMediaPhoto(
            media=main_image_url,
            caption=text,
            parse_mode='Markdown'
        )
        await query.edit_message_media(media=media, reply_markup=keyboard)
    else:
        # Если картинки нет, просто редактируем текст, как и раньше
        await query.edit_message_text(
            text=text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
async def cook_recipe_and_update_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатие кнопки "Приготовить" и списывает ингредиенты."""
    query = update.callback_query
    await query.answer(text="Списываю продукты...")

    user_id = query.from_user.id
    recipe_id = int(query.data.split("_")[1])
    recipe = db.get_recipe_by_id(recipe_id)

    if not recipe:
        if query.message.photo:
            await query.edit_message_caption(caption="Ошибка: рецепт для списания не найден.", reply_markup=None)
        else:
            await query.edit_message_text(text="Ошибка: рецепт для списания не найден.", reply_markup=None)
        return

    current_fridge = db.get_user_products(user_id)
    required_ingredients = recipe.get("ingredients", {})

    products_to_delete = []
    products_to_update = []
    report_lines = ["Обращаю Твое внимание, что закончились следующие продукты:"]

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
        display_name = user_has.get('db_name', name)
        if new_quantity <= 0:
            products_to_delete.append(user_has['product_id'])
            report_lines.append(f"🗑️ {display_name}: использован полностью.")
        else:
            products_to_update.append({
                'product_id': user_has['product_id'],
                'quantity': new_quantity,
                'unit': user_has['unit']
            })

    if products_to_delete:
        db.remove_products_from_user(user_id, products_to_delete)
    if products_to_update:
        db.upsert_products_to_user(user_id, products_to_update)

    if len(report_lines) == 1:
        final_report = "Все необходимые продукты были в достаточном количестве."
    else:
        final_report = "\n".join(report_lines)
        
    final_text = (
        f"*{recipe['name']}*\n\n{final_report}\n\nПриятного аппетита!"
    )
        
    if query.message.photo:
        await query.edit_message_caption(
            caption=final_text,
            parse_mode='Markdown',
            reply_markup=None
        )
    else:
        await query.edit_message_text(
            text=final_text,
            parse_mode='Markdown',
            reply_markup=None
        )

# --- Вспомогательные функции ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение."""
    help_text = (
        "🤖 *Я твой кулинарный помощник! Вот что я умею:*\n\n"
        "● *Мой холодильник* - управляй списком продуктов, которые у тебя есть. Добавляй и удаляй их, чтобы я знал, из чего тебе готовить.\n\n"
        "● *Мое оборудование* - укажи, какая кухонная техника у тебя есть, чтобы я подбирал рецепты, которые ты точно сможешь приготовить.\n\n"
        "● *Подобрать рецепт* - главный раздел! Я найду лучшие блюда на основе твоих продуктов, оборудования и предпочтений, хранящихся в базе данных.\n\n"
        "Для начала работы используй кнопки в меню ниже."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main() -> None:
    """Основная функция для запуска бота."""
    
    global ALL_PRODUCTS_CACHE, ALL_EQUIPMENT_CACHE
    ALL_PRODUCTS_CACHE = db.load_products_cache()
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
                MessageHandler(filters.Regex("^Добавить оборудование$"), add_equipment_interactive),
                MessageHandler(filters.Regex("^Удалить оборудование$"), remove_equipment_interactive),
            ],
            SELECTING_EQUIPMENT_KEYBOARD: [
                CallbackQueryHandler(done_selecting_equipment, pattern="^equip_done$"),
                CallbackQueryHandler(select_equipment_callback, pattern="^equip_"),
            ],
            SELECTING_EQUIPMENT_FOR_REMOVAL: [
                CallbackQueryHandler(done_removing_equipment, pattern="^del_equip_done$"),
                CallbackQueryHandler(select_equipment_for_removal_callback, pattern="^del_equip_"),
            ],
        },
        fallbacks=common_fallbacks,
        per_message=False,
    )
    
    # Ветка 3: Управление предпочтениями и ограничениями
    preferences_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Предпочтения и ограничения$"), manage_preferences)],
        states={
            MANAGE_PREFERENCES: [
                MessageHandler(filters.Regex("^Посмотреть мои данные$"), view_preferences_and_constraints),
                MessageHandler(filters.Regex("^Добавить предпочтение$"), add_preference_prompt),
                MessageHandler(filters.Regex("^Добавить ограничение$"), add_constraint_prompt),
                MessageHandler(filters.Regex("^Удалить запись$"), delete_type_prompt),
            ],
            ADD_PREFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_preference)],
            ADD_CONSTRAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_constraint)],
            CHOOSE_DELETE_TYPE: [
                MessageHandler(filters.Regex("^Предпочтения$"), list_preferences_for_deletion),
                MessageHandler(filters.Regex("^Ограничения$"), list_constraints_for_deletion),
            ],
            AWAIT_PREFERENCE_DELETION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_preferences_by_number)],
            AWAIT_CONSTRAINT_DELETION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_constraints_by_number)],
        },
        fallbacks=common_fallbacks,
    )
    
    # Ветка 4: Подбор рецепта
    recipe_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Подобрать рецепт$"), prompt_recipe_type)],
        states={
            CHOOSE_RECIPE_TYPE: [MessageHandler(filters.Regex("^(Только из имеющихся продуктов|Добавить 1-2 недостающих ингредиента)$"), prompt_for_time)],
            FILTER_BY_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_and_show_recipes)],
        },
        fallbacks=common_fallbacks,
        per_message=False,
    )
    
    # Регистрация всех обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", main_menu))
    application.add_handler(MessageHandler(filters.Regex("^Помощь$"), help_command))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(storage_conv)
    application.add_handler(equipment_conv)
    application.add_handler(preferences_conv)
    application.add_handler(recipe_conv)

    application.add_handler(CallbackQueryHandler(recipe_details, pattern="^recipe_"))
    application.add_handler(CallbackQueryHandler(cook_recipe_and_update_storage, pattern="^cook_"))
    application.add_handler(CallbackQueryHandler(back_to_main_menu_inline, pattern="^main_menu_back$"))

    application.run_polling()

if __name__ == "__main__":
    main()
