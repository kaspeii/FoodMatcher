# db.py (Тестовая имитация / Mock)
import logging
from decimal import Decimal

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ИМИТАЦИЯ БАЗЫ ДАННЫХ В ПАМЯТИ ---

# --- Справочники ---

# Категории продуктов
_categories = {
    1: 'молочные продукты',
    2: 'овощи',
    3: 'фрукты',
    4: 'мясо',
    5: 'бакалея',
    6: 'напитки',
    7: 'хлебобулочные изделия',
    8: 'морепродукты'
}

# Продукты с привязкой к категориям
_products = {
    # id: { name, category_id, per_unit, calories, ... }
    1: {'name': 'яйцо', 'category_id': 1, 'per_unit': '1pc', 'calories': Decimal('70'), 'protein': Decimal('6'), 'fat': Decimal('5'), 'carbs': Decimal('0.5')},
    2: {'name': 'молоко', 'category_id': 1, 'per_unit': '100ml', 'calories': Decimal('60'), 'protein': Decimal('3.5'), 'fat': Decimal('3.2'), 'carbs': Decimal('4.8')},
    3: {'name': 'соль', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('0'), 'protein': Decimal('0'), 'fat': Decimal('0'), 'carbs': Decimal('0')},
    4: {'name': 'растительное масло', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('884'), 'protein': Decimal('0'), 'fat': Decimal('100'), 'carbs': Decimal('0')},
    5: {'name': 'помидоры', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('18'), 'protein': Decimal('0.9'), 'fat': Decimal('0.2'), 'carbs': Decimal('3.9')},
    6: {'name': 'огурцы', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('15'), 'protein': Decimal('0.7'), 'fat': Decimal('0.1'), 'carbs': Decimal('3.6')},
    7: {'name': 'красный лук', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('40'), 'protein': Decimal('1.1'), 'fat': Decimal('0.1'), 'carbs': Decimal('9.3')},
    8: {'name': 'фета', 'category_id': 1, 'per_unit': '100g', 'calories': Decimal('264'), 'protein': Decimal('14'), 'fat': Decimal('21'), 'carbs': Decimal('4.1')},
    9: {'name': 'оливки', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('115'), 'protein': Decimal('0.8'), 'fat': Decimal('11'), 'carbs': Decimal('6')},
    10: {'name': 'оливковое масло', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('884'), 'protein': Decimal('0'), 'fat': Decimal('100'), 'carbs': Decimal('0')},
    11: {'name': 'куриная грудка', 'category_id': 4, 'per_unit': '100g', 'calories': Decimal('165'), 'protein': Decimal('31'), 'fat': Decimal('3.6'), 'carbs': Decimal('0')},
    12: {'name': 'рис', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('130'), 'protein': Decimal('2.7'), 'fat': Decimal('0.3'), 'carbs': Decimal('28')},
    13: {'name': 'соевый соус', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('53'), 'protein': Decimal('8'), 'fat': Decimal('0.6'), 'carbs': Decimal('5.6')},
    14: {'name': 'овощи', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('65'), 'protein': Decimal('2.9'), 'fat': Decimal('0.4'), 'carbs': Decimal('14')},
    15: {'name': 'кабачок', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('17'), 'protein': Decimal('1.2'), 'fat': Decimal('0.3'), 'carbs': Decimal('3.1')},
    16: {'name': 'баклажан', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('25'), 'protein': Decimal('1'), 'fat': Decimal('0.2'), 'carbs': Decimal('6')},
    17: {'name': 'лук', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('40'), 'protein': Decimal('1.1'), 'fat': Decimal('0.1'), 'carbs': Decimal('9.3')},
    18: {'name': 'морковь', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('41'), 'protein': Decimal('0.9'), 'fat': Decimal('0.2'), 'carbs': Decimal('10')},
    19: {'name': 'чеснок', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('149'), 'protein': Decimal('6'), 'fat': Decimal('0.5'), 'carbs': Decimal('33')},
    20: {'name': 'томатная паста', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('82'), 'protein': Decimal('4.3'), 'fat': Decimal('0.5'), 'carbs': Decimal('19')},
    21: {'name': 'хлеб', 'category_id': 7, 'per_unit': '100g', 'calories': Decimal('265'), 'protein': Decimal('9'), 'fat': Decimal('3.2'), 'carbs': Decimal('49')},
    22: {'name': 'сыр', 'category_id': 1, 'per_unit': '100g', 'calories': Decimal('402'), 'protein': Decimal('25'), 'fat': Decimal('33'), 'carbs': Decimal('1.3')},
    23: {'name': 'картофель', 'category_id': 2, 'per_unit': '100g', 'calories': Decimal('77'), 'protein': Decimal('2'), 'fat': Decimal('0.1'), 'carbs': Decimal('17')},
    24: {'name': 'арахис', 'category_id': 5, 'per_unit': '100g', 'calories': Decimal('567'), 'protein': Decimal('26'), 'fat': Decimal('49'), 'carbs': Decimal('16')},
    25: {'name': 'креветки', 'category_id': 8, 'per_unit': '100g', 'calories': Decimal('99'), 'protein': Decimal('24'), 'fat': Decimal('0.3'), 'carbs': Decimal('0.2')},
    26: {'name': 'гречка', 'category_id': 7, 'per_unit': '100g', 'calories': Decimal('343'), 'protein': Decimal('13'), 'fat': Decimal('3.4'), 'carbs': Decimal('72')},
}

