#!/usr/bin/env python3
"""
Веб-сайт для продажи фискальных накопителей с оплатой через Bitcoin Core.
Полная копия функционала Telegram-бота, но в виде сайта.
"""

import os
import json
import uuid
import shutil
import urllib.request
import urllib.error
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

# Загружаем .env
load_dotenv()

# ======================== НАСТРОЙКИ ========================
BTC_RPC_USER = os.getenv("BTC_RPC_USER", "-")
BTC_RPC_PASSWORD = os.getenv("BTC_RPC_PASSWORD", "-")
BTC_RPC_HOST = os.getenv("BTC_RPC_HOST", "127.0.0.1")
BTC_RPC_PORT = os.getenv("BTC_RPC_PORT", "18332")
BTC_WALLET = os.getenv("BTC_WALLET", "-")  # имя кошелька (если несколько)
if BTC_WALLET:
    BTC_RPC_URL = f"http://{BTC_RPC_USER}:{BTC_RPC_PASSWORD}@{BTC_RPC_HOST}:{BTC_RPC_PORT}/wallet/{BTC_WALLET}"
else:
    BTC_RPC_URL = f"http://{BTC_RPC_USER}:{BTC_RPC_PASSWORD}@{BTC_RPC_HOST}:{BTC_RPC_PORT}"

PRICE_RUB = int(os.getenv("PRICE_RUB", "-"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "-")
SUPPORT_LINK = f"https://t.me/{SUPPORT_USERNAME}"
SECRET_KEY = os.getenv("SECRET_KEY", "-")

# Администраторы (список username через запятую, без @)
ADMIN_USERNAMES = [u.strip().lower() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "-")  # пароль для входа в админку

# Путь к данным
ORDERS_FILE = "orders.txt"
USERS_DATA_DIR = "users_data"
BASE_DIR = Path(__file__).parent

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ======================== ПОЛУЧЕНИЕ КУРСА BTC/RUB ========================
def get_btc_rub_rate():
    """
    Получить актуальный курс Bitcoin к рублю через CoinGecko API.
    Возвращает цену 1 BTC в рублях или None при ошибке.
    """
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=rub"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FiscalShop/1.0)"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            rate = data.get("bitcoin", {}).get("rub")
            if rate:
                print(f"[BTC Курс] 1 BTC = {rate:.2f} RUB")
                return rate
            return None
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError) as e:
        print(f"[BTC Курс] Ошибка получения курса: {e}")
        return None

def calculate_price_sats():
    """
    Рассчитать цену в сатоши на основе фиксированной цены в рублях
    и актуального курса BTC/RUB.
    Возвращает (price_sats, rate) или (None, None) при ошибке.
    """
    rate = get_btc_rub_rate()
    if not rate:
        return None, None

    price_btc = PRICE_RUB / rate
    price_sats = int(price_btc * 100_000_000)

    print(f"[BTC Цена] {PRICE_RUB} RUB = {price_sats:,} сатоши (1 BTC = {rate:.2f} RUB)")
    return price_sats, rate

# ======================== Bitcoin RPC клиент ========================
def get_btc_connection():
    """Получить соединение с Bitcoin Core через RPC"""
    try:
        rpc = AuthServiceProxy(BTC_RPC_URL)
        return rpc
    except Exception as e:
        print(f"[BTC RPC] Ошибка подключения: {e}")
        return None

def check_btc_connection():
    """Проверить соединение с Bitcoin Core"""
    try:
        rpc = get_btc_connection()
        if rpc:
            info = rpc.getblockchaininfo()
            print(f"[BTC] Подключено! Блоков: {info['blocks']}, Цепь: {info['chain']}")
            return True
        return False
    except Exception as e:
        print(f"[BTC] Не удалось подключиться: {e}")
        return False

def create_btc_invoice(order_id, required_sats):
    """
    Создать счет на оплату в Bitcoin.
    Генерирует новый адрес для заказа.
    """
    try:
        rpc = get_btc_connection()
        if not rpc:
            return None, None

        address = rpc.getnewaddress(f"order_{order_id}")
        amount_btc = required_sats / 100_000_000

        return address, amount_btc
    except Exception as e:
        print(f"[BTC RPC Error] {e}")
        return None, None

def check_payment(address, required_sats):
    """
    Проверить, поступила ли оплата на указанный адрес.
    """
    try:
        rpc = get_btc_connection()
        if not rpc:
            return False, 0

        received = rpc.listreceivedbyaddress(0, True, True, address)

        if not received:
            return False, 0

        total_received = sum(tx['amount'] for tx in received if tx.get('address') == address)
        total_received_sats = int(total_received * 100_000_000)

        if total_received_sats >= required_sats:
            return True, total_received_sats

        return False, total_received_sats
    except JSONRPCException as e:
        print(f"[BTC RPC Error] {e}")
        return False, 0

