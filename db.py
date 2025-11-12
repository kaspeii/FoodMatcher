
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
          VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING; \
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
          SELECT p.name, up.quantity, up.unit
          FROM products p
                   JOIN user_products up ON p.id = up.product_id
                   JOIN users u ON u.id = up.user_id
          WHERE u.telegram_id = %s; \
          """
    products = {}
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (telegram_id,))
                for row in cur.fetchall():
                    products[row['name']] = {
                        'quantity': row['quantity'],
                        'unit': row['unit']
                    }
        conn.close()
    return products


def get_user_product_preferences(telegram_id: int) -> dict:
    """
    Возвращает словарь с предпочтениями пользователя по продуктам.
    Формат: {'like': {'яблоки', 'сыр'}, 'avoid': {'лук'}}
    """
    sql = """
          SELECT p.name, upp.preference
          FROM products p
                   JOIN user_product_preferences upp ON p.id = upp.product_id
                   JOIN users u ON u.id = upp.user_id
          WHERE u.telegram_id = %s; \
          """
    preferences = {'like': set(), 'avoid': set()}
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(sql, (telegram_id,))
                for row in cur.fetchall():
                    if row['preference'] in preferences:
                        preferences[row['preference']].add(row['name'].lower())
        conn.close()
    return preferences


def get_user_equipment(telegram_id: int) -> set:
    """Возвращает множество названий оборудования пользователя."""
    sql = """
          SELECT e.name
          FROM equipment e
                   JOIN user_equipment ue ON e.id = ue.equipment_id
                   JOIN users u ON u.id = ue.user_id
          WHERE u.telegram_id = %s; \
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


def get_user_food_constraints(telegram_id: int) -> set:
    """
    Возвращает множество названий ВСЕХ продуктов, которые нельзя пользователю,
    включая продукты из запрещенных категорий.
    """
    # Запрос для продуктов, запрещенных напрямую
    sql_products = """
                   SELECT p.name
                   FROM products p
                            JOIN user_food_constraints ufc ON p.id = ufc.product_id
                            JOIN users u ON u.id = ufc.user_id
                   WHERE u.telegram_id = %s; \
                   """
    # Запрос для продуктов из запрещенных категорий
    sql_categories = """
                     SELECT p.name
                     FROM products p
                     WHERE p.category_id IN (SELECT ufc.category_id \
                                             FROM user_food_constraints ufc \
                                                      JOIN users u ON u.id = ufc.user_id \
                                             WHERE u.telegram_id = %s \
                                               AND ufc.category_id IS NOT NULL); \
                     """
    forbidden_products = set()
    conn = get_db_connection()
    if conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql_products, (telegram_id,))
                for row in cur.fetchall():
                    forbidden_products.add(row[0].lower())

                cur.execute(sql_categories, (telegram_id,))
                for row in cur.fetchall():
                    forbidden_products.add(row[0].lower())
        conn.close()
    return forbidden_products


def upsert_products_to_user(telegram_id: int, products_data: list):
    """
    Пакетное добавление/обновление продуктов пользователя.
    products_data - список словарей: [{'name': str, 'quantity': Decimal, 'unit': str}]
    """
    sql =""""
          INSERT INTO user_products (user_id, product_id, quantity, unit)
          VALUES ((SELECT id FROM users WHERE telegram_id = %(telegram_id)s),
                         (SELECT id FROM products WHERE name = %(name)s),
                         %(quantity)s,
                         %(unit)s
                 )...")
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

def remove_products_from_user(telegram_id: int, product_names: list):
    """Пакетное удаление продуктов пользователя по списку названий."""
    sql = """
        DELETE FROM user_products
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        AND product_id IN (SELECT id FROM products WHERE name = ANY(%s));
    """
    conn = get_db_connection()
    if conn and product_names:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (telegram_id, product_names))
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
                    # 1. базовые данные о рецептах
                    cur.execute(
                        "SELECT id, name, description, instructions, cooking_time_minutes, equipment FROM recipes")
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
            conn.close()

            return list(recipes.values())

        def get_recipe_by_id(recipe_id: int) -> dict | None:
            """
            Возвращает один рецепт по его ID со всеми связанными данными.
            """
            conn = get_db_connection()
            if not conn:
                return None

            recipe = None
            with conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    # 1. Базовые данные
                    cur.execute(
                        "SELECT id, name, description, instructions, cooking_time_minutes, equipment FROM recipes WHERE id = %s",
                        (recipe_id,))
                    record = cur.fetchone()
                    if not record:
                        conn.close()
                        return None

                    recipe = dict(record)
                    recipe['ingredients'] = {}
                    recipe['tags'] = set()

                    # 2. Ингредиенты
                    cur.execute("""
                                SELECT p.name, ri.quantity_description
                                FROM recipe_ingredients ri
                                         JOIN products p ON ri.product_id = p.id
                                WHERE ri.recipe_id = %s
                                """, (recipe_id,))
                    for row in cur.fetchall():
                        recipe['ingredients'][row['name']] = row['quantity_description']

                    # 3. Теги
                    cur.execute("""
                                SELECT t.name
                                FROM recipe_tags rt
                                         JOIN tags t ON rt.tag_id = t.id
                                WHERE rt.recipe_id = %s
                                """, (recipe_id,))
                    for row in cur.fetchall():
                        recipe['tags'].add(row['name'].lower())
            conn.close()
            return recipe

        # --- Функции для получения справочников ---

        def get_all_product_names() -> set:
            """Возвращает множество всех названий продуктов из справочника products."""
            sql = "SELECT name FROM products;"
            product_names = set()
            conn = get_db_connection()
            if conn:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        rows = cur.fetchall()
                        for row in rows:
                            product_names.add(row[0].lower())
                conn.close()
            return product_names

        def get_all_equipment_names() -> set:
            """Возвращает множество всех названий оборудования из справочника equipment."""
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
if __name__ == "__main__":
    conn = get_db_connection()
    if not conn:
        print("❌ Не смог подключиться к БД")
    else:
        print("✅ Подключение ок")

        # проверим, что таблица users вообще есть
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users;")
                count = cur.fetchone()[0]
                print(f"В таблице users записей: {count}")

        conn.close()