# Для удобства создадим обратные маппинги и множества
_product_name_to_id = {v['name']: k for k, v in _products.items()}
_existing_product_names = set(_product_name_to_id.keys())

# Оборудование
_equipment = {
    1: 'сковорода',
    2: 'венчик',
    3: 'миска',
    4: 'нож',
    5: 'кастрюля',
    6: 'духовка',
    7: 'блендер',
    8: 'мультиварка',
}
_equipment_name_to_id = {v: k for k, v in _equipment.items()}
_existing_equipment_names = set(_equipment_name_to_id.keys())


# Рецепты
_recipes = [
    {
        "id": 1,
        "name": "Классический омлет",
        "description": "Простой и быстрый завтрак.",
        "ingredients": {"яйцо": "3 шт", "молоко": "50 мл", "соль": "по вкусу", "растительное масло": "1 ст.л."},
        "instructions": "1. Взбейте яйцо с молоком и солью. 2. Разогрейте сковороду с маслом. 3. Вылейте яичную смесь и готовьте до готовности.",
        "equipment": "Сковорода, венчик",
        "cooking_time_minutes": 10,
        "tags": {'завтрак', 'быстро', 'вегетарианское'},
    },
    {
        "id": 2,
        "name": "Греческий салат",
        "description": "Свежий и легкий салат.",
        "ingredients": {"помидоры": "2 шт", "огурцы": "1 шт", "красный лук": "0.5 шт", "фета": "100 г", "оливки": "50 г", "оливковое масло": "2 ст.л."},
        "instructions": "1. Нарежьте овощи. 2. Добавьте фету и оливки. 3. Заправьте оливковым маслом.",
        "equipment": "Миска, нож",
        "cooking_time_minutes": 15,
        "tags": {'салат', 'быстро', 'вегетарианское', 'лето'},
    },
    {
        "id": 3,
        "name": "Куриная грудка с рисом",
        "description": "Полноценный обед.",
        "ingredients": {"куриная грудка": "200 г", "рис": "100 г", "соевый соус": "30 мл", "овощи": "150 г"},
        "instructions": "1. Отварите рис. 2. Обжарьте куриную грудку с овощами. 3. Добавьте соевый соус и потушите пару минут.",
        "equipment": "Сковорода, кастрюля",
        "cooking_time_minutes": 30,
        "tags": {'обед', 'основное блюдо', 'курица'},
    },
    {
        "id": 4,
        "name": "Овощное рагу",
        "description": "Сытное веганское блюдо.",
        "ingredients": {"кабачок": "1 шт", "баклажан": "1 шт", "помидоры": "2 шт", "лук": "1 шт", "морковь": "1 шт", "чеснок": "2 зубчика", "томатная паста": "2 ст.л."},
        "instructions": "1. Нарежьте все овощи кубиками. 2. Обжарьте лук и морковь. 3. Добавьте остальные овощи и томатную пасту. 4. Тушите до готовности.",
        "equipment": "Глубокая сковорода или кастрюля",
        "cooking_time_minutes": 40,
        "tags": {'веганское', 'вегетарианское', 'рагу', 'овощи', 'основное блюдо'},
    },
    {
        "id": 5,
        "name": "Жареная картошка",
        "description": "Просто и вкусно.",
        "ingredients": {"картофель": "500 г", "лук": "1 шт", "растительное масло": "3 ст.л.", "соль": "по вкусу"},
        "instructions": "1. Почистить и нарезать картофель и лук. 2. Разогреть масло на сковороде. 3. Жарить картофель до золотистой корочки, в конце добавить лук и соль.",
        "equipment": "Сковорода",
        "cooking_time_minutes": 25,
        "tags": {'гарнир', 'просто', 'веганское', 'вегетарианское'},
    }
]
_recipes_by_id = {recipe['id']: recipe for recipe in _recipes}

