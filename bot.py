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
    await turso_client.execute("INSERT INTO inventory(user_id, item_idx, price, broken) VALUES(?,?,?,?)", [uid, item_idx, price, broken])

async def del_inv(inv_id):
    await turso_client.execute("DELETE FROM inventory WHERE id=?", [inv_id])

async def upd_inv(inv_id, price, broken):
    await turso_client.execute("UPDATE inventory SET price=?, broken=? WHERE id=?", [price, broken, inv_id])

# ================== БОТ (Хэндлеры) ==================
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"), InlineKeyboardButton(text="🏪 Рынок", callback_data="market")],
        [InlineKeyboardButton(text="📦 Инвентарь", callback_data="inv"), InlineKeyboardButton(text="🖥️ Собрать ПК", callback_data="asm")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="bal")],
    ])

@dp.message(Command("start"))
async def start(m: Message):
    u = await get_user(m.from_user.id, m.from_user.username or "")
    await m.answer(f"👋 Привет, {m.from_user.first_name}!\n💰 Баланс: <b>{u['balance']} ₽</b>\n\n/start, /shop, /inv, /market", reply_markup=main_menu())

@dp.callback_query(F.data == "main")
async def cb_main(cb: CallbackQuery):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(f"👋 <b>Меню</b>\n💰 Баланс: <b>{u['balance']} ₽</b>", reply_markup=main_menu())
    await cb.answer()

# (Другие хэндлеры бота: магазин, инвентарь, подарок - они уже были в предыдущих файлах, 
# чтобы не раздувать код, я оставил только базу для API. Бот работает по старой логике)

# ================== API ДЛЯ HTML ==================
@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        response = web.Response()
    else:
        response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

async def api_get_user(request):
    uid = int(request.match_info['user_id'])
    u = await get_user(uid, "WebUser")
    inv = await get_inv(uid)
    inv_data = [{"id": r[0], "item_idx": r[1], "price": r[2], "broken": r[3], "name": CATALOG[r[1]]["name"], "icon": CATALOG[r[1]]["icon"], "slot": CATALOG[r[1]].get("slot"), "socket": CATALOG[r[1]].get("socket"), "ddr": CATALOG[r[1]].get("ddr")} for r in inv]
    return web.json_response({"balance": u["balance"], "inventory": inv_data})

async def api_buy(request):
    data = await request.json()
    uid, idx = data['user_id'], data['item_idx']
    item = CATALOG[idx]
    u = await get_user(uid)
    if u["balance"] < item["price"]: return web.json_response({"error": "Не хватает денег"}, status=400)
    await upd_balance(uid, -item["price"])
    await add_inv(uid, idx, broken=1 if item.get("broken") else 0)
    return web.json_response({"status": "ok"})

