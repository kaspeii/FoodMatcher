-- Пользователи
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Категории продуктов
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    shelf_life_days INT
);

-- Продукты (со своими КБЖУ)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    category_id INT REFERENCES categories(id),
    calories NUMERIC(10,2),
    protein  NUMERIC(10,2),
    fat      NUMERIC(10,2),
    carbs    NUMERIC(10,2),
    per_unit TEXT NOT NULL DEFAULT '100g'
);

-- Холодильник пользователя
CREATE TABLE user_products (
    user_id INT REFERENCES users(id),
    product_id INT REFERENCES products(id),
    quantity NUMERIC(10,2),
    unit TEXT,
    added_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, product_id)
);

-- Рецепты (тоже с КБЖУ)
CREATE TABLE recipes (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    instructions TEXT NOT NULL,
    cooking_time_minutes INT,
    image_url TEXT,
    equipment_raw TEXT,
    calories NUMERIC(10,2),
    protein  NUMERIC(10,2),
    fat      NUMERIC(10,2),
    carbs    NUMERIC(10,2),
    nutrition_missing INT DEFAULT 0
);

-- Ингредиенты рецептов
CREATE TABLE recipe_ingredients (
    recipe_id INT REFERENCES recipes(id),
    product_id INT REFERENCES products(id),
    quantity_description TEXT,
    quantity NUMERIC(10,2),
    unit TEXT,
    PRIMARY KEY (recipe_id, product_id)
);

-- Теги
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Связка рецептов и тегов
CREATE TABLE recipe_tags (
    recipe_id INT REFERENCES recipes(id),
    tag_id INT REFERENCES tags(id),
    PRIMARY KEY (recipe_id, tag_id)
);

-- Картинки рецептов (шаги + обложка)
CREATE TABLE recipe_images (
    id SERIAL PRIMARY KEY,
    recipe_id INT REFERENCES recipes(id),
    image_url TEXT NOT NULL,
    step_number INT NOT NULL
);

-- Предпочтения пользователя по продуктам
CREATE TABLE user_product_preferences (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    note TEXT
);

-- Справочник оборудования
CREATE TABLE equipment (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Оборудование пользователя
CREATE TABLE user_equipment (
    user_id INT REFERENCES users(id) NOT NULL,
    equipment_id INT REFERENCES equipment(id) NOT NULL,
    PRIMARY KEY (user_id, equipment_id)
);

-- Оборудование рецепта (нормализованное)
CREATE TABLE recipe_equipment (
    recipe_id INT REFERENCES recipes(id) NOT NULL,
    equipment_id INT REFERENCES equipment(id) NOT NULL,
    PRIMARY KEY (recipe_id, equipment_id)
);

-- Ограничения по еде
CREATE TABLE user_food_constraints (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) NOT NULL,
    note TEXT
);