# --- Данные пользователей ---

# Счетчик для "auto-increment" ID
_next_user_id = 1
_next_preference_id = 1
_next_constraint_id = 1

# Таблица "users": { telegram_id: {'id': internal_id, 'first_name': 'John'} }
_users = {}

# Таблица "user_products" (Холодильник): { telegram_id: { 'продукт': {'quantity': Decimal, 'unit': 'str'} } }
_user_products = {}

# Таблица "user_equipment": { telegram_id: {equipment_id_1, equipment_id_2} }
_user_equipment = {}

# Таблица "user_preferences": { telegram_id: [ {'id': 1, 'note': 'люблю острое'}, ... ] }
_user_preferences = {}

# Таблица "user_food_constraints": { telegram_id: [{'product_id': int|None, 'category_id': int|None}, ...] }
_user_food_constraints = {}


# --- КОНЕЦ ИМИТАЦИИ БД ---


# --- Функции для работы с пользователями и их продуктами ---

def ensure_user_exists(telegram_id: int, first_name: str):
    """Имитация: создает пользователя со всеми связанными записями, если его нет."""
    global _next_user_id
    if telegram_id not in _users:
        _users[telegram_id] = {'id': _next_user_id, 'first_name': first_name}
        _user_products[telegram_id] = {}
        _user_equipment[telegram_id] = set()
        _user_food_constraints[telegram_id] = []
        _user_preferences[telegram_id] = [] 
        _next_user_id += 1
        logger.info(f"Mock DB: Создан новый пользователь с telegram_id {telegram_id}")

def get_user_products(telegram_id: int) -> dict:
    """Имитация: возвращает словарь продуктов пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    logger.info(f"Mock DB: Запрошен холодильник для telegram_id {telegram_id}")
    return _user_products.get(telegram_id, {})

def get_user_equipment(telegram_id: int) -> set:
    """Имитация: возвращает множество названий оборудования пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    logger.info(f"Mock DB: Запрошено оборудование для telegram_id {telegram_id}")
    equipment_ids = _user_equipment.get(telegram_id, set())
    return { _equipment[eq_id] for eq_id in equipment_ids }

def upsert_products_to_user(telegram_id: int, products_data: list):
    """
    Имитация: пакетное добавление/обновление продуктов пользователя.
    products_data - список словарей: [{'name': str, 'quantity': Decimal, 'unit': str}]
    """
    ensure_user_exists(telegram_id, "Mock User")
    fridge = _user_products.get(telegram_id)
    logger.info(f"Mock DB: UPSERT для telegram_id {telegram_id}, данные: {products_data}")

    for p_data in products_data:
        name = p_data['name'].lower()
        if name in _existing_product_names:
            fridge[name] = {
                'quantity': p_data.get('quantity'),
                'unit': p_data.get('unit')
            }

def remove_products_from_user(telegram_id: int, product_names: list):
    """Имитация: пакетное удаление продуктов пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    fridge = _user_products.get(telegram_id)
    logger.info(f"Mock DB: DELETE для telegram_id {telegram_id}, продукты: {product_names}")

    for name in product_names:
        if name.lower() in fridge:
            del fridge[name.lower()]

def add_user_equipment(telegram_id: int, equipment_names: set):
    """Имитация: добавляет оборудование пользователю."""
    ensure_user_exists(telegram_id, "Mock User")
    user_eq_set = _user_equipment.get(telegram_id)
    logger.info(f"Mock DB: ADD EQUIPMENT для telegram_id {telegram_id}, оборудование: {equipment_names}")
    
    for name in equipment_names:
        eq_id = _equipment_name_to_id.get(name.lower())
        if eq_id:
            user_eq_set.add(eq_id)

def remove_user_equipment(telegram_id: int, equipment_names: set):
    """Имитация: удаляет оборудование у пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    user_eq_set = _user_equipment.get(telegram_id)
    logger.info(f"Mock DB: REMOVE EQUIPMENT для telegram_id {telegram_id}, оборудование: {equipment_names}")
    
    ids_to_remove = set()
    for name in equipment_names:
        eq_id = _equipment_name_to_id.get(name.lower())
        if eq_id:
            ids_to_remove.add(eq_id)
            
    user_eq_set.difference_update(ids_to_remove)

