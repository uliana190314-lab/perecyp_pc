import os
import random
import asyncio
import json
from datetime import datetime
from aiohttp import web

import libsql_client
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if not TOKEN or not TURSO_URL or not TURSO_TOKEN:
    raise RuntimeError("Не заданы переменные окружения")

def normalize_turso_url(url: str) -> str:
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url

turso_client = None

# ================== СОСТОЯНИЯ ==================
class TradeStates(StatesGroup):
    waiting_item_price = State()
    waiting_pc_price = State()

# ================== КАТАЛОГ ==================
CATALOG = [
    {"cat":"cpu","name":"Pentium E5300","price":300,"slot":"cpu","socket":"LGA775","ddr":"DDR2","icon":"🧠"},
    {"cat":"cpu","name":"Core 2 Quad Q6600","price":1200,"slot":"cpu","socket":"LGA775","ddr":"DDR2","icon":"🧠"},
    {"cat":"cpu","name":"Core i5-3570K","price":2500,"slot":"cpu","socket":"LGA1155","ddr":"DDR3","icon":"🧠"},
    {"cat":"cpu","name":"Core i7-4790K","price":5500,"slot":"cpu","socket":"LGA1150","ddr":"DDR3","icon":"🧠"},
    {"cat":"cpu","name":"Core i5-10400F","price":6000,"slot":"cpu","socket":"LGA1200","ddr":"DDR4","icon":"🧠"},
    {"cat":"cpu","name":"Core i5-12400F","price":9500,"slot":"cpu","socket":"LGA1700","ddr":"DDR4","icon":"🧠"},
    {"cat":"cpu","name":"Ryzen 5 3600","price":6500,"slot":"cpu","socket":"AM4","ddr":"DDR4","icon":"🧠"},
    {"cat":"cpu","name":"Ryzen 5 5600","price":8500,"slot":"cpu","socket":"AM4","ddr":"DDR4","icon":"🧠"},
    {"cat":"cpu","name":"Ryzen 7 7800X3D","price":32000,"slot":"cpu","socket":"AM5","ddr":"DDR5","icon":"🧠"},
    {"cat":"gpu","name":"GT 730","price":1500,"slot":"gpu","icon":"🎮"},
    {"cat":"gpu","name":"GTX 1060 6GB","price":6500,"slot":"gpu","icon":"🎮"},
    {"cat":"gpu","name":"GTX 1660 Super","price":12000,"slot":"gpu","icon":"🎮"},
    {"cat":"gpu","name":"RTX 2060 (греется)","price":13000,"slot":"gpu","icon":"🎮","broken":True},
    {"cat":"gpu","name":"RTX 3060 12GB","price":20000,"slot":"gpu","icon":"🎮"},
    {"cat":"gpu","name":"RTX 4070","price":45000,"slot":"gpu","icon":"🎮"},
    {"cat":"gpu","name":"RX 580 8GB (майнинг)","price":7000,"slot":"gpu","icon":"🎮","broken":True},
    {"cat":"gpu","name":"RX 6700 XT","price":22000,"slot":"gpu","icon":"🎮"},
    {"cat":"mb","name":"G31 (LGA775)","price":600,"slot":"mb","socket":"LGA775","ddr":"DDR2","icon":"🧩"},
    {"cat":"mb","name":"H61 (LGA1155)","price":1200,"slot":"mb","socket":"LGA1155","ddr":"DDR3","icon":"🧩"},
    {"cat":"mb","name":"Z97 (LGA1150)","price":4500,"slot":"mb","socket":"LGA1150","ddr":"DDR3","icon":"🧩"},
    {"cat":"mb","name":"B560M (LGA1200)","price":3500,"slot":"mb","socket":"LGA1200","ddr":"DDR4","icon":"🧩"},
    {"cat":"mb","name":"B450M (AM4)","price":4000,"slot":"mb","socket":"AM4","ddr":"DDR4","icon":"🧩"},
    {"cat":"mb","name":"Z690 (LGA1700)","price":9000,"slot":"mb","socket":"LGA1700","ddr":"DDR4","icon":"🧩"},
    {"cat":"mb","name":"B650 (AM5)","price":12000,"slot":"mb","socket":"AM5","ddr":"DDR5","icon":"🧩"},
    {"cat":"ram","name":"DDR2 4GB 800","price":700,"slot":"ram","ddr":"DDR2","icon":"💾"},
    {"cat":"ram","name":"DDR3 8GB 1600","price":1200,"slot":"ram","ddr":"DDR3","icon":"💾"},
    {"cat":"ram","name":"DDR3 16GB 1600","price":2500,"slot":"ram","ddr":"DDR3","icon":"💾"},
    {"cat":"ram","name":"DDR4 16GB 3200","price":3500,"slot":"ram","ddr":"DDR4","icon":"💾"},
    {"cat":"ram","name":"DDR4 32GB 3600","price":7000,"slot":"ram","ddr":"DDR4","icon":"💾"},
    {"cat":"ram","name":"DDR5 16GB 5200","price":6000,"slot":"ram","ddr":"DDR5","icon":"💾"},
    {"cat":"ram","name":"DDR5 32GB 6000","price":12000,"slot":"ram","ddr":"DDR5","icon":"💾"},
    {"cat":"storage","name":"HDD 1TB","price":1200,"slot":"storage","icon":"💿"},
    {"cat":"storage","name":"SSD 512GB SATA","price":2000,"slot":"storage","icon":"💿"},
    {"cat":"storage","name":"SSD 1TB NVMe","price":5000,"slot":"storage","icon":"💿"},
    {"cat":"storage","name":"SSD 2TB Gen4","price":12000,"slot":"storage","icon":"💿"},
    {"cat":"psu","name":"300W noname","price":700,"slot":"psu","watt":300,"icon":"⚡"},
    {"cat":"psu","name":"500W noname","price":1500,"slot":"psu","watt":500,"icon":"⚡"},
    {"cat":"psu","name":"650W Chieftec","price":3000,"slot":"psu","watt":650,"icon":"⚡"},
    {"cat":"psu","name":"850W Be Quiet!","price":7000,"slot":"psu","watt":850,"icon":"⚡"},
    {"cat":"psu","name":"1000W Seasonic","price":12000,"slot":"psu","watt":1000,"icon":"⚡"},
    {"cat":"case","name":"ATX без стекла","price":1000,"slot":"case","icon":"📦"},
    {"cat":"case","name":"Zalman RGB","price":2500,"slot":"case","icon":"📦"},
    {"cat":"case","name":"Lian Li O11","price":8000,"slot":"case","icon":"📦"},
    {"cat":"cooler","name":"Боксовый Intel","price":300,"slot":"cooler","icon":"❄️"},
    {"cat":"cooler","name":"Башня 4 трубки","price":1200,"slot":"cooler","icon":"❄️"},
    {"cat":"cooler","name":"Noctua NH-D15","price":4000,"slot":"cooler","icon":"❄️"},
    {"cat":"cooler","name":"СЖО 360","price":12000,"slot":"cooler","icon":"❄️"},
    {"cat":"periph","name":"Мышь офисная","price":200,"icon":"🖱️"},
    {"cat":"periph","name":"Logitech G102","price":1200,"icon":"🖱️"},
    {"cat":"periph","name":"Redragon клава","price":3000,"icon":"⌨️"},
    {"cat":"periph","name":"Keychron","price":8000,"icon":"⌨️"},
    {"cat":"periph","name":"Монитор 22\"","price":3000,"icon":"🖥️"},
    {"cat":"periph","name":"Монитор 27\" 144Hz","price":12000,"icon":"🖥️"},
    {"cat":"misc","name":"Термопаста","price":500,"icon":"🧴"},
    {"cat":"misc","name":"Отвёртки","price":800,"icon":"🛠️"},
    {"cat":"misc","name":"USB-хаб","price":300,"icon":"🔌"},
]