# ======================== РАБОТА С ДАННЫМИ ========================
def save_order(data):
    """
    Сохраняет заказ в текстовый файл.
    """
    orders_dir = BASE_DIR / USERS_DATA_DIR
    orders_dir.mkdir(exist_ok=True)

    order_id = data["order_id"]
    filename = orders_dir / f"order_{order_id}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== ЗАКАЗ #{order_id} ===\n")
        f.write(f"Дата: {data['date']}\n")
        f.write(f"Телефон: {data['phone']}\n")
        f.write(f"Адрес: {data['address']}\n")
        f.write(f"ФИО: {data['fullname']}\n")
        f.write(f"Email: {data.get('email', 'не указан')}\n")
        f.write(f"Цена в RUB: {data['price_rub']}\n")
        f.write(f"Курс BTC/RUB: {data['btc_rate']}\n")
        f.write(f"BTC Адрес: {data['btc_address']}\n")
        f.write(f"Сумма BTC: {data['btc_amount']}\n")
        f.write(f"Сумма сатоши: {data['sats']}\n")
        f.write(f"Статус: {data['status']}\n")
        f.write("=" * 30 + "\n")

    # Также добавляем в общий лог
    orders_file = BASE_DIR / ORDERS_FILE
    with open(orders_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return filename

def read_all_orders():
    """Прочитать все заказы из файла"""
    orders = []
    orders_file = BASE_DIR / ORDERS_FILE
    if orders_file.exists():
        with open(orders_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    orders.append(json.loads(line.strip()))
                except:
                    pass
    return orders

def clear_all_orders():
    """Очистить всю историю заказов"""
    # Очищаем orders.txt
    orders_file = BASE_DIR / ORDERS_FILE
    if orders_file.exists():
        os.remove(orders_file)
    # Очищаем папку users_data
    users_dir = BASE_DIR / USERS_DATA_DIR
    if users_dir.exists():
        shutil.rmtree(users_dir)
        users_dir.mkdir(exist_ok=True)

# ======================== АДМИН-АУТЕНТИФИКАЦИЯ ========================
def is_admin_session():
    """Проверить, авторизован ли пользователь как админ в текущей сессии"""
    return session.get("is_admin", False)

def admin_required(f):
    """Декоратор: требует авторизации админа"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_session():
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

# ======================== МАРШРУТЫ ========================

@app.route("/")
def index():
    """Главная страница"""
    return render_template("index.html", price_rub=PRICE_RUB)

@app.route("/order", methods=["GET", "POST"])
def order():
    """Страница оформления заказа"""
    if request.method == "GET":
        return render_template("order.html", price_rub=PRICE_RUB)

    # POST - обработка данных формы
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()

    # Валидация
    errors = []
    if not phone:
        errors.append("Введите номер телефона")
    if not address:
        errors.append("Введите адрес доставки")
    if not fullname:
        errors.append("Введите ФИО")

    if errors:
        return render_template("order.html", price_rub=PRICE_RUB, errors=errors,
                               form_data={"phone": phone, "address": address, "fullname": fullname, "email": email})

    # Создаем заказ
    order_id = str(uuid.uuid4())[:8].upper()
    order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Получаем курс и рассчитываем цену
    price_sats, btc_rate = calculate_price_sats()
    if not btc_rate or not price_sats:
        return render_template("order.html", price_rub=PRICE_RUB,
                               errors=["Не удалось получить актуальный курс Bitcoin. Попробуйте позже."],
                               form_data={"phone": phone, "address": address, "fullname": fullname, "email": email})

    # Создаем BTC счет
    btc_address, btc_amount = create_btc_invoice(order_id, price_sats)

    if not btc_address:
        return render_template("order.html", price_rub=PRICE_RUB,
                               errors=["Не удалось подключиться к платежной системе Bitcoin. Попробуйте позже."],
                               form_data={"phone": phone, "address": address, "fullname": fullname, "email": email})

    # Сохраняем данные заказа
    order_data = {
        "order_id": order_id,
        "date": order_date,
        "phone": phone,
        "address": address,
        "fullname": fullname,
        "email": email,
        "price_rub": PRICE_RUB,
        "btc_rate": btc_rate,
        "btc_address": btc_address,
        "btc_amount": btc_amount,
        "sats": price_sats,
        "status": "pending"
    }

    save_order(order_data)

    # Сохраняем в сессии для проверки оплаты
    session["order_data"] = order_data

    return render_template("payment.html", order=order_data)

@app.route("/payment/<order_id>")
def payment_page(order_id):
    """Страница оплаты (по ID заказа)"""
    orders = read_all_orders()
    order = None
    for o in orders:
        if o["order_id"] == order_id:
            order = o
            break

    if not order:
        return render_template("error.html", message="Заказ не найден"), 404

    return render_template("payment.html", order=order)

@app.route("/check-payment", methods=["POST"])
def check_payment_route():
    """Проверка статуса оплаты"""
    order_data = session.get("order_data")

    if not order_data:
        order_id = request.form.get("order_id")
        if order_id:
            orders = read_all_orders()
            for o in orders:
                if o["order_id"] == order_id:
                    order_data = o
                    break

    if not order_data:
        return jsonify({
            "success": False,
            "message": "Данные заказа не найдены. Начните оформление заново."
        })

    btc_address = order_data["btc_address"]
    required_sats = order_data["sats"]
    order_id = order_data["order_id"]

    paid, received_sats = check_payment(btc_address, required_sats)

    if paid:
        # Обновляем статус
        order_data["status"] = "paid"
        save_order(order_data)
        session["order_data"] = order_data

        return jsonify({
            "success": True,
            "paid": True,
            "message": "Оплата получена!",
            "order": order_data
        })
    else:
        received_btc = received_sats / 100_000_000
        required_btc = required_sats / 100_000_000

        return jsonify({
            "success": True,
            "paid": False,
            "received_sats": received_sats,
            "received_btc": f"{received_btc:.8f}",
            "required_sats": required_sats,
            "required_btc": f"{required_btc:.8f}",
            "message": "Оплата еще не поступила"
        })

@app.route("/success/<order_id>")
def success(order_id):
    """Страница успешной оплаты"""
    orders = read_all_orders()
    order = None
    for o in orders:
        if o["order_id"] == order_id:
            order = o
            break

    if not order:
        return render_template("error.html", message="Заказ не найден"), 404

    return render_template("success.html", order=order)

@app.route("/support")
def support():
    """Страница поддержки"""
    return render_template("support.html", support_username=SUPPORT_USERNAME, support_link=SUPPORT_LINK)

@app.route("/check-btc-status")
def check_btc_status():
    """Ajax проверка статуса Bitcoin Core"""
    btc_ok = check_btc_connection()
    rate = get_btc_rub_rate()

    return jsonify({
        "btc_connected": btc_ok,
        "btc_rate": rate is not None,
        "price_rub": PRICE_RUB
    })

# ======================== АДМИН-ПАНЕЛЬ ========================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Страница входа в админ-панель"""
    if is_admin_session():
        return redirect(url_for("admin_orders"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if username in ADMIN_USERNAMES and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            session["admin_username"] = username
            return redirect(url_for("admin_orders"))
        else:
            error = "❌ Неверный логин или пароль"

    return render_template("admin/login.html", error=error,
                           admin_usernames=", ".join(ADMIN_USERNAMES) if ADMIN_USERNAMES else "")

@app.route("/admin/logout")
def admin_logout():
    """Выход из админ-панели"""
    session.pop("is_admin", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_panel():
    """Перенаправление на страницу заказов"""
    return redirect(url_for("admin_orders"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    """Показать список всех заказов"""
    orders = read_all_orders()
    return render_template("admin/orders.html", orders=orders,
                           admin_username=session.get("admin_username", ""))

@app.route("/admin/stats")
@admin_required
def admin_stats():
    """Показать статистику"""
    orders = read_all_orders()
    total = len(orders)
    paid = sum(1 for o in orders if o.get("status") == "paid")
    pending = total - paid
    total_rub = sum(o.get("price_rub", 0) for o in orders if o.get("status") == "paid")

    return render_template("admin/stats.html",
                           total=total, paid=paid, pending=pending, total_rub=total_rub,
                           admin_username=session.get("admin_username", ""))

@app.route("/admin/clear", methods=["GET", "POST"])
@admin_required
def admin_clear():
    """Очистить всю историю заказов"""
    if request.method == "POST":
        clear_all_orders()
        flash("🗑️ Все заказы удалены! История заказов и статистика сброшены.", "success")
        return redirect(url_for("admin_orders"))

    return render_template("admin/clear.html",
                           admin_username=session.get("admin_username", ""))

# ======================== ЗАПУСК ========================
if __name__ == "__main__":
    print("=" * 50)
    print("  Веб-сайт - Продажа фискальных накопителей")
    print("  Оплата через Bitcoin Core")
    print(f"  Цена: {PRICE_RUB:,} RUB (автоконвертация по курсу BTC)")
    print("=" * 50)

    # Проверяем подключение к Bitcoin Core
    print("\n[1] Проверка подключения к Bitcoin Core...")
    if not check_btc_connection():
        print("[!] ВНИМАНИЕ: Не удалось подключиться к Bitcoin Core!")
        print("    Сайт запустится, но оплата будет недоступна.")
    else:
        print("[+] Bitcoin Core подключен успешно!")

    # Проверка получения курса BTC
    print("\n[2] Проверка получения курса BTC/RUB...")
    rate = get_btc_rub_rate()
    if rate:
        sats = int((PRICE_RUB / rate) * 100_000_000)
        print(f"[+] Курс получен: 1 BTC = {rate:.2f} RUB")
        print(f"[+] {PRICE_RUB:,} RUB = {sats:,} сатоши")
    else:
        print("[!] ВНИМАНИЕ: Не удалось получить курс BTC/RUB!")

    print("\n[3] Запуск веб-сервера...")
    print(f"[+] Открыть сайт: http://127.0.0.1:5000")
    print("[+] Нажмите Ctrl+C для остановки.")
    print("=" * 50)

    app.run(debug=True, host="127.0.0.1", port=5000)
