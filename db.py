# db.py
import os
import psycopg2
from psycopg2.extras import DictCursor, execute_batch
from dotenv import load_dotenv
import logging
from decimal import Decimal

# Загрузка переменных окружения
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Устанавливает соединение с базой данных."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        return None

# --- Функции для работы с пользователями и их продуктами ---

def ensure_user_exists(telegram_id: int, first_name: str):
    """
    Проверяет, есть ли пользователь в БД. Если нет - создает новую запись.
    """
    sql = """
        INSERT INTO users (telegram_id, first_name)
        VALUES (%s, %s)
        ON CONFLICT (telegram_id) DO NOTHING;
    """
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, first_name))
        conn.close()

def get_user_products(telegram_id: int) -> dict:
    """
    Возвращает словарь продуктов пользователя с количеством и ед. измерения.
    Формат: {'молоко': {'quantity': Decimal('1.0'), 'unit': 'л'}, 'хлеб': {'quantity': None, 'unit': None}}
    """
    sql = """
        SELECT p.id AS product_id, p.name, up.quantity, up.unit
        FROM products p
        JOIN user_products up ON p.id = up.product_id
        JOIN users u ON u.id = up.user_id
        WHERE u.telegram_id = %s;
    """
    products = {}
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (telegram_id,))
                for row in cur.fetchall():
                    product_name_db = row['name']
                    product_key = product_name_db.lower()
                    products[product_key] = {
                        'product_id': row['product_id'],
                        'db_name': product_name_db,
                        'quantity': row['quantity'],
                        'unit': row['unit']
                    }
        conn.close()
    return products

def get_user_equipment(telegram_id: int) -> set:
    """Возвращает множество названий оборудования пользователя."""
    sql = """
        SELECT e.name
        FROM equipment e
        JOIN user_equipment ue ON e.id = ue.equipment_id
        JOIN users u ON u.id = ue.user_id
        WHERE u.telegram_id = %s;
    """
    equipment = set()
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id,))
                for row in cur.fetchall():
                    equipment.add(row[0].lower())
        conn.close()
    return equipment

def upsert_products_to_user(telegram_id: int, products_data: list):
    """
    Пакетное добавление/обновление продуктов пользователя.
    products_data - список словарей: [{'product_id': int, 'quantity': Decimal, 'unit': str}]
    """
    sql = """
        INSERT INTO user_products (user_id, product_id, quantity, unit)
        VALUES (
            (SELECT id FROM users WHERE telegram_id = %(telegram_id)s),
            %(product_id)s,
            %(quantity)s,
            %(unit)s
        )
        ON CONFLICT (user_id, product_id) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            unit = EXCLUDED.unit;
    """
    conn = get_db_connection()
    if conn and products_data:
        for p in products_data:
            p['telegram_id'] = telegram_id
        
        with conn:
            with conn.cursor() as cur:
                execute_batch(cur, sql, products_data)
        conn.close()

def remove_products_from_user(telegram_id: int, product_ids: list[int]):
    """Пакетное удаление продуктов пользователя по списку идентификаторов."""
    sql = """
        DELETE FROM user_products
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        AND product_id = ANY(%s);
    """
    conn = get_db_connection()
    if conn and product_ids:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, product_ids))
        conn.close()

def add_user_equipment(telegram_id: int, equipment_names: set):
    """Добавляет оборудование пользователю."""
    sql = """
        INSERT INTO user_equipment (user_id, equipment_id)
        SELECT 
            (SELECT id FROM users WHERE telegram_id = %s),
            e.id
        FROM equipment e WHERE e.name = ANY(%s)
        ON CONFLICT (user_id, equipment_id) DO NOTHING;
    """
    conn = get_db_connection()
    if conn and equipment_names:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, list(equipment_names)))
        conn.close()

def remove_user_equipment(telegram_id: int, equipment_names: set):
    """Удаляет оборудование у пользователя."""
    sql = """
        DELETE FROM user_equipment
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        AND equipment_id IN (SELECT id FROM equipment WHERE name = ANY(%s));
    """
    conn = get_db_connection()
    if conn and equipment_names:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, list(equipment_names)))
        conn.close()

# --- функции для предпочтений и ограничений ---

def get_user_preferences_with_ids(telegram_id: int) -> list[dict]:
    """Возвращает список предпочтений пользователя, каждое с его ID."""
    sql = """
        SELECT id, note FROM user_product_preferences
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        ORDER BY id;
    """
    notes = []
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (telegram_id,))
                notes = cur.fetchall()
        conn.close()
    return notes

