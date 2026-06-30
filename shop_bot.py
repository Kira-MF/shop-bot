# -*- coding: utf-8 -*-
import asyncio
import json
import os
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY = os.getenv("PROXY") or None
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_FILE = "shop.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID не задан в .env")

logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())

def load_db():
    if not os.path.exists(DB_FILE):
        return {"categories": {}, "orders": {}, "requisites": "Не указаны", "users": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user(db, user_id):
    uid = str(user_id)
    if "users" not in db:
        db["users"] = {}
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0, "username": ""}
    return db["users"][uid]

class AdminStates(StatesGroup):
    add_category = State()
    add_product_category = State()
    add_product_name = State()
    add_product_price = State()
    add_product_credentials = State()
    set_requisites = State()
    add_balance_user = State()
    add_balance_amount = State()
    set_balance_amount = State()

class BalanceStates(StatesGroup):
    waiting_amount = State()
    waiting_screenshot = State()

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Каталог", callback_data="catalog"),
         InlineKeyboardButton(text="💰 Мой баланс", callback_data="my_balance")],
        [InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders"),
         InlineKeyboardButton(text="ℹ️ О магазине", callback_data="about")],
    ])

def admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton(text="📦 Добавить товар", callback_data="admin_add_product")],
        [InlineKeyboardButton(text="🗑️ Удалить категорию", callback_data="admin_del_category")],
        [InlineKeyboardButton(text="🗑️ Удалить товар", callback_data="admin_del_product")],
        [InlineKeyboardButton(text="💳 Изменить реквизиты", callback_data="admin_set_requisites")],
        [InlineKeyboardButton(text="💸 Изменить баланс пользователю", callback_data="admin_set_balance")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
    ])

def categories_kb(for_admin=False):
    db = load_db()
    buttons = []
    for cat_id, cat in db["categories"].items():
        cb = f"admin_select_cat_{cat_id}" if for_admin else f"category_{cat_id}"
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def products_kb(cat_id):
    db = load_db()
    cat = db["categories"].get(cat_id, {})
    products = cat.get("products", {})
    buttons = []
    for prod_id, prod in products.items():
        count = len(prod.get("credentials", []))
        text = f"{prod['name']} - {prod['price']} руб. [{count} шт.]"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"product_{cat_id}_{prod_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_kb(target="back_main"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=target)]
    ])

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    db = load_db()
    user = get_user(db, message.from_user.id)
    user["username"] = message.from_user.username or ""
    save_db(db)
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👋 Добро пожаловать, Администратор!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛍️ Магазин", callback_data="catalog"),
                 InlineKeyboardButton(text="⚙️ Админ панель", callback_data="admin_panel")],
            ])
        )
    else:
        await message.answer(
            "👋 Добро пожаловать в магазин!\n\nВыбери нужный раздел:",
            reply_markup=main_menu_kb()
        )

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбери нужный раздел:", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "my_balance")
async def my_balance(callback: types.CallbackQuery):
    db = load_db()
    user = get_user(db, callback.from_user.id)
    save_db(db)
    await callback.message.edit_text(
        f"💰 Ваш баланс: {user['balance']} руб.\n\nПополни баланс чтобы покупать товары.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup_balance")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
        ])
    )

@dp.callback_query(F.data == "topup_balance")
async def topup_balance(callback: types.CallbackQuery, state: FSMContext):
    db = load_db()
    requisites = db.get("requisites", "Не указаны")
    await state.set_state(BalanceStates.waiting_amount)
    await callback.message.edit_text(
        f"💳 Пополнение баланса\n\nРеквизиты для оплаты:\n{requisites}\n\nВведи сумму которую хочешь пополнить:"
    )

@dp.message(BalanceStates.waiting_amount)
async def topup_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0!")
        return
    await state.update_data(topup_amount=amount)
    await state.set_state(BalanceStates.waiting_screenshot)
    await message.answer(f"📸 Отправь скриншот оплаты на сумму {amount} руб.:")

