from telegram import ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext, MessageHandler, ConversationHandler, CallbackQueryHandler, filters
from telegram import ReplyKeyboardMarkup
import db
import logging
import os
from dotenv import load_dotenv
import re
from decimal import Decimal, InvalidOperation

# Загружаем переменные из .env файла в окружение
load_dotenv()

# Загружаем логин из окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Логгинг
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ALL_PRODUCTS_CACHE = set()
ALL_EQUIPMENT_CACHE = set()

# КХ
(
    MANAGE_STORAGE,
    ADD_PRODUCTS,
    REMOVE_PRODUCTS,
    MANAGE_EQUIPMENT,
    ADD_EQUIPMENT,
    REMOVE_EQUIPMENT,
    CHOOSE_RECIPE_TYPE,
    FILTER_BY_TIME,
    FIND_RECIPES
) = range(9)

# --- Основное меню ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Главная функция. Приветствует пользователя, показывает основное меню 
    и служит точкой выхода для всех ConversationHandler'ов.
    """
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    db.ensure_user_exists(user_id, first_name)

    reply_keyboard = [
        ["Мой холодильник", "Мое оборудование"],
        ["Подобрать рецепт"], 
        ["Помощь"],
    ]

    await update.message.reply_text(
        "👋 Добро пожаловать! Я ваш кулинарный помощник.\n\nВыберите действие в меню ниже:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
    
    return ConversationHandler.END

# --- Управление кухней ---

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
    await update.message.reply_text("Введите оборудование, которое хотите добавить, через запятую:",
                                    reply_markup=ReplyKeyboardRemove())
    return ADD_EQUIPMENT

async def add_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление оборудования с валидацией."""
    user_id = update.message.from_user.id
    input_equipment = {e.strip().lower() for e in update.message.text.split(",") if e.strip()}
    
    valid_equipment = input_equipment.intersection(ALL_EQUIPMENT_CACHE)
    invalid_equipment = input_equipment.difference(ALL_EQUIPMENT_CACHE)
    
    if valid_equipment:
        db.add_user_equipment(user_id, valid_equipment)
        await update.message.reply_text(f"✅ Добавлено: {', '.join(sorted(valid_equipment))}")
    
    if invalid_equipment:
        await update.message.reply_text(f"❌ Не найдено в справочнике: {', '.join(sorted(invalid_equipment))}")

    return await manage_equipment(update, context)

async def remove_equipment_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите оборудование, которое хотите удалить, через запятую:",
                                    reply_markup=ReplyKeyboardRemove())
    return REMOVE_EQUIPMENT