def get_user_food_constraints_with_ids(telegram_id: int) -> list[dict]:
    """Возвращает список ограничений пользователя, каждое с его ID."""
    sql = """
        SELECT id, note FROM user_food_constraints
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        ORDER BY id;
    """
    notes = []
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (telegram_id,))
                notes = cur.fetchall()
        conn.close()
    return notes

def add_user_preference(telegram_id: int, note: str):
    """Добавляет новое текстовое предпочтение пользователю."""
    sql = """
        INSERT INTO user_product_preferences (user_id, note)
        VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s);
    """
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, note))
        conn.close()

def add_user_food_constraint(telegram_id: int, note: str):
    """Добавляет новое текстовое ограничение пользователю."""
    sql = """
        INSERT INTO user_food_constraints (user_id, note)
        VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s);
    """
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, note))
        conn.close()

def delete_user_preferences_by_ids(telegram_id: int, note_ids: list[int]):
    """Удаляет указанные предпочтения пользователя."""
    if not note_ids:
        return
    sql = """
        DELETE FROM user_product_preferences
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND id = ANY(%s);
    """
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, note_ids))
        conn.close()

def delete_user_food_constraints_by_ids(telegram_id: int, note_ids: list[int]):
    """Удаляет указанные ограничения пользователя."""
    if not note_ids:
        return
    sql = """
        DELETE FROM user_food_constraints
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND id = ANY(%s);
    """
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, note_ids))
        conn.close()

def clear_user_preferences(telegram_id: int):
    """Удаляет ВСЕ текстовые предпочтения пользователя (для команды "все")."""
    sql = "DELETE FROM user_product_preferences WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s);"
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id,))
        conn.close()

def clear_user_food_constraints(telegram_id: int):
    """Удаляет ВСЕ текстовые ограничения пользователя (для команды "все")."""
    sql = "DELETE FROM user_food_constraints WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s);"
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id,))
        conn.close()

# --- Функции для работы с рецептами ---