CATS = [
    ("cpu","🧠 Процессоры"),("gpu","🎮 Видеокарты"),("mb","🧩 Платы"),
    ("ram","💾 ОЗУ"),("storage","💿 Диски"),("psu","⚡ БП"),
    ("case","📦 Корпуса"),("cooler","❄️ Кулеры"),
    ("periph","🖱️ Периферия"),("misc","🎁 Безделушки"),
]

# ================== БАЗА ДАННЫХ ==================
async def db_init():
    await turso_client.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, username TEXT,
        balance INTEGER DEFAULT 50000, last_gift TEXT)""")
    await turso_client.execute("""CREATE TABLE IF NOT EXISTS inventory(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        item_idx INTEGER, price INTEGER, broken INTEGER DEFAULT 0)""")
    await turso_client.execute("""CREATE TABLE IF NOT EXISTS market(
        id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, seller_name TEXT,
        item_idx INTEGER, price INTEGER, broken INTEGER DEFAULT 0, 
        is_pc INTEGER DEFAULT 0, pc_data TEXT)""")

async def get_user(uid, uname=""):
    rs = await turso_client.execute("SELECT balance, last_gift FROM users WHERE user_id=?", [uid])
    if not rs.rows:
        await turso_client.execute("INSERT INTO users(user_id, username) VALUES(?,?)", [uid, uname])
        return {"balance": 50000, "last_gift": None}
    return {"balance": rs.rows[0][0], "last_gift": rs.rows[0][1]}

async def upd_balance(uid, delta):
    await turso_client.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", [delta, uid])

async def get_inv(uid):
    rs = await turso_client.execute("SELECT id, item_idx, price, broken FROM inventory WHERE user_id=? ORDER BY id", [uid])
    return rs.rows

async def add_inv(uid, item_idx, price=None, broken=0):
    if price is None: price = CATALOG[item_idx]["price"]
    await turso_client.execute("INSERT INTO inventory(user_id, item_idx, price, broken) VALUES(?,?,?,?)",
                               [uid, item_idx, price, broken])

async def del_inv(inv_id):
    await turso_client.execute("DELETE FROM inventory WHERE id=?", [inv_id])

async def upd_inv(inv_id, price, broken):
    await turso_client.execute("UPDATE inventory SET price=?, broken=? WHERE id=?", [price, broken, inv_id])

async def set_last_gift(uid, ts):
    await turso_client.execute("UPDATE users SET last_gift=? WHERE user_id=?", [ts, uid])

# ================== БОТ ==================
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
         InlineKeyboardButton(text="🏪 Рынок", callback_data="market")],
        [InlineKeyboardButton(text="📦 Инвентарь", callback_data="inv"),
         InlineKeyboardButton(text="🖥️ Собрать ПК", callback_data="asm")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="bal")],
    ])

def shop_kb():
    rows = []
    for i in range(0, len(CATS), 2):
        row = [InlineKeyboardButton(text=CATS[i][1], callback_data=f"c:{CATS[i][0]}")]
        if i+1 < len(CATS):
            row.append(InlineKeyboardButton(text=CATS[i+1][1], callback_data=f"c:{CATS[i+1][0]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="« Меню", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def items_kb(cat):
    rows = []
    for idx, item in enumerate(CATALOG):
        if item["cat"] != cat: continue
        text = f"{item['icon']} {item['name']} — {item['price']}₽"
        if item.get("broken"): text += " ⚠"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"b:{idx}")])
    rows.append([InlineKeyboardButton(text="« Категории", callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def inv_content(uid):
    rows = await get_inv(uid)
    if not rows:
        return ("📦 <b>Инвентарь пуст</b>\nКупи что-нибудь в /shop", main_menu())
    text = "📦 <b>Твой инвентарь:</b>\n\n"
    kb_rows = []
    for inv_id, item_idx, price, broken in rows:
        item = CATALOG[item_idx]
        mark = " ⚠" if broken else ""
        text += f"• {item['icon']} {item['name']} — {price}₽{mark}\n"
        
        row = [
            InlineKeyboardButton(text=f"💰 Продать", callback_data=f"s:{inv_id}"),
            InlineKeyboardButton(text=f"🏷️ На рынок", callback_data=f"lst:{inv_id}")
        ]
        if broken:
            row.insert(0, InlineKeyboardButton(text="🔧 Починить", callback_data=f"r:{inv_id}"))
        kb_rows.append(row)
    kb_rows.append([InlineKeyboardButton(text="« Меню", callback_data="main")])
    return (text, InlineKeyboardMarkup(inline_keyboard=kb_rows))

async def build_pc(uid):
    rows = await get_inv(uid)
    picked = {}
    for inv_id, item_idx, price, broken in rows:
        if broken: continue
        item = CATALOG[item_idx]
        slot = item.get("slot")
        if slot and slot not in picked:
            picked[slot] = (inv_id, item)
    slots = ["cpu","mb","ram","gpu","psu","storage","case","cooler"]
    labels = {"cpu":"Процессор","mb":"Мат.плата","ram":"ОЗУ","gpu":"Видеокарта",
              "psu":"БП","storage":"Диск","case":"Корпус","cooler":"Кулер"}
    problems = []; total = 0; ids = []
    lines = "🖥️ <b>Сборка ПК</b>\n\n"
    for s in slots:
        if s in picked:
            inv_id, item = picked[s]
            lines += f"✅ {labels[s]}: {item['name']}\n"
            total += item["price"]; ids.append(inv_id)
        else:
            lines += f"❌ {labels[s]}: нет\n"
    if "cpu" in picked and "mb" in picked:
        if picked["cpu"][1].get("socket") != picked["mb"][1].get("socket"):
            problems.append("Сокет CPU ≠ мат.платы")
    if "mb" in picked and "ram" in picked:
        if picked["mb"][1].get("ddr") != picked["ram"][1].get("ddr"):
            problems.append("DDR платы ≠ DDR памяти")
    missing = [s for s in slots if s not in picked]
    lines += f"\n💰 Стоимость: {total} ₽\n"
    if problems:
        lines += "\n⚠ <b>Проблемы:</b>\n" + "\n".join(problems)
        return lines, None
    if missing:
        lines += f"\nНе хватает: {len(missing)} шт."
        return lines, None
    sale = int(total * 1.35)
    lines += f"\n🎉 <b>ПК собран!</b>\nМожно продать государству за {sale} ₽ или выставить на рынок!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 Продать за {sale}₽", callback_data=f"asell:{sale}:{','.join(map(str,ids))}")],
        [InlineKeyboardButton(text="🏷️ Выставить на рынок", callback_data=f"pclst:{','.join(map(str,ids))}")]
    ])
    return lines, kb

async def market_content():
    rs = await turso_client.execute("SELECT id, seller_name, item_idx, price, broken, is_pc, pc_data FROM market ORDER BY id DESC LIMIT 15")
    rows = rs.rows
    
    if not rows:
        return "🏪 <b>Рынок пуст</b>\nНикто пока ничего не продает.", main_menu()
    
    text = "🏪 <b>Рынок игроков (последние 15 лотов):</b>\n\n"
    kb_rows = []
    for m_id, s_name, item_idx, m_price, broken, is_pc, pc_data in rows:
        if is_pc:
            name = "🖥️ Собранный ПК"
        else:
            item = CATALOG[item_idx]
            name = f"{item['icon']} {item['name']}"
            if broken: name += " ⚠"
            
        text += f"• {name} от <b>{s_name}</b> — {m_price}₽\n"
        kb_rows.append([InlineKeyboardButton(text=f"Купить {name[:15]} ({m_price}₽)", callback_data=f"mbuy:{m_id}")])
    
    kb_rows.append([InlineKeyboardButton(text="« Меню", callback_data="main")])
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)

# ================== ХЭНДЛЕРЫ ==================

@dp.message(Command("start"))
async def start(m: Message):
    u = await get_user(m.from_user.id, m.from_user.username or "")
    await m.answer(
        f"👋 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        f"💰 Баланс: <b>{u['balance']} ₽</b>\n\n"
        f"Ты — перекуп ПК. Покупай железо, чини, собирай компы и продавай!\n\n"
        f"/shop — магазин\n/inv — инвентарь\n/get — подарок\n"
        f"/balance — баланс\n/assemble — собрать ПК\n/market — рынок игроков",
        reply_markup=main_menu()
    )

@dp.message(Command("market"))
async def market_cmd(m: Message):
    text, kb = await market_content()
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "market")
async def cb_market(cb: CallbackQuery):
    text, kb = await market_content()
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("mbuy:"))
async def cb_mbuy(cb: CallbackQuery):
    m_id = int(cb.data.split(":")[1])
    rs = await turso_client.execute("SELECT seller_id, item_idx, price, broken, is_pc, pc_data FROM market WHERE id=?", [m_id])
    if not rs.rows:
        await cb.answer("❌ Этот лот уже продан!", show_alert=True); return
        
    seller_id, item_idx, m_price, broken, is_pc, pc_data = rs.rows[0]
    buyer_id = cb.from_user.id
    
    if buyer_id == seller_id:
        await cb.answer("❌ Вы не можете купить свой собственный лот!", show_alert=True); return
        
    u = await get_user(buyer_id)
    if u["balance"] < m_price:
        await cb.answer("❌ Не хватает денег!", show_alert=True); return
        
    await upd_balance(buyer_id, -m_price)
    await upd_balance(seller_id, m_price)
    
    if is_pc == 1:
        parts = json.loads(pc_data)
        for p_idx in parts:
            await add_inv(buyer_id, p_idx)
    else:
        await add_inv(buyer_id, item_idx, price=m_price, broken=broken)
        
    await turso_client.execute("DELETE FROM market WHERE id=?", [m_id])
    
    await cb.answer("✅ Успешно куплено!", show_alert=True)
    text, kb = await market_content()
    await cb.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("lst:"))
async def cb_list_item(cb: CallbackQuery, state: FSMContext):
    inv_id = int(cb.data.split(":")[1])
    await state.update_data(list_inv_id=inv_id, list_is_pc=False)
    await cb.message.answer("🏷️ <b>Введите цену</b>, за которую хотите выставить этот предмет (числом):")
    await state.set_state(TradeStates.waiting_item_price)
    await cb.answer()

@dp.callback_query(F.data.startswith("pclst:"))
async def cb_list_pc(cb: CallbackQuery, state: FSMContext):
    ids_str = cb.data.split(":")[1]
    ids = [int(x) for x in ids_str.split(",")]
    await state.update_data(list_pc_ids=ids, list_is_pc=True)
    await cb.message.answer("🏷️ <b>Введите цену</b> для вашего собранного ПК (числом):")
    await state.set_state(TradeStates.waiting_pc_price)
    await cb.answer()

@dp.message(TradeStates.waiting_item_price)
async def process_item_price(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit():
        await m.answer("❌ Пожалуйста, введите целое число (без букв)."); return
    price = int(m.text)
    data = await state.get_data()
    inv_id = data['list_inv_id']
    
    rs = await turso_client.execute("SELECT id, item_idx, price, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, m.from_user.id])
    if not rs.rows:
        await m.answer("❌ Предмет не найден в инвентаре."); await state.clear(); return
        
    _, item_idx, old_price, broken = rs.rows[0]
    
    await del_inv(inv_id)
    await turso_client.execute("INSERT INTO market(seller_id, seller_name, item_idx, price, broken) VALUES(?,?,?,?,?)",
                               [m.from_user.id, m.from_user.first_name, item_idx, price, broken])
    
    await m.answer(f"✅ Вы выставили <b>{CATALOG[item_idx]['name']}</b> на рынок за <b>{price}₽</b>!")
    await state.clear()

@dp.message(TradeStates.waiting_pc_price)
async def process_pc_price(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit():
        await m.answer("❌ Пожалуйста, введите целое число (без букв)."); return
    price = int(m.text)
    data = await state.get_data()
    ids = data['list_pc_ids']
    
    parts_indices = []
    for inv_id in ids:
        rs = await turso_client.execute("SELECT id, item_idx FROM inventory WHERE id=? AND user_id=?", [inv_id, m.from_user.id])
        if rs.rows:
            parts_indices.append(rs.rows[0][1])
            await del_inv(inv_id)
            
    await turso_client.execute("INSERT INTO market(seller_id, seller_name, item_idx, price, broken, is_pc, pc_data) VALUES(?,?,?,?,?,?,?)",
                               [m.from_user.id, m.from_user.first_name, -1, price, 0, 1, json.dumps(parts_indices)])
    
    await m.answer(f"✅ Вы выставили <b>Собранный ПК</b> на рынок за <b>{price}₽</b>!")
    await state.clear()

@dp.message(Command("shop"))
async def shop_cmd(m: Message):
    await m.answer("🛒 <b>Магазин</b>\nВыбери категорию:", reply_markup=shop_kb())

@dp.message(Command("inv"))
async def inv_cmd(m: Message):
    text, kb = await inv_content(m.from_user.id)
    await m.answer(text, reply_markup=kb)

@dp.message(Command("balance"))
async def balance_cmd(m: Message):
    u = await get_user(m.from_user.id)
    await m.answer(f"💰 Твой баланс: <b>{u['balance']} ₽</b>")

@dp.message(Command("assemble"))
async def assemble_cmd(m: Message):
    text, kb = await build_pc(m.from_user.id)
    await m.answer(text, reply_markup=kb)

@dp.message(Command("get"))
async def get_gift(m: Message):
    u = await get_user(m.from_user.id, m.from_user.username or "")
    now = datetime.now()
    if u["last_gift"]:
        last = datetime.fromisoformat(u["last_gift"])
        left = 86400 - int((now - last).total_seconds())
        if left > 0:
            h, rem = divmod(left, 3600)
            await m.answer(f"⏳ Подарок уже получен.\nСледующий через {h}ч {rem//60}м")
            return
    idx = random.randrange(len(CATALOG))
    item = CATALOG[idx]
    await add_inv(m.from_user.id, idx, broken=1 if item.get("broken") else 0)
    await set_last_gift(m.from_user.id, now.isoformat())
    await m.answer(
        f"🎁 <b>Ежедневный подарок!</b>\n\n"
        f"Тебе выпало: {item['icon']} <b>{item['name']}</b>\n"
        f"Стоимость: {item['price']} ₽\n\n"
        f"Загляни в /inv — там уже лежит!"
    )

@dp.callback_query(F.data.startswith("c:"))
async def cb_cat(cb: CallbackQuery):
    cat = cb.data[2:]
    name = dict(CATS).get(cat, cat)
    await cb.message.edit_text(f"{name}\nЖми на товар, чтобы купить:", reply_markup=items_kb(cat))
    await cb.answer()

@dp.callback_query(F.data.startswith("b:"))
async def cb_buy(cb: CallbackQuery):
    idx = int(cb.data[2:]); item = CATALOG[idx]
    u = await get_user(cb.from_user.id)
    if u["balance"] < item["price"]:
        await cb.answer("❌ Не хватает денег!", show_alert=True); return
    await upd_balance(cb.from_user.id, -item["price"])
    await add_inv(cb.from_user.id, idx, broken=1 if item.get("broken") else 0)
    await cb.answer(f"✅ Куплено: {item['name']} за {item['price']}₽", show_alert=True)

@dp.callback_query(F.data == "shop")
async def cb_shop(cb: CallbackQuery):
    await cb.message.edit_text("🛒 <b>Магазин</b>\nВыбери категорию:", reply_markup=shop_kb())
    await cb.answer()

@dp.callback_query(F.data == "main")
async def cb_main(cb: CallbackQuery):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"👋 <b>Меню</b>\n💰 Баланс: <b>{u['balance']} ₽</b>",
        reply_markup=main_menu()
    )
    await cb.answer()

@dp.callback_query(F.data == "inv")
async def cb_inv(cb: CallbackQuery):
    text, kb = await inv_content(cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "bal")
async def cb_bal(cb: CallbackQuery):
    u = await get_user(cb.from_user.id)
    await cb.answer(f"💰 Баланс: {u['balance']}₽", show_alert=True)

@dp.callback_query(F.data == "asm")
async def cb_asm(cb: CallbackQuery):
    text, kb = await build_pc(cb.from_user.id)
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("s:"))
async def cb_sell(cb: CallbackQuery):
    inv_id = int(cb.data[2:])
    rs = await turso_client.execute("SELECT id, item_idx, price, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, cb.from_user.id])
    if not rs.rows:
        await cb.answer("Не найдено", show_alert=True); return
    _, item_idx, price, broken = rs.rows[0]
    item = CATALOG[item_idx]
    sale = int(price * 0.85)
    if broken: sale = int(sale * 0.5)
    await upd_balance(cb.from_user.id, sale); await del_inv(inv_id)
    await cb.answer(f"💰 Продано государству: {item['name']} за {sale}₽", show_alert=True)
    text, kb = await inv_content(cb.from_user.id)
    try: await cb.message.edit_text(text, reply_markup=kb)
    except: pass

@dp.callback_query(F.data.startswith("r:"))
async def cb_repair(cb: CallbackQuery):
    inv_id = int(cb.data[2:])
    rs = await turso_client.execute("SELECT id, item_idx, price, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, cb.from_user.id])
    if not rs.rows or not rs.rows[0][3]:
        await cb.answer("Нечего чинить", show_alert=True); return
    _, item_idx, price, broken = rs.rows[0]
    cost = int(price * 0.2)
    u = await get_user(cb.from_user.id)
    if u["balance"] < cost:
        await cb.answer(f"Нужно {cost}₽ на ремонт", show_alert=True); return
    await upd_balance(cb.from_user.id, -cost)
    await upd_inv(inv_id, int(price * 1.3), 0)
    await cb.answer(f"🔧 Починено за {cost}₽", show_alert=True)
    text, kb = await inv_content(cb.from_user.id)
    try: await cb.message.edit_text(text, reply_markup=kb)
    except: pass

@dp.callback_query(F.data.startswith("asell:"))
async def cb_asell(cb: CallbackQuery):
    _, sale, ids = cb.data.split(":")
    sale = int(sale); ids = [int(x) for x in ids.split(",")]
    for i in ids: await del_inv(i)
    await upd_balance(cb.from_user.id, sale)
    await cb.message.edit_text(f"🎉 ПК продан государству за <b>{sale} ₽</b>!")
    await cb.answer()

# ================== ВЕБ-СЕРВЕР И WEBHOOK ==================
async def on_startup(bot: Bot):
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        print(f"✅ Webhook установлен на {webhook_url}")

async def main():
    global turso_client
    turso_client = libsql_client.create_client(url=normalize_turso_url(TURSO_URL), auth_token=TURSO_TOKEN)
    await db_init()
    print("✅ База данных Turso инициализирована")
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")
    
    async def health(request):
        return web.Response(text="Bot is running")
    app.router.add_get("/", health)
    
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Веб-сервер запущен на порту {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