async def api_sell(request):
    data = await request.json()
    uid, inv_id = data['user_id'], data['inv_id']
    rs = await turso_client.execute("SELECT price, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, uid])
    if not rs.rows: return web.json_response({"error": "Не найдено"}, status=404)
    price, broken = rs.rows[0]
    sale = int(price * 0.85) if not broken else int(price * 0.85 * 0.5)
    await upd_balance(uid, sale)
    await del_inv(inv_id)
    return web.json_response({"status": "ok"})

async def api_repair(request):
    data = await request.json()
    uid, inv_id = data['user_id'], data['inv_id']
    rs = await turso_client.execute("SELECT price, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, uid])
    if not rs.rows or not rs.rows[0][1]: return web.json_response({"error": "Нечего чинить"}, status=400)
    price = rs.rows[0][0]
    cost = int(price * 0.2)
    u = await get_user(uid)
    if u["balance"] < cost: return web.json_response({"error": "Мало денег"}, status=400)
    await upd_balance(uid, -cost)
    await upd_inv(inv_id, int(price * 1.3), 0)
    return web.json_response({"status": "ok"})

# API для сборки ПК
async def api_assemble(request):
    data = await request.json()
    uid, ids = data['user_id'], data['ids']
    total = 0
    for inv_id in ids:
        rs = await turso_client.execute("SELECT price FROM inventory WHERE id=? AND user_id=?", [inv_id, uid])
        if rs.rows:
            total += rs.rows[0][0]
            await del_inv(inv_id)
    sale = int(total * 1.35)
    await upd_balance(uid, sale)
    return web.json_response({"status": "ok", "sale": sale})

# API для рынка
async def api_market_get(request):
    rs = await turso_client.execute("SELECT id, seller_name, item_idx, price, broken, is_pc FROM market ORDER BY id DESC LIMIT 20")
    market_items = []
    for r in rs.rows:
        name = "🖥️ Собранный ПК" if r[5] else f"{CATALOG[r[2]]['icon']} {CATALOG[r[2]]['name']}"
        market_items.append({"id": r[0], "seller": r[1], "name": name, "price": r[3], "broken": r[4], "is_pc": r[5]})
    return web.json_response({"market": market_items})

async def api_market_list(request):
    data = await request.json()
    uid, name, inv_id, price, is_pc = data['user_id'], data['name'], data['inv_id'], data['price'], data['is_pc']
    
    if is_pc:
        parts_indices = []
        for iid in inv_id:
            rs = await turso_client.execute("SELECT item_idx FROM inventory WHERE id=? AND user_id=?", [iid, uid])
            if rs.rows:
                parts_indices.append(rs.rows[0][0])
                await del_inv(iid)
        await turso_client.execute("INSERT INTO market(seller_id, seller_name, item_idx, price, is_pc, pc_data) VALUES(?,?,?,?,?,?)", [uid, name, -1, price, 1, json.dumps(parts_indices)])
    else:
        rs = await turso_client.execute("SELECT item_idx, broken FROM inventory WHERE id=? AND user_id=?", [inv_id, uid])
        if not rs.rows: return web.json_response({"error": "Не найдено"}, status=404)
        item_idx, broken = rs.rows[0]
        await del_inv(inv_id)
        await turso_client.execute("INSERT INTO market(seller_id, seller_name, item_idx, price, broken) VALUES(?,?,?,?,?)", [uid, name, item_idx, price, broken])
    return web.json_response({"status": "ok"})

async def api_market_buy(request):
    data = await request.json()
    buyer_id, m_id = data['user_id'], data['market_id']
    rs = await turso_client.execute("SELECT seller_id, item_idx, price, broken, is_pc, pc_data FROM market WHERE id=?", [m_id])
    if not rs.rows: return web.json_response({"error": "Лот не найден"}, status=404)
    seller_id, item_idx, m_price, broken, is_pc, pc_data = rs.rows[0]
    
    u = await get_user(buyer_id)
    if u["balance"] < m_price: return web.json_response({"error": "Не хватает денег"}, status=400)
    
    await upd_balance(buyer_id, -m_price)
    await upd_balance(seller_id, m_price)
    
    if is_pc:
        for p_idx in json.loads(pc_data): await add_inv(buyer_id, p_idx)
    else:
        await add_inv(buyer_id, item_idx, price=m_price, broken=broken)
        
    await turso_client.execute("DELETE FROM market WHERE id=?", [m_id])
    return web.json_response({"status": "ok"})

# ================== ВЕБ-СЕРВЕР ==================
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
    
    app = web.Application(middlewares=[cors_middleware])
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    
    app.router.add_get("/api/user/{user_id}", api_get_user)
    app.router.add_post("/api/buy", api_buy)
    app.router.add_post("/api/sell", api_sell)
    app.router.add_post("/api/repair", api_repair)
    app.router.add_post("/api/assemble", api_assemble)
    app.router.add_get("/api/market", api_market_get)
    app.router.add_post("/api/market/list", api_market_list)
    app.router.add_post("/api/market/buy", api_market_buy)
    
    async def health(request): return web.Response(text="Server is running")
    app.router.add_get("/", health)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Веб-сервер запущен на порту {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