def get_all_recipes() -> list[dict]:
    """
    Возвращает список всех рецептов из БД, собирая данные из связанных таблиц.
    """
    conn = get_db_connection()
    if not conn:
        return []

    recipes = {}
    with conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT
                    id,
                    name,
                    description,
                    instructions,
                    cooking_time_minutes,
                    equipment_raw AS equipment_raw
                FROM recipes
            """)
            for row in cur.fetchall():
                recipes[row['id']] = dict(row)
                recipes[row['id']]['ingredients'] = {}
                recipes[row['id']]['tags'] = set()

            # 2. ингредиенты
            cur.execute("""
                SELECT ri.recipe_id, p.name, ri.quantity_description
                FROM recipe_ingredients ri
                JOIN products p ON ri.product_id = p.id
            """)
            for row in cur.fetchall():
                if row['recipe_id'] in recipes:
                    recipes[row['recipe_id']]['ingredients'][row['name']] = row['quantity_description']

            # 3. теги
            cur.execute("""
                SELECT rt.recipe_id, t.name
                FROM recipe_tags rt
                JOIN tags t ON rt.tag_id = t.id
            """)
            for row in cur.fetchall():
                if row['recipe_id'] in recipes:
                    recipes[row['recipe_id']]['tags'].add(row['name'].lower())
            
            # 4. оборудование
            cur.execute("""
                SELECT e.name
                FROM recipe_equipment re
                JOIN equipment e ON re.equipment_id = e.id
            """)
            for row in cur.fetchall():
                if row['recipe_id'] in recipes:
                    recipes[row['recipe_id']]['equipment'].add(row['name'].lower())
    conn.close()
    
    return list(recipes.values())

def get_recipe_by_id(recipe_id: int) -> dict | None:
    """
    Возвращает один рецепт по его ID со всеми связанными данными.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # базовые данные
            cur.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    instructions,
                    cooking_time_minutes,
                    equipment_raw AS equipment_raw
                FROM recipes
                WHERE id = %s
                """,
                (recipe_id,),
            )
            record = cur.fetchone()
            if not record:
                return None

            recipe = dict(record)
            recipe["ingredients"] = {}
            recipe["tags"] = set()
            recipe["equipment"] = set()

            # ингредиенты
            cur.execute(
                """
                SELECT p.name, ri.quantity_description
                FROM recipe_ingredients ri
                JOIN products p ON ri.product_id = p.id
                WHERE ri.recipe_id = %s
                """,
                (recipe_id,),
            )
            for row in cur.fetchall():
                recipe["ingredients"][row[0]] = row[1]

            # теги
            cur.execute(
                """
                SELECT t.name
                FROM recipe_tags rt
                JOIN tags t ON rt.tag_id = t.id
                WHERE rt.recipe_id = %s
                """,
                (recipe_id,),
            )
            for row in cur.fetchall():
                recipe["tags"].add(row[0].lower())
            
            cur.execute(
                """
                SELECT e.name
                FROM recipe_equipment re
                JOIN equipment e ON re.equipment_id = e.id
                WHERE re.recipe_id = %s
                """,
                (recipe_id,),
            )
            for row in cur.fetchall():
                recipe["equipment"].add(row[0].lower())

        return recipe

    finally:
        conn.close()


# --- Функции для получения справочников ---

def load_products_cache() -> dict:
    """
    Загружает полную информацию о продуктах из БД для кэширования.
    
    Возвращает словарь следующей структуры:
    {
        'название_продукта': {
            'per_unit': '100g',
            'calories': 150.00,
            'protein': 5.50,
            'fat': 2.30,
            'carbs': 25.00,
            'category_id': 1
        },
        ...
    }
    """
    sql = "SELECT id, name, per_unit, calories, protein, fat, carbs, category_id FROM products;"
    products_cache = {}
    conn = get_db_connection()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    for row in rows:
                        product_id = row[0]
                        product_name_db = row[1]
                        product_key = product_name_db.lower()

                        products_cache[product_key] = {
                            'id': product_id,
                            'db_name': product_name_db,
                            'per_unit': row[2],
                            'calories': row[3],
                            'protein': row[4],
                            'fat': row[5],
                            'carbs': row[6],
                            'category_id': row[7]
                        }
        finally:
            conn.close()
            
    return products_cache

def get_all_equipment_names() -> set:
    """Возвращает множество всех названий оборудования из справочника `equipment`."""
    sql = "SELECT name FROM equipment;"
    equipment_names = set()
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur.fetchall():
                    equipment_names.add(row[0].lower())
        conn.close()
    return equipment_names


def preliminary_filter_recipes_db(
    telegram_id: int,
    recipe_type: str,
    max_time: int = 0,
) -> list[dict]:
    """
    Фильтруем рецепты прямо в Postgres:
    - оставляем только те, что укладываются по времени (если задано)
    - считаем, сколько ингредиентов у пользователя нет
    - в зависимости от recipe_type отбрасываем лишние

    recipe_type:
        "Только из имеющихся продуктов" -> missing_count = 0
        "Добавить 1-2 недостающих ингредиента" -> missing_count <= 2
    """
    conn = get_db_connection()
    if not conn:
        return []


    sql = """
    WITH user_inv AS (
        -- что есть у пользователя
        SELECT u.id AS user_id,
               up.product_id,
               up.quantity
        FROM users u
        JOIN user_products up ON up.user_id = u.id
        WHERE u.telegram_id = %s
    ),
    recipe_need AS (
        -- все ингредиенты всех рецептов, но сразу режем по времени
        SELECT r.id AS recipe_id,
               r.name,
               r.description,
               r.instructions,
               r.cooking_time_minutes,
               ri.product_id,
               ri.quantity AS need_qty,
               ri.unit     AS need_unit
        FROM recipes r
        JOIN recipe_ingredients ri ON ri.recipe_id = r.id
        WHERE (%s = 0 OR r.cooking_time_minutes IS NULL OR r.cooking_time_minutes <= %s)
    ),
    joined AS (
        -- к каждому требуемому продукту рецепта подкладываем, есть ли он у юзера
        SELECT
            rn.recipe_id,
            rn.name,
            rn.description,
            rn.instructions,
            rn.cooking_time_minutes,
            (ui.product_id IS NOT NULL AND ui.quantity >= rn.need_qty) AS user_has
        FROM recipe_need rn
        LEFT JOIN user_inv ui
               ON ui.product_id = rn.product_id
    )
    SELECT
        recipe_id,
        MAX(name) AS name,
        MAX(description) AS description,
        MAX(instructions) AS instructions,
        MAX(cooking_time_minutes) AS cooking_time_minutes,
        COUNT(*) FILTER (WHERE NOT user_has) AS missing_count
    FROM joined
    GROUP BY recipe_id
    ORDER BY recipe_id;
    """

    filtered_recipes = []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (telegram_id, max_time, max_time))
            rows = cur.fetchall()

            only_owned = (recipe_type == "✅ Только из имеющихся продуктов")
            allow_1_2 = (recipe_type == "🛒 Добавить 1-2 недостающих ингредиента")

            for row in rows:
                missing = row["missing_count"] or 0
                if only_owned and missing != 0:
                    continue
                if allow_1_2 and missing > 2:
                    continue
                
                filtered_recipes.append(dict(row))
            
            if not filtered_recipes:
                return []
            
            recipes_map = {recipe['recipe_id']: recipe for recipe in filtered_recipes}
            recipe_ids = list(recipes_map.keys())

            for recipe in recipes_map.values():
                recipe['ingredients'] = {}
                recipe['tags'] = set()
                recipe['equipment'] = set()
                recipe['id'] = recipe.pop('recipe_id')


            cur.execute(
                """
                SELECT ri.recipe_id, p.name, ri.quantity_description
                FROM recipe_ingredients ri
                JOIN products p ON ri.product_id = p.id
                WHERE ri.recipe_id = ANY(%s)
                """,
                (recipe_ids,),
            )
            for row in cur.fetchall():
                recipes_map[row['recipe_id']]['ingredients'][row['name']] = row['quantity_description']

            cur.execute(
                """
                SELECT rt.recipe_id, t.name
                FROM recipe_tags rt
                JOIN tags t ON rt.tag_id = t.id
                WHERE rt.recipe_id = ANY(%s)
                """,
                (recipe_ids,),
            )
            for row in cur.fetchall():
                recipes_map[row['recipe_id']]['tags'].add(row['name'].lower())

            cur.execute(
                """
                SELECT re.recipe_id, e.name
                FROM recipe_equipment re
                JOIN equipment e ON re.equipment_id = e.id
                WHERE re.recipe_id = ANY(%s)
                """,
                (recipe_ids,),
            )
            for row in cur.fetchall():
                recipes_map[row['recipe_id']]['equipment'].add(row['name'].lower())

            return list(recipes_map.values())

    finally:
        conn.close()

    return [] # На случай, если что-то пошло не так

def get_recipe_main_image(recipe_id: int) -> str | None:
    """Возвращает URL главного изображения рецепта."""
    sql = "SELECT image_url FROM recipes WHERE id = %s;"
    image_url = None
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (recipe_id,))
                result = cur.fetchone()
                if result:
                    image_url = result[0]
        conn.close()
    return image_url

def get_recipe_step_images(recipe_id: int) -> list[dict]:
    """Возвращает список пошаговых изображений для рецепта."""
    sql = """
        SELECT image_url, step_number
        FROM recipe_images
        WHERE recipe_id = %s
        ORDER BY step_number ASC;
    """
    images = []
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (recipe_id,))
                images = [dict(row) for row in cur.fetchall()]
        conn.close()
    return images

def get_recipe_nutrition(recipe_id: int) -> dict | None:
    """
    Возвращает КБЖУ и количество ингредиентов, не учтенных в подсчете, для одного рецепта по его ID.
    """
    sql = """
        SELECT
            calories,
            protein,
            fat,
            carbs,
            nutrition_missing
        FROM recipes
        WHERE id = %s;
    """
    conn = get_db_connection()
    if not conn:
        return None

    nutrition_info = None
    with conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, (recipe_id,))
            record = cur.fetchone()
            if record:
                nutrition_info = {
                    'calories': record['calories'] or Decimal('0.00'),
                    'protein': record['protein'] or Decimal('0.00'),
                    'fat': record['fat'] or Decimal('0.00'),
                    'carbs': record['carbs'] or Decimal('0.00'),
                    'nutrition_missing': record['nutrition_missing'] or 0
                }
    conn.close()
    return nutrition_info


def get_product_lifetime(category_id: int):
    sql_categories = f"""
                     SELECT shelf_life_days
                     FROM categories
                     WHERE id = %s;
                     """
    conn = get_db_connection()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql_categories, (category_id,))
                    result = cur.fetchone()
                    if result:
                        life_time = result[0]
        except Exception as e:
            logger.error(f"Error getting product category: {e}")
        finally:
            conn.close()

    return life_time

def get_product_added_at(telegram_id: int, product_id: int):
    """
    Возвращает дату добавления конкретного продукта конкретным пользователем.
    """
    sql_products = """
                     SELECT added_at
                     FROM user_products
                     WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
                       AND product_id = %s;
                   """

    conn = get_db_connection()
    added_at = None
    
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql_products, (telegram_id, product_id))
                    result = cur.fetchone()
                    if result:
                        added_at = result[0]
        except Exception as e:
            logger.error(f"Error getting product added_at: {e}")
        finally:
            conn.close()

    return added_at


def get_product_category(product_id: int):
    sql_categories = """
                     SELECT category_id
                     FROM products
                     WHERE id = %s;
                     """
    conn = get_db_connection()
    category = None
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql_categories, (product_id,))
                    result = cur.fetchone()
                    if result:
                        category = result[0]
        except Exception as e:
            logger.error(f"Error getting product category: {e}")
        finally:
            conn.close()

    return int(category) if category is not None else None