# --- Функции для работы с рецептами ---

def get_all_recipes() -> list[dict]:
    """Имитация: просто возвращает заранее подготовленный список _recipes."""
    logger.info("Mock DB: Запрошены все рецепты")
    return _recipes

def get_recipe_by_id(recipe_id: int) -> dict | None:
    """Имитация: ищет рецепт в словаре _recipes_by_id."""
    logger.info(f"Mock DB: Запрошен рецепт с ID {recipe_id}")
    return _recipes_by_id.get(recipe_id)


# --- Функции для получения справочников ---

def load_products_cache() -> dict:
    """
    Имитация: создает кэш с полной информацией о продуктах,
    аналогично `load_products_cache_improved()` для реальной БД.
    """
    logger.info("Mock DB: Загружен полный кэш продуктов")
    
    products_cache = {}
    for product_id, product_data in _products.items():
        name = product_data['name'].lower()
        # Создаем копию, чтобы не менять исходный мок
        info = product_data.copy() 
        # Удаляем имя, так как оно становится ключом
        del info['name'] 
        products_cache[name] = info
        
    return products_cache

def get_all_equipment_names() -> set:
    """Имитация: возвращает set со всеми известными названиями оборудования."""
    logger.info("Mock DB: Запрошен справочник всего оборудования")
    return _existing_equipment_names

def get_user_preferences_with_ids(telegram_id: int) -> dict:
    """Имитация: возвращает список словарей предпочтений пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    logger.info(f"Mock DB: Запрошены предпочтения с ID для telegram_id {telegram_id}")
    return _user_preferences.get(telegram_id)

def get_user_food_constraints_with_ids(telegram_id: int) -> list[dict]:
    """Имитация: возвращает список словарей ограничений пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    logger.info(f"Mock DB: Запрошены ограничения с ID для telegram_id {telegram_id}")
    return _user_food_constraints.get(telegram_id, [])

def add_user_preference(telegram_id: int, note: str):
    """Имитация: добавляет новое текстовое предпочтение."""
    global _next_preference_id
    ensure_user_exists(telegram_id, "Mock User")
    _user_preferences[telegram_id].append({'id': _next_preference_id, 'note': note})
    logger.info(f"Mock DB: Добавлено предпочтение ID {_next_preference_id} для telegram_id {telegram_id}: '{note}'")
    _next_preference_id += 1

def add_user_food_constraint(telegram_id: int, note: str):
    """Имитация: добавляет новое текстовое ограничение."""
    global _next_constraint_id
    ensure_user_exists(telegram_id, "Mock User")
    _user_food_constraints[telegram_id].append({'id': _next_constraint_id, 'note': note})
    logger.info(f"Mock DB: Добавлено ограничение ID {_next_constraint_id} для telegram_id {telegram_id}: '{note}'")
    _next_constraint_id += 1

def delete_user_preferences_by_ids(telegram_id: int, note_ids: list[int]):
    """Имитация: удаляет предпочтения по списку их ID."""
    ensure_user_exists(telegram_id, "Mock User")
    if not note_ids: return
    
    current_prefs = _user_preferences.get(telegram_id, [])
    ids_to_delete_set = set(note_ids)
    
    _user_preferences[telegram_id] = [p for p in current_prefs if p['id'] not in ids_to_delete_set]
    logger.info(f"Mock DB: Удалены предпочтения с ID {note_ids} для telegram_id {telegram_id}")

def delete_user_food_constraints_by_ids(telegram_id: int, note_ids: list[int]):
    """Имитация: удаляет ограничения по списку их ID."""
    ensure_user_exists(telegram_id, "Mock User")
    if not note_ids: return

    current_constraints = _user_food_constraints.get(telegram_id, [])
    ids_to_delete_set = set(note_ids)
    
    _user_food_constraints[telegram_id] = [c for c in current_constraints if c['id'] not in ids_to_delete_set]
    logger.info(f"Mock DB: Удалены ограничения с ID {note_ids} для telegram_id {telegram_id}")

def clear_user_preferences(telegram_id: int):
    """Имитация: удаляет все предпочтения пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    _user_preferences[telegram_id] = []
    logger.info(f"Mock DB: Очищены все предпочтения для telegram_id {telegram_id}")

def clear_user_food_constraints(telegram_id: int):
    """Имитация: удаляет все ограничения пользователя."""
    ensure_user_exists(telegram_id, "Mock User")
    _user_food_constraints[telegram_id] = []
    logger.info(f"Mock DB: Очищены все ограничения для telegram_id {telegram_id}")