@dp.message(BalanceStates.waiting_screenshot, F.photo)
async def topup_screenshot(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data["topup_amount"]
    await state.clear()
    db = load_db()
    topup_id = f"t{len(db['orders']) + 1}"
    db["orders"][topup_id] = {
        "type": "topup",
        "user_id": message.from_user.id,
        "username": message.from_user.username or "",
        "amount": amount,
        "photo_id": message.photo[-1].file_id,
        "status": "pending"
    }
    save_db(db)
    await message.answer("✅ Скриншот получен! Ожидай подтверждения администратора.", reply_markup=main_menu_kb())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_topup_{topup_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_topup_{topup_id}")],
    ])
    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"📥 Запрос на пополнение #{topup_id}\nПользователь: @{message.from_user.username or '-'} ({message.from_user.id})\nСумма: {amount} руб.",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("confirm_topup_"))
async def confirm_topup(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return
    topup_id = callback.data.replace("confirm_topup_", "")
    db = load_db()
    order = db["orders"].get(topup_id)
    if not order or order["status"] != "pending":
        await callback.answer("Уже обработано")
        return
    user = get_user(db, order["user_id"])
    user["balance"] += order["amount"]
    order["status"] = "completed"
    save_db(db)
    await bot.send_message(order["user_id"], f"✅ Баланс пополнен на {order['amount']} руб.!\nТекущий баланс: {user['balance']} руб.")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ Подтверждено")
    await callback.answer("✅ Баланс пополнен!")

@dp.callback_query(F.data.startswith("reject_topup_"))
async def reject_topup(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return
    topup_id = callback.data.replace("reject_topup_", "")
    db = load_db()
    order = db["orders"].get(topup_id)
    if not order or order["status"] != "pending":
        await callback.answer("Уже обработано")
        return
    order["status"] = "rejected"
    save_db(db)
    await bot.send_message(order["user_id"], "❌ Пополнение отклонено. Если уверен что оплатил - обратись в поддержку.")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ Отклонено")
    await callback.answer("❌ Отклонено")

@dp.callback_query(F.data == "catalog")
async def catalog(callback: types.CallbackQuery):
    db = load_db()
    if not db["categories"]:
        await callback.message.edit_text("📭 Категорий пока нет.", reply_markup=back_kb("back_main"))
        return
    await callback.message.edit_text("🛍️ Выбери категорию:", reply_markup=categories_kb())

@dp.callback_query(F.data.startswith("category_"))
async def show_category(callback: types.CallbackQuery):
    cat_id = callback.data.split("_")[1]
    db = load_db()
    cat = db["categories"].get(cat_id)
    if not cat:
        await callback.answer("Категория не найдена")
        return
    if not cat.get("products"):
        await callback.message.edit_text(f"📂 {cat['name']}\n\nТоваров пока нет.", reply_markup=back_kb("catalog"))
        return
    await callback.message.edit_text(f"📂 {cat['name']}\n\nВыбери товар:", reply_markup=products_kb(cat_id))

@dp.callback_query(F.data.startswith("product_"))
async def show_product(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cat_id, prod_id = parts[1], parts[2]
    db = load_db()
    prod = db["categories"].get(cat_id, {}).get("products", {}).get(prod_id)
    if not prod:
        await callback.answer("Товар не найден")
        return
    user = get_user(db, callback.from_user.id)
    save_db(db)
    count = len(prod.get("credentials", []))
    status = "✅ В наличии" if count > 0 else "❌ Нет в наличии"
    text = (
        f"🛒 {prod['name']}\n\n"
        f"💰 Цена: {prod['price']} руб.\n"
        f"📦 Наличие: {status} ({count} шт.)\n"
        f"💳 Ваш баланс: {user['balance']} руб."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🛒 Купить за {prod['price']} руб.", callback_data=f"buy_{cat_id}_{prod_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"category_{cat_id}")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    cat_id, prod_id = parts[1], parts[2]
    db = load_db()
    prod = db["categories"].get(cat_id, {}).get("products", {}).get(prod_id)
    if not prod or len(prod.get("credentials", [])) == 0:
        await callback.answer("❌ Товар недоступен", show_alert=True)
        return
    user = get_user(db, callback.from_user.id)
    if user["balance"] < prod["price"]:
        await callback.answer(f"❌ Недостаточно средств! Нужно {prod['price']} руб., у тебя {user['balance']} руб.", show_alert=True)
        return
    user["balance"] -= prod["price"]
    credential = prod["credentials"].pop(0)
    order_id = str(len(db["orders"]) + 1)
    db["orders"][order_id] = {
        "type": "purchase",
        "user_id": callback.from_user.id,
        "username": callback.from_user.username or "",
        "prod_name": prod["name"],
        "price": prod["price"],
        "status": "completed"
    }
    save_db(db)
    await callback.message.edit_text(
        f"✅ Покупка успешна!\n\n🛒 Товар: {prod['name']}\n\n🔑 Ваши данные:\n{credential}\n\n💰 Остаток баланса: {user['balance']} руб.",
        reply_markup=main_menu_kb()
    )
    await bot.send_message(ADMIN_ID, f"🛒 Продажа #{order_id}\nПользователь: @{callback.from_user.username or '-'}\nТовар: {prod['name']} - {prod['price']} руб.")

@dp.callback_query(F.data == "my_orders")
async def my_orders(callback: types.CallbackQuery):
    db = load_db()
    orders = [o for o in db["orders"].values() if o.get("user_id") == callback.from_user.id and o.get("type") == "purchase"]
    if not orders:
        await callback.message.edit_text("📦 У тебя пока нет заказов.", reply_markup=back_kb("back_main"))
        return
    text = "📦 Твои заказы:\n\n"
    for i, o in enumerate(orders[-10:], 1):
        text += f"{i}. {o['prod_name']} - {o['price']} руб. ✅\n"
    await callback.message.edit_text(text, reply_markup=back_kb("back_main"))

@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ О магазине\n\nЗдесь ты можешь купить цифровые товары.\nПополни баланс и покупай товары мгновенно!",
        reply_markup=back_kb("back_main")
    )

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("⚙️ Админ панель\nВыбери действие:", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_add_category")
async def admin_add_category(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.add_category)
    await callback.message.edit_text("📁 Введи название новой категории:")

@dp.message(AdminStates.add_category)
async def save_category(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    db = load_db()
    cat_id = str(len(db["categories"]) + 1)
    db["categories"][cat_id] = {"name": message.text, "products": {}}
    save_db(db)
    await state.clear()
    await message.answer(f"✅ Категория «{message.text}» добавлена!", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_add_product")
async def admin_add_product(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    db = load_db()
    if not db["categories"]:
        await callback.answer("Сначала добавь категорию!", show_alert=True)
        return
    await state.set_state(AdminStates.add_product_category)
    await callback.message.edit_text("📁 Выбери категорию для товара:", reply_markup=categories_kb(for_admin=True))

@dp.callback_query(F.data.startswith("admin_select_cat_"))
async def admin_select_cat(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    cat_id = callback.data.split("_")[3]
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminStates.add_product_name)
    await callback.message.edit_text("📝 Введи название товара:")

@dp.message(AdminStates.add_product_name)
async def save_product_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(prod_name=message.text)
    await state.set_state(AdminStates.add_product_price)
    await message.answer("💰 Введи цену (только число, например: 299):")

@dp.message(AdminStates.add_product_price)
async def save_product_price(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число!")
        return
    await state.update_data(prod_price=price)
    await state.set_state(AdminStates.add_product_credentials)
    await message.answer("🔑 Введи данные товара (логин:пароль или ключ).\nМожно несколько - каждый с новой строки:")

@dp.message(AdminStates.add_product_credentials)
async def save_product_credentials(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    credentials = [line.strip() for line in message.text.split("\n") if line.strip()]
    db = load_db()
    cat = db["categories"].get(data["cat_id"])
    if not cat:
        await message.answer("❌ Категория не найдена.")
        await state.clear()
        return
    prod_id = str(len(cat["products"]) + 1)
    cat["products"][prod_id] = {"name": data["prod_name"], "price": data["prod_price"], "credentials": credentials}
    save_db(db)
    await state.clear()
    await message.answer(f"✅ Товар «{data['prod_name']}» добавлен! ({len(credentials)} шт.)", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_del_category")
async def admin_del_category(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    db = load_db()
    buttons = [[InlineKeyboardButton(text=f"🗑️ {cat['name']}", callback_data=f"delcat_{cid}")] for cid, cat in db["categories"].items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🗑️ Выбери категорию для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("delcat_"))
async def delete_category(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    cat_id = callback.data.split("_")[1]
    db = load_db()
    db["categories"].pop(cat_id, None)
    save_db(db)
    await callback.message.edit_text("✅ Категория удалена.", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_del_product")
async def admin_del_product(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    db = load_db()
    buttons = []
    for cid, cat in db["categories"].items():
        for pid, prod in cat.get("products", {}).items():
            buttons.append([InlineKeyboardButton(text=f"🗑️ {cat['name']} - {prod['name']}", callback_data=f"delprod_{cid}_{pid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🗑️ Выбери товар для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("delprod_"))
async def delete_product(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    parts = callback.data.split("_")
    cat_id, prod_id = parts[1], parts[2]
    db = load_db()
    db["categories"][cat_id]["products"].pop(prod_id, None)
    save_db(db)
    await callback.message.edit_text("✅ Товар удалён.", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_set_requisites")
async def admin_set_requisites(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.set_requisites)
    await callback.message.edit_text("💳 Введи реквизиты для пополнения баланса:")

@dp.message(AdminStates.set_requisites)
async def save_requisites(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    db = load_db()
    db["requisites"] = message.text
    save_db(db)
    await state.clear()
    await message.answer("✅ Реквизиты обновлены!", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.add_balance_user)
    await callback.message.edit_text("👤 Введи ID пользователя:")

@dp.message(AdminStates.add_balance_user)
async def admin_balance_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text)
    except ValueError:
        await message.answer("❌ Введи числовой ID!")
        return
    await state.update_data(target_uid=uid)
    await state.set_state(AdminStates.add_balance_amount)
    await message.answer("💰 Введи сумму пополнения:")

@dp.message(AdminStates.add_balance_amount)
async def admin_balance_amount(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число!")
        return
    data = await state.get_data()
    uid = data["target_uid"]
    db = load_db()
    user = get_user(db, uid)
    user["balance"] += amount
    save_db(db)
    await state.clear()
    await message.answer(f"✅ Баланс пользователя {uid} пополнен на {amount} руб.\nТекущий баланс: {user['balance']} руб.", reply_markup=admin_menu_kb())
    try:
        await bot.send_message(uid, f"💸 Администратор пополнил ваш баланс на {amount} руб.!\nТекущий баланс: {user['balance']} руб.")
    except:
        pass

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    db = load_db()
    users = db.get("users", {})
    if not users:
        await callback.message.edit_text("👥 Пользователей пока нет.", reply_markup=back_kb("admin_panel"))
        return
    text = "👥 Пользователи:\n\n"
    for uid, u in list(users.items())[-20:]:
        uname = f"@{u['username']}" if u.get("username") else f"ID: {uid}"
        text += f"{uname} - {u['balance']} руб.\n"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_panel"))

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    db = load_db()
    purchases = [o for o in db["orders"].values() if o.get("type") == "purchase" and o["status"] == "completed"]
    topups = [o for o in db["orders"].values() if o.get("type") == "topup" and o["status"] == "completed"]
    revenue = sum(o["price"] for o in purchases)
    deposited = sum(o["amount"] for o in topups)
    await callback.message.edit_text(
        f"📊 Статистика магазина\n\n"
        f"👥 Пользователей: {len(db.get('users', {}))}\n"
        f"🛒 Продаж: {len(purchases)}\n"
        f"💰 Выручка: {revenue} руб.\n"
        f"➕ Пополнений: {len(topups)}\n"
        f"💳 Депозиты: {deposited} руб.\n"
        f"📁 Категорий: {len(db['categories'])}",
        reply_markup=back_kb("admin_panel")
    )

async def main():
    session = AiohttpSession(proxy=PROXY) if PROXY else None
    bot = Bot(token=BOT_TOKEN, session=session) if session else Bot(token=BOT_TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())