async def remove_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаление оборудования с валидацией."""
    user_id = update.message.from_user.id
    input_equipment = {e.strip().lower() for e in update.message.text.split(",") if e.strip()}
    
    valid_equipment = input_equipment.intersection(ALL_EQUIPMENT_CACHE)
    invalid_equipment = input_equipment.difference(ALL_EQUIPMENT_CACHE)
    
    if valid_equipment:
        db.remove_user_equipment(user_id, valid_equipment)
        await update.message.reply_text(f"✅ Удалено: {', '.join(sorted(valid_equipment))}")
    
    if invalid_equipment:
        await update.message.reply_text(f"❌ Не найдено в справочнике: {', '.join(sorted(invalid_equipment))}")

    return await manage_equipment(update, context)

# --- Управление холодильником ---

async def manage_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню управления холодильником."""
    reply_keyboard = [
        ["Посмотреть продукты"],
        ["Добавить продукты", "Удалить продукты"],
        ["Назад в меню"],
    ]
    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
    )
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
    Возвращает список словарей: [{'name': ..., 'quantity': ..., 'unit': ...}]
    """
    parsed_products = []
    items = [item.strip() for item in text.split(',') if item.strip()]
    
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
    """Запрос на добавление продуктов."""
    await update.message.reply_text("Введи продукты, которые хочешь добавить, через запятую:",
                                    reply_markup=ReplyKeyboardRemove())
    return ADD_PRODUCTS

async def add_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(update.message.text)
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
    """Запрос на удаление продуктов."""
    await update.message.reply_text("Введи продукты, которые хочешь удалить, через запятую:",
                                    reply_markup=ReplyKeyboardRemove())
    return REMOVE_PRODUCTS

async def remove_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    
    parsed_input = parse_products_with_quantity(update.message.text)
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
async def choose_recipe_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Первый шаг подбора: выбор типа."""
    recipe_type = update.message.text
    if recipe_type not in ["Только из имеющихся продуктов", "Добавить 1-2 недостающих ингредиента"]:
         reply_keyboard = [
            ["Только из имеющихся продуктов"],
            ["Добавить 1-2 недостающих ингредиента"],
            ["Назад в меню"],
        ]
         await update.message.reply_text("Как будем подбирать рецепт?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
         return CHOOSE_RECIPE_TYPE

    context.user_data["recipe_type"] = recipe_type
    
    await update.message.reply_text(
        "Введите максимальное время приготовления в минутах (например, 30). Если время неважно, введите 0.",
        reply_markup=ReplyKeyboardRemove()
    )
    return FILTER_BY_TIME


def _calculate_preference_score(recipe: dict, preferences: dict) -> int:
    """Вспомогательная функция для подсчета 'очков' рецепта для сортировки."""
    score = 0
    recipe_ingredients = {ing.lower() for ing in recipe.get('ingredients', {}).keys()}
    score += len(recipe_ingredients.intersection(preferences.get('like', set())))
    score -= len(recipe_ingredients.intersection(preferences.get('avoid', set())))
    return score
    
async def prompt_for_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["recipe_type"] = update.message.text
    
    time_keyboard = ReplyKeyboardMarkup(
        [["Неважно"]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    
    await update.message.reply_text(
        "Введите максимальное время приготовления в минутах (например, 30). Если время неважно, введите 0.",
        reply_markup=time_keyboard
    )
    return FILTER_BY_TIME

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

# БУДЕТ ЗАМЕНЕНО НА ВЫЗОВ LLM
def find_matching_recipes(user_products: dict, user_equipment: set, forbidden_products: set, recipe_type: str, max_time: int, all_recipes: list) -> list:
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


async def find_and_show_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальный шаг: поиск, СОРТИРОВКА и отображение рецептов."""
    user_input = update.message.text
    if user_input == "Неважно":
        max_time = 0
    else:
        try:
            max_time = int(user_input)
        except (ValueError, TypeError):
            await update.message.reply_text("Это не похоже на число. Пожалуйста, введите время в минутах (например, 30) или нажмите 'Неважно'.")
            return FILTER_BY_TIME
    
    user_id = update.message.from_user.id
    
    user_products = db.get_user_products(user_id)
    user_equipment = db.get_user_equipment(user_id)
    forbidden_products = db.get_user_food_constraints(user_id)
    user_preferences = db.get_user_product_preferences(user_id)
    
    all_recipes = db.get_all_recipes()
    recipe_type = context.user_data.get("recipe_type")
    
    recipes = find_matching_recipes(user_products, user_equipment, forbidden_products, recipe_type, max_time, all_recipes)

    recipes.sort(key=lambda r: _calculate_preference_score(r, user_preferences), reverse=True)

    reply_keyboard = [
        ["Мой холодильник", "Мое оборудование"],
        ["Подобрать рецепт"], 
        ["Помощь"],
    ]

    if not recipes:
        await update.message.reply_text("К сожалению, подходящих рецептов не найдено.",
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),)
    else:
        keyboard = []
        for recipe in recipes:
            button = [InlineKeyboardButton(recipe["name"], callback_data=f"recipe_{recipe['id']}")]
            keyboard.append(button)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Вот что я нашел:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),)
    

    context.user_data.clear()
    
    return ConversationHandler.END


async def recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображение полной информации о рецепте."""
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
        [InlineKeyboardButton("✅ Приготовить (списать ингредиенты)", callback_data=f"cook_{recipe_id}")]
    ])

    await query.edit_message_text(
        text=text, 
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    
async def cook_recipe_and_update_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатие кнопки "Приготовить".
    Списывает ингредиенты из холодильника пользователя.
    """
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

    final_report = "\n".join(report_lines)
    await query.edit_message_text(
        text=f"*{recipe['name']}*\n\n{final_report}\n\nПриятного аппетита!" ,
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
    
    global ALL_PRODUCTS_CACHE, ALL_EQUIPMENT_CACHE
    ALL_PRODUCTS_CACHE = db.get_all_product_names()
    ALL_EQUIPMENT_CACHE = db.get_all_equipment_names()
    if not ALL_PRODUCTS_CACHE:
        logger.warning("Справочник продуктов пуст! Проверка названий не будет работать.")
    else:
        logger.info(f"Кэш продуктов загружен: {len(ALL_PRODUCTS_CACHE)} наименований.")
    if not ALL_EQUIPMENT_CACHE:
        logger.warning("Справочник оборудования пуст! Проверка названий не будет работать.")
    else:
        logger.info(f"Кэш оборудования загружен: {len(ALL_EQUIPMENT_CACHE)} наименований.")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Ветка 1: Управление холодильником
    storage_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Мой холодильник$"), manage_storage)],
        states={
            MANAGE_STORAGE: [
                MessageHandler(filters.Regex("^Посмотреть продукты$"), view_products),
                MessageHandler(filters.Regex("^Добавить продукты$"), add_products_prompt),
                MessageHandler(filters.Regex("^Удалить продукты$"), remove_products_prompt),
            ],
            ADD_PRODUCTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_products)],
            REMOVE_PRODUCTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_products)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^Назад в меню$"), start)
        ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
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
            ADD_EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_equipment)],
            REMOVE_EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_equipment)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^Назад в меню$"), start)
        ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )
    
        # Ветка 3: Подбор рецепта
    recipe_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Подобрать рецепт$"), choose_recipe_type)],
        states={
            CHOOSE_RECIPE_TYPE: [MessageHandler(filters.Regex("^(Только из имеющихся продуктов|Добавить 1-2 недостающих ингредиента)$"), prompt_for_time)],
            FILTER_BY_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_and_show_recipes)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^Назад в меню$"), start)
        ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )
    
    # 4. Все обработчики в приложении
    
    # Команды верхнего уровня
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(filters.Regex("^Помощь$"), help_command))

    # Ветки диалогов
    application.add_handler(storage_conv)
    application.add_handler(equipment_conv)
    application.add_handler(recipe_conv)

    # Обработчики для inline-кнопок (рецепты)
    application.add_handler(CallbackQueryHandler(recipe_details, pattern="^recipe_"))
    application.add_handler(CallbackQueryHandler(cook_recipe_and_update_storage, pattern="^cook_"))

    application.run_polling()

if __name__ == "__main__":
    main()
