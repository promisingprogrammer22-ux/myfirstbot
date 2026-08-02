import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import sqlite3
from datetime import datetime
import csv
import io
from flask import Flask, request, jsonify
import threading

# ==========================================
# الثوابت والبيانات الأساسية وقنوات الإشعارات
# ==========================================
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BASE_URL = "https://public-grapes-lead.loca.lt"

# معرفات القنوات الخاصة بالإشعارات (استبدلها بالآي دي الرقمي الصحيح أو اسم المستخدم العام)
NEW_USERS_CHANNEL_ID = "@your_new_users_channel"         # قناة انضمام المستخدمين الجدد
DEPOSIT_WITHDRAW_CHANNEL_ID = "@your_deposits_channel"  # قناة الإيداعات والسحوبات

bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ حالات المستخدمين والأدمن أثناء العمليات التفاعلية
user_states = {}

# ==========================================
# تهيئة قاعدة البيانات والإعدادات وخزنة البوت
# ==========================================
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT,
            balance REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            type TEXT,
            amount REAL,
            details TEXT,
            status TEXT,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # الإعدادات الافتراضية بما فيها خزنة البوت (رصيد البوت الأساسي)
    default_settings = [
        ('bot_status', 'on'),
        ('trans_status', 'on'),
        ('support_account', '@Support_Admin'),
        ('usd_rate', '15000'),
        ('syriatel_numbers', '45696515'),
        ('offers_text', '🔹 لا توجد عروض أو بونصات نشطة حالياً. ترقبونا قريباً!'),
        ('bot_treasury', '5000000.0')  # رأس مال الخزنة الأساسي للبوت
    ]
    
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def update_setting(key, value):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_bot_treasury():
    val = get_setting('bot_treasury')
    return float(val) if val else 0.0

def update_bot_treasury(amount, operation='add'):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'bot_treasury'")
    row = cursor.fetchone()
    current_treasury = float(row[0]) if row and row[0] else 0.0
    
    if operation == 'add':
        new_treasury = current_treasury + amount
    elif operation == 'sub':
        new_treasury = max(0.0, current_treasury - amount)
    else:
        new_treasury = amount
        
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_treasury', ?)", (str(new_treasury),))
    conn.commit()
    conn.close()
    return new_treasury

def get_total_bot_balance():
    return get_bot_treasury()

# ==========================================
# خادم Flask المدمج للتعامل مع منصة الألعاب والرهانات
# ==========================================
flask_app = Flask(__name__)

@flask_app.route('/api/user_info', methods=['GET'])
def api_user_info():
    name = request.args.get('name')
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, username, balance FROM users WHERE username = ?", (name,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return jsonify({'success': True, 'telegram_id': user[0], 'username': user[1], 'balance': user[2]})
    return jsonify({'success': False, 'message': 'User not found'}), 404

@flask_app.route('/api/game_result', methods=['POST'])
def api_game_result():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400

    telegram_id = data.get('telegram_id')
    bet_amount = float(data.get('bet_amount', 0))
    result = data.get('result')  # 'win' أو 'loss'
    win_amount = float(data.get('win_amount', 0))

    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404
        
    current_balance = row[0]
    if current_balance < bet_amount:
        conn.close()
        return jsonify({'success': False, 'message': 'رصيد المحفظة غير كافٍ للرهان'}), 400

    new_balance = current_balance - bet_amount

    if result == 'loss':
        update_bot_treasury(bet_amount, 'add')
    elif result == 'win':
        net_profit = win_amount - bet_amount
        if net_profit > 0:
            treasury = get_bot_treasury()
            if treasury < net_profit:
                conn.close()
                return jsonify({'success': False, 'message': 'عذراً خزنة البوت لا تحتمل السيولة حالياً'}), 400
            update_bot_treasury(net_profit, 'sub')
        elif net_profit < 0:
            loss_part = abs(net_profit)
            update_bot_treasury(loss_part, 'add')
        new_balance += win_amount

    cursor.execute("UPDATE users SET balance = ? WHERE telegram_id = ?", (new_balance, telegram_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'new_balance': new_balance, 'treasury': get_bot_treasury()})

def run_flask():
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# ==========================================
# لوحات المفاتيح المدمجة (Inline Keyboards)
# ==========================================
def get_main_menu(user_id):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE telegram_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    db_username = row[0] if row and row[0] else "Alaa"
    web_app_url = f"{BASE_URL}/games_platform.html?name={db_username}"

    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(InlineKeyboardButton(text="🎮 منصة الألعاب", web_app=WebAppInfo(url=web_app_url)))
    markup.row(
        InlineKeyboardButton("💸 سحب من البوت", callback_data="btn_withdraw"),
        InlineKeyboardButton("💰 شحن البوت", callback_data="btn_deposit")
    )
    markup.row(
        InlineKeyboardButton("👤 معلومات الملف الشخصي", callback_data="btn_profile"),
        InlineKeyboardButton("💼 محفظتي", callback_data="btn_wallet")
    )
    markup.row(InlineKeyboardButton("🎁 إهداء رصيد", callback_data="btn_gift"))
    markup.row(
        InlineKeyboardButton("📥 سجل الإيداع", callback_data="btn_deposit_history"),
        InlineKeyboardButton("📤 سجل السحب", callback_data="btn_withdrawal_history")
    )
    markup.row(
        InlineKeyboardButton("🔄 استرداد آخر طلب سحب", callback_data="btn_refund"),
        InlineKeyboardButton("📜 دليل المستخدم والشروط", callback_data="btn_rules")
    )
    markup.row(
        InlineKeyboardButton("🎁 العروض والبونصات", callback_data="btn_offers"),
        InlineKeyboardButton("📞 مراسلة الدعم", url=f"https://t.me/{get_setting('support_account').replace('@', '')}")
    )
    
    if str(user_id) == str(ADMIN_ID):
        markup.row(InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="btn_admin"))
        
    return markup

def get_back_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="btn_main_menu"))
    return markup

def get_admin_back_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 العودة لوحة الأدمن", callback_data="adm_back_to_panel"))
    return markup

def get_admin_menu():
    bot_status = "🟢 البوت يعمل" if get_setting('bot_status') == 'on' else "🔴 البوت متوقف"
    trans_status = "🟢 الشحن والسحب متاح" if get_setting('trans_status') == 'on' else "🔴 الشحن والسحب متوقف"
    total_balance = get_bot_treasury()
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(InlineKeyboardButton(f"💰 خزنة البوت: {total_balance} ل.س", callback_data="adm_bot_balance_info"))
    markup.row(InlineKeyboardButton("💳 إيداع أو سحب رصيد (للعميل)", callback_data="adm_direct_balance"))
    markup.row(InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="adm_users_page_0"))
    markup.row(InlineKeyboardButton("📊 إحصائيات البوت", callback_data="adm_stats"), InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm_broadcast"))
    markup.row(InlineKeyboardButton("⏳ طلبات الإيداع والسحب المعلقة", callback_data="adm_pending_transactions"), InlineKeyboardButton("💱 تحديث سعر الصرف", callback_data="adm_usd_rate"))
    markup.row(InlineKeyboardButton("🎁 إدارة العروض والبونصات", callback_data="adm_edit_offers"), InlineKeyboardButton("📞 تعيين حساب الدعم", callback_data="adm_support_acc"))
    markup.row(InlineKeyboardButton("📱 إدارة أرقام سيرياتيل", callback_data="adm_syriatel"))
    markup.row(InlineKeyboardButton(trans_status, callback_data="toggle_trans"), InlineKeyboardButton(bot_status, callback_data="toggle_bot"))
    markup.row(InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="btn_main_menu"))
    return markup

def get_users_page_markup(page=0):
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, username, balance FROM users ORDER BY telegram_id DESC")
    users = cursor.fetchall()
    conn.close()
    
    per_page = 8
    total_users = len(users)
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
        
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔍 البحث عن مستخدم", callback_data="adm_search_user"))
    
    for u in page_users:
        t_id, uname, bal = u
        markup.add(InlineKeyboardButton(text=f"{uname} (الرصيد: {bal} ل.س)", callback_data=f"adm_user_info_{t_id}"))
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"adm_users_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"adm_users_page_{page+1}"))
    if nav_buttons:
        markup.row(*nav_buttons)
        
    markup.add(InlineKeyboardButton("🔙 العودة للوحة الأدمن", callback_data="adm_back_to_panel"))
    return markup, page+1, total_pages

# ==========================================
# أداة استخراج آي دي القنوات تلقائياً
# ==========================================
@bot.channel_post_handler(func=lambda message: True)
def get_channel_id(message):
    print(f"📌 آي دي القناة هو: {message.chat.id}")
    try:
        bot.send_message(ADMIN_ID, f"📌 آي دي القناة الحالية هو: `{message.chat.id}`", parse_mode="Markdown")
    except Exception as e:
        print(e)

# ==========================================
# أمر /start والتسجيل والشروط والأحكام
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if get_setting('bot_status') == 'off' and str(user_id) != str(ADMIN_ID):
        bot.send_message(user_id, "🔴 البوت متوقف حالياً للصيانة من قبل الإدارة. يرجى العودة لاحقاً.")
        return

    if user_id in user_states:
        del user_states[user_id]
    
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        bot.send_message(
            user_id, 
            f"✨ **أهلاً بك مجدداً يا {user[1]} في البوت!**", 
            parse_mode="Markdown", 
            reply_markup=get_main_menu(user_id)
        )
    else:
        terms_text = (
            "📜 **الشروط والأحكام لاستخدام المنصة**\n\n"
            "عند الضغط على زر الموافقة أدناه، فأنت تقر بالشروط التالية:\n\n"
            "1️⃣ يلتزم اللاعب بالأخلاق العالية، النزاهة التامة، وعدم محاولة الاحتيال.\n"
            "2️⃣ تتم عمليات الشحن وسحب الأرباح حصراً عبر الطرق المعتمدة.\n"
            "3️⃣ في حال رصد أي عملية غش، سيتم حظر الحساب فوراً وتجميد الأرصدة.\n\n"
            "🔹 *البوت رسمي ومؤمن بخوارزميات دقيقة لضمان حماية حقوق المستخدمين.*"
        )
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ موافق وأوافق على الشروط", callback_data="accept_terms"),
            InlineKeyboardButton("❌ عدم الموافقة", callback_data="reject_terms")
        )
        
        bot.send_message(user_id, terms_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['accept_terms', 'reject_terms'])
def handle_terms_callback(call):
    user_id = call.from_user.id
    message_id = call.message.message_id
    
    if call.data == 'accept_terms':
        bot.answer_callback_query(call.id, "شكراً لموافقتك على الشروط.")
        bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="✅ **تم قبول الشروط والأحكام بنجاح.**\n\nالرجاء إرسال **اسم الحساب** الذي تود اعتماده:",
            parse_mode="Markdown"
        )
        sent_msg = bot.send_message(user_id, "أدخل اسم الحساب:")
        bot.register_next_step_handler(sent_msg, process_username)
        
    elif call.data == 'reject_terms':
        bot.answer_callback_query(call.id, "تم رفض الشروط.")
        bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ عذراً، تم إلغاء التسجيل لعدم الموافقة على الشروط. يمكنك البدء مجدداً بإرسال /start",
            parse_mode="Markdown"
        )

def process_username(message):
    user_id = message.from_user.id
    username = message.text
    user_states[user_id] = {'username': username}
    
    sent_msg = bot.send_message(user_id, "🔒 ممتاز! الآن أرسل **كلمة المرور** الخاصة بحسابك:", parse_mode="Markdown")
    bot.register_next_step_handler(sent_msg, process_password)

def process_password(message):
    user_id = message.from_user.id
    password = message.text
    if user_id in user_states:
        username = user_states[user_id]['username']
        initial_balance = 0.0
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (telegram_id, username, password, balance) VALUES (?, ?, ?, ?)", 
                       (user_id, username, password, initial_balance))
        conn.commit()
        conn.close()
        
        try:
            tg_username = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"
            new_user_msg = (
                f"👤 **مستخدم جديد انضم للبوت وتم تفعيل حسابه!**\n\n"
                f"▫️ اسم الحساب: `{username}`\n"
                f"▫️ كلمة المرور: `{password}`\n"
                f"▫️ معرف تليجرام: {tg_username}\n"
                f"▫️ الآي دي (ID): `{user_id}`\n"
                f"▫️ الرصيد الافتتاحي: `{initial_balance}` ل.س"
            )
            bot.send_message(NEW_USERS_CHANNEL_ID, new_user_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending new user notification: {e}")
        
        del user_states[user_id]
        
        bot.send_message(
            user_id, 
            f"🎉 **تم إنشاء وتفعيل حسابك بنجاح!**\nرصيدك الحالي هو `{initial_balance}` ل.س (يمكنك شحن رصيدك أو انتظار إيداع/إهداء من الأدمن).", 
            parse_mode="Markdown", 
            reply_markup=get_main_menu(user_id)
        )

# ==========================================
# معالجة الأزرار المدمجة (Callbacks) - تم إصلاحها لتدعم قبول/رفض المعاملات
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith(('btn_', 'adm_', 'toggle_', 'app_', 'accept_tx_', 'reject_tx_')))
def handle_inline_buttons(call):
    user_id = call.from_user.id
    action = call.data
    message_id = call.message.message_id
    bot.answer_callback_query(call.id)

    if get_setting('bot_status') == 'off' and str(user_id) != str(ADMIN_ID) and action != 'btn_main_menu':
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text="🔴 البوت متوقف حالياً للصيانة.")
        return

    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, balance FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if action == "adm_back_to_panel":
        if str(user_id) == str(ADMIN_ID):
            bot.clear_step_handler_by_chat_id(user_id)
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())

    elif action == "btn_main_menu":
        if user_id in user_states:
            del user_states[user_id]
        bot.clear_step_handler_by_chat_id(user_id)
        bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="🏠 **أهلاً بك في القائمة الرئيسية:**",
            parse_mode="Markdown",
            reply_markup=get_main_menu(user_id)
        )

    elif action == "btn_wallet":
        msg = f"💼 **محفظتك المالية:**\n\n▪️ الرصيد المتوفر حالياً: `{user[2]}` ل.س"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_profile":
        msg = (f"👤 **معلومات الحساب الشخصي:**\n\n"
               f"▪️ اسم الحساب: `{user[0]}`\n"
               f"▪️ كلمة المرور: `{user[1]}`\n"
               f"▪️ معرف تلغرام (ID): `{user_id}`\n"
               f"▪️ الرصيد الحالي: `{user[2]}` ل.س")
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_deposit":
        if get_setting('trans_status') == 'off' and str(user_id) != str(ADMIN_ID):
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚠️ عذراً، عمليات الشحن متوقفة مؤقتاً من قبل الإدارة.", parse_mode="Markdown", reply_markup=get_back_menu())
            return
            
        syriatel_nums = get_setting('syriatel_numbers')
        msg = (f"💰 **شحن رصيد المحفظة عبر سيرياتيل كاش:**\n\n"
               f"يرجى تحويل المبلغ المطلوب إلى الرقم المعتمد التالي:\n`{syriatel_nums}`\n\n"
               f"بعد إتمام التحويل، أرسل الآن **رقم عملية التحويل**:")
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(call.message, process_deposit_trx)

    elif action == "btn_withdraw":
        if get_setting('trans_status') == 'off' and str(user_id) != str(ADMIN_ID):
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚠️ عذراً، عمليات السحب متوقفة مؤقتاً من قبل الإدارة.", parse_mode="Markdown", reply_markup=get_back_menu())
            return

        msg = "💸 **سحب الأرباح:**\n\nأرسل المبلغ الذي تود سحبه من رصيدك (تطبق عمولة 10% للبوت):"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(call.message, process_withdrawal_amount)

    elif action == "btn_gift":
        msg = "🎁 **إهداء رصيد لصديق:**\n\nأرسل **معرف تلغرام (Telegram ID)** الخاص بالشخص المراد إهداؤه:"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(call.message, process_gift_target)

    elif action == "btn_deposit_history":
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT amount, status, timestamp FROM transactions WHERE telegram_id = ? AND type = 'deposit'", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            msg = "📥 **سجل الإيداعات:**\n\nليس لديك أي عمليات إيداع مسجلة حتى الآن."
        else:
            msg = "📥 **سجل الإيداعات الخاصة بك:**\n\n"
            for row in rows:
                msg += f"▫️ المبلغ: `{row[0]}` ل.س | الحالة: *{row[1]}* | الوقت: {row[2]}\n"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_withdrawal_history":
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT amount, status, timestamp FROM transactions WHERE telegram_id = ? AND type = 'withdrawal'", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            msg = "📤 **سجل السحوبات:**\n\nليس لديك أي طلبات سحب مسجلة حتى الآن."
        else:
            msg = "📤 **سجل طلبات السحب الخاصة بك:**\n\n"
            for row in rows:
                msg += f"▫️ المبلغ: `{row[0]}` ل.س | الحالة: *{row[1]}* | الوقت: {row[2]}\n"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_refund":
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id, amount, status FROM transactions WHERE telegram_id = ? AND type = 'withdrawal' ORDER BY id DESC LIMIT 1", (user_id,))
        last_tx = cursor.fetchone()
        
        if not last_tx or last_tx[2] != 'pending':
            msg = "❌ عذراً، لا توجد طلبات سحب معلقة ليمكنك استردادها حالياً."
            conn.close()
        else:
            tx_id, amount = last_tx[0], last_tx[1]
            cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, user_id))
            update_bot_treasury(amount, 'sub')
            conn.commit()
            conn.close()
            msg = f"✅ تم إلغاء طلب السحب واسترداد مبلغ `{amount}` ل.س إلى محفظتك بنجاح!"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_rules":
        rules = (
            "📜 **دليل الاستخدام وشروط البوت:**\n\n"
            "1️⃣ يلتزم اللاعب بالأخلاق العالية، النزاهة التامة، وعدم محاولة الاحتيال.\n"
            "2️⃣ تتم عمليات الشحن وسحب الأرباح حصراً عبر الطرق المعتمدة.\n"
            "3️⃣ في حال رصد أي عملية غش، سيتم حظر الحساب فوراً وتجميد الأرصدة.\n\n"
            "🔹 *البوت رسمي ومؤمن بخوارزميات دقيقة لضمان حماية حقوق المستخدمين.*"
        )
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=rules, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_offers":
        offers = get_setting('offers_text')
        msg = f"🎁 **العروض والبونصات الحالية:**\n\n{offers}"
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())

    elif action == "btn_admin":
        if str(user_id) == str(ADMIN_ID):
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())
        else:
            bot.answer_callback_query(call.id, "⚠️ هذه اللوحة مخصصة للمالك فقط.", show_alert=True)

    elif action == "adm_bot_balance_info":
        if str(user_id) == str(ADMIN_ID):
            treasury_val = get_bot_treasury()
            bot.answer_callback_query(call.id, f"رصيد خزنة البوت الإجمالي الحالي: {treasury_val} ل.س", show_alert=True)

    elif action == "adm_direct_balance":
        if str(user_id) == str(ADMIN_ID):
            sent_msg = bot.send_message(user_id, "💳 **إيداع أو سحب رصيد يدوي للعميل:**\n\nأرسل الآن (آي دي المستخدم Telegram ID) أو (اسم الحساب):", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_adm_direct_user_lookup)

    elif action.startswith("adm_users_page_"):
        if str(user_id) == str(ADMIN_ID):
            page = int(action.split("_")[-1])
            markup, curr_p, total_p = get_users_page_markup(page)
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text=f"👥 **قائمة المستخدمين (صفحة {curr_p}/{total_p}):**", parse_mode="Markdown", reply_markup=markup)

    elif action == "adm_search_user":
        if str(user_id) == str(ADMIN_ID):
            sent_msg = bot.send_message(user_id, "🔍 أرسل اسم المستخدم أو الآي دي (ID) للبحث عنه:", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_admin_search_user)

    elif action.startswith("adm_user_info_"):
        if str(user_id) == str(ADMIN_ID):
            target_t_id = int(action.split("_")[-1])
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, username, password, balance FROM users WHERE telegram_id = ?", (target_t_id,))
            target_user = cursor.fetchone()
            conn.close()
            
            if target_user:
                t_id, uname, pwd, bal = target_user
                msg = (
                    f"👤 **معلومات اللاعب:**\n\n"
                    f"▪️ اسم الحساب: `{uname}`\n"
                    f"▪️ كلمة المرور: `{pwd}`\n"
                    f"▪️ الآي دي (ID): `{t_id}`\n"
                    f"▪️ الرصيد الحالي: `{bal}` ل.س"
                )
                markup = InlineKeyboardMarkup(row_width=2)
                markup.row(
                    InlineKeyboardButton("➕ إيداع رصيد", callback_data=f"adm_add_bal_{t_id}"),
                    InlineKeyboardButton("➖ سحب رصيد", callback_data=f"adm_sub_bal_{t_id}")
                )
                markup.row(InlineKeyboardButton("🔙 العودة لإدارة المستخدمين", callback_data="adm_users_page_0"))
                markup.row(InlineKeyboardButton("🔙 العودة للوحة الأدمن", callback_data="adm_back_to_panel"))
                bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=markup)

    elif action.startswith(('adm_add_bal_', 'adm_sub_bal_')):
        if str(user_id) == str(ADMIN_ID):
            parts = action.split('_')
            op_type = parts[1]
            target_t_id = int(parts[3])
            
            user_states[user_id] = {'target_t_id': target_t_id, 'op_type': op_type}
            op_text = "إيداعها إلى" if op_type == 'add' else "سحبها من"
            
            sent_msg = bot.send_message(user_id, f"💰 أرسل المبلغ المراد {op_text} رصيد المستخدم (ID: `{target_t_id}`):", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_admin_balance_modification)

    elif action == "toggle_bot":
        if str(user_id) == str(ADMIN_ID):
            current = get_setting('bot_status')
            new_val = 'off' if current == 'on' else 'on'
            update_setting('bot_status', new_val)
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())

    elif action == "toggle_trans":
        if str(user_id) == str(ADMIN_ID):
            current = get_setting('trans_status')
            new_val = 'off' if current == 'on' else 'on'
            update_setting('trans_status', new_val)
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())

    elif action == "adm_support_acc":
        if str(user_id) == str(ADMIN_ID):
            msg = f"📞 حساب الدعم الحالي: `{get_setting('support_account')}`\n\nأرسل اسم المستخدم الجديد لحساب الدعم (مثال: `@username`):"
            sent_msg = bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_update_support)

    elif action == "adm_usd_rate":
        if str(user_id) == str(ADMIN_ID):
            msg = f"💱 سعر صرف الدولار الحالي: `{get_setting('usd_rate')}`\n\nأرسل سعر الصرف الجديد:"
            sent_msg = bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_update_usd)

    elif action == "adm_syriatel":
        if str(user_id) == str(ADMIN_ID):
            msg = f"📱 أرقام سيرياتيل الحالية: `{get_setting('syriatel_numbers')}`\n\nأرسل الرقم أو الأرقام الجديدة المعتمدة للإيداع:"
            sent_msg = bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_update_syriatel)

    elif action == "adm_edit_offers":
        if str(user_id) == str(ADMIN_ID):
            msg = f"🎁 العروض الحالية:\n{get_setting('offers_text')}\n\nأرسل النص الجديد للعروض والبونصات:"
            sent_msg = bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_update_offers)

    elif action == "adm_broadcast":
        if str(user_id) == str(ADMIN_ID):
            sent_msg = bot.send_message(user_id, "📢 أرسل الرسالة الجماعية التي تود إرسالها لجميع المشتركين:", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_broadcast_message)

    elif action == "adm_stats":
        if str(user_id) == str(ADMIN_ID):
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*), SUM(balance) FROM users")
            u_res = cursor.fetchone()
            total_users = u_res[0] or 0
            total_user_balances = u_res[1] or 0.0
            treasury_balance = get_bot_treasury()
            
            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='deposit'")
            total_deposits = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='withdrawal'")
            total_withdrawals = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='deposit' AND date(timestamp) = date('now')")
            daily_deposit = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='withdrawal' AND date(timestamp) = date('now')")
            daily_withdrawal = cursor.fetchone()[0] or 0.0

            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='deposit' AND datetime(timestamp) >= datetime('now', '-7 days')")
            weekly_deposit = cursor.fetchone()[0] or 0.0

            cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='withdrawal' AND datetime(timestamp) >= datetime('now', '-7 days')")
            weekly_withdrawal = cursor.fetchone()[0] or 0.0

            conn.close()

            stats_msg = (
                "📊 **إحصائيات البوت الشاملة:**\n\n"
                f"👥 إجمالي المستخدمين: `{total_users}`\n"
                f"🏛️ رصيد خزنة البوت: `{treasury_balance}` ل.س\n"
                f"💰 مجموع أرصدة المستخدمين: `{total_user_balances}` ل.س\n"
                f"📥 مجموع الإيداعات العامة: `{total_deposits}` ل.س\n"
                f"📤 مجموع السحوبات العامة: `{total_withdrawals}` ل.س\n\n"
                f"📅 إيداعات اليوم: `{daily_deposit}` ل.س | سحوبات اليوم: `{daily_withdrawal}` ل.س\n"
                f"📆 إيداعات الأسبوع: `{weekly_deposit}` ل.س | سحوبات الأسبوع: `{weekly_withdrawal}` ل.س\n"
            )
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📥 تصدير تقرير Excel (CSV)", callback_data="adm_export_csv"))
            markup.row(InlineKeyboardButton("🔙 العودة لوحة الأدمن", callback_data="adm_back_to_panel"))
            
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text=stats_msg, parse_mode="Markdown", reply_markup=markup)

    elif action == "adm_export_csv":
        if str(user_id) == str(ADMIN_ID):
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT id, telegram_id, type, amount, status, timestamp FROM transactions")
            rows = cursor.fetchall()
            conn.close()
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Telegram ID', 'Type', 'Amount', 'Status', 'Timestamp'])
            for row in rows:
                writer.writerow(row)
            
            output.seek(0)
            file_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
            file_bytes.name = 'bot_transactions_report.csv'
            
            bot.send_document(user_id, file_bytes, caption="📁 تقرير العمليات الكامل للبوت.")

    elif action == "adm_pending_transactions":
        if str(user_id) == str(ADMIN_ID):
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT id, telegram_id, type, amount, details, timestamp FROM transactions WHERE status='pending'")
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                bot.answer_callback_query(call.id, "لا توجد عمليات معلقة حالياً.", show_alert=True)
            else:
                for row in rows:
                    tx_id, t_id, t_type, amt, details, time_str = row
                    type_str = "إيداع 📥" if t_type == 'deposit' else "سحب 📤"
                    markup = InlineKeyboardMarkup(row_width=2)
                    markup.add(
                        InlineKeyboardButton("✅ قبول", callback_data=f"accept_tx_{tx_id}"),
                        InlineKeyboardButton("❌ رفض واسترداد", callback_data=f"reject_tx_{tx_id}")
                    )
                    bot.send_message(user_id, f"⏳ طلب معلق ({type_str}):\n▪️ صاحب الآي دي: `{t_id}`\n▪️ المبلغ: `{amt}` ل.س\n▪️ التفاصيل/المحفظة: `{details}`\n▪️ الوقت: {time_str}", parse_mode="Markdown", reply_markup=markup)

    elif action.startswith(('accept_tx_', 'reject_tx_')):
        if str(user_id) == str(ADMIN_ID):
            parts = action.split('_')
            decision = parts[0]
            tx_id = parts[2]
            
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, type, amount FROM transactions WHERE id = ?", (tx_id,))
            tx = cursor.fetchone()
            
            if tx:
                t_id, t_type, amt = tx[0], tx[1], tx[2]
                if decision == 'accept':
                    cursor.execute("UPDATE transactions SET status = 'completed' WHERE id = ?", (tx_id,))
                    if t_type == 'deposit':
                        update_bot_treasury(amt, 'sub')
                        cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amt, t_id))
                        bot.send_message(t_id, f"✅ تم اعتماد وقبول عملية الشحن الخاصة بك بقيمة `{amt}` ل.س وإضافتها لمحفظتك بنجاح.", parse_mode="Markdown")
                    else:
                        bot.send_message(t_id, f"✅ تم قبول ومعالجة طلب السحب الخاص بك بقيمة `{amt}` ل.س بنجاح.", parse_mode="Markdown")
                    conn.commit()
                    bot.answer_callback_query(call.id, "تم قبول العملية بنجاح.")
                else:
                    if t_type == 'withdrawal':
                        cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amt, t_id))
                        update_bot_treasury(amt, 'sub')
                        bot.send_message(t_id, f"❌ تم رفض طلب السحب الخاص بك واسترداد مبلغ `{amt}` ل.س إلى محفظتك.", parse_mode="Markdown")
                    else:
                        bot.send_message(t_id, f"❌ نأسف، تم رفض طلب إيداع مبلغ `{amt}` ل.س من قبل الإدارة.", parse_mode="Markdown")
                    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
                    conn.commit()
                    bot.answer_callback_query(call.id, "تم رفض العملية بنجاح.")
            conn.close()

# ==========================================
# خطوات إدخال الأدمن والنوافذ التفاعلية
# ==========================================
def process_adm_direct_user_lookup(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        query = message.text.strip()
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, username, balance FROM users WHERE username LIKE ? OR telegram_id = ?", (f"%{query}%", query))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            sent_msg = bot.send_message(ADMIN_ID, f"❌ لم يتم العثور على مستخدم مطابق لـ: `{query}`\nأعد إدخال الآي دي أو اسم الحساب:", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_adm_direct_user_lookup)
        else:
            t_id, uname, bal = user
            user_states[ADMIN_ID] = {'target_t_id': t_id}
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("➕ إيداع رصيد", callback_data=f"adm_add_bal_{t_id}"),
                InlineKeyboardButton("➖ سحب رصيد", callback_data=f"adm_sub_bal_{t_id}")
            )
            markup.row(InlineKeyboardButton("🔙 العودة لوحة الأدمن", callback_data="adm_back_to_panel"))
            
            bot.send_message(
                ADMIN_ID,
                f"👤 **تم العثور على العميل بنجاح:**\n\n"
                f"▪️ اسم الحساب: `{uname}`\n"
                f"▪️ الآي دي (ID): `{t_id}`\n"
                f"▪️ الرصيد الحالي: `{bal}` ل.س\n\n"
                f"اختر نوع العملية المطلوبة:",
                parse_mode="Markdown",
                reply_markup=markup
            )

def process_admin_search_user(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        query = message.text.strip()
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, username, password, balance FROM users WHERE username LIKE ? OR telegram_id = ?", (f"%{query}%", query))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            sent_msg = bot.send_message(ADMIN_ID, f"❌ لم يتم العثور على مستخدم مطابق لـ: `{query}`\nأعد إدخال اسم المستخدم أو الآي دي للبحث:", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_admin_search_user)
        else:
            t_id, uname, pwd, bal = user
            msg = (
                f"👤 **معلومات اللاعب:**\n\n"
                f"▪️ اسم الحساب: `{uname}`\n"
                f"▪️ كلمة المرور: `{pwd}`\n"
                f"▪️ الآي دي (ID): `{t_id}`\n"
                f"▪️ الرصيد الحالي: `{bal}` ل.س"
            )
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("➕ إيداع رصيد", callback_data=f"adm_add_bal_{t_id}"),
                InlineKeyboardButton("➖ سحب رصيد", callback_data=f"adm_sub_bal_{t_id}")
            )
            markup.row(InlineKeyboardButton("🔙 العودة لإدارة المستخدمين", callback_data="adm_users_page_0"))
            markup.row(InlineKeyboardButton("🔙 العودة لوحة الأدمن", callback_data="adm_back_to_panel"))
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown", reply_markup=markup)

def process_admin_balance_modification(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        user_id = message.from_user.id
        if user_id not in user_states:
            bot.send_message(ADMIN_ID, "❌ انتهت الجلسة، حاول مجدداً.", reply_markup=get_admin_menu())
            return
            
        try:
            amount = float(message.text)
            target_t_id = user_states[user_id]['target_t_id']
            op_type = user_states[user_id]['op_type']
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT username, balance FROM users WHERE telegram_id = ?", (target_t_id,))
            target_user = cursor.fetchone()
            
            if not target_user:
                bot.send_message(ADMIN_ID, "❌ المستخدم غير موجود في القاعدة.", reply_markup=get_admin_menu())
                conn.close()
                return
                
            current_bal = target_user[1]
            
            if op_type == 'add':
                update_bot_treasury(amount, 'sub')
                new_bal = current_bal + amount
                cursor.execute("UPDATE users SET balance = ? WHERE telegram_id = ?", (new_bal, target_t_id))
                cursor.execute("INSERT INTO transactions (telegram_id, type, amount, details, status, timestamp) VALUES (?, 'admin_addition', ?, 'إضافة رصيد بواسطة الأدمن', 'completed', ?)", (target_t_id, amount, timestamp))
                conn.commit()
                conn.close()
                
                bot.send_message(ADMIN_ID, f"✅ تم إيداع مبلغ `{amount}` ل.س بنجاح إلى رصيد العميل `{target_user[0]}`.\nرصيده الجديد: `{new_bal}` ل.س", parse_mode="Markdown", reply_markup=get_admin_menu())
                try:
                    bot.send_message(target_t_id, f"💰 **إشعار من الإدارة:**\nتم إيداع رصيد بقيمة `{amount}` ل.س إلى محفظتك.\nرصيدك الحالي: `{new_bal}` ل.س", parse_mode="Markdown")
                except:
                    pass
                    
            elif op_type == 'sub':
                if current_bal < amount:
                    bot.send_message(ADMIN_ID, f"❌ رصيد العميل الحالي (`{current_bal}` ل.س) أقل من المبلغ المراد سحبه (`{amount}` ل.س).", parse_mode="Markdown", reply_markup=get_admin_menu())
                    conn.close()
                    return
                    
                update_bot_treasury(amount, 'add')
                new_bal = current_bal - amount
                cursor.execute("UPDATE users SET balance = ? WHERE telegram_id = ?", (new_bal, target_t_id))
                cursor.execute("INSERT INTO transactions (telegram_id, type, amount, details, status, timestamp) VALUES (?, 'admin_deduction', ?, 'سحب رصيد بواسطة الأدمن', 'completed', ?)", (target_t_id, amount, timestamp))
                conn.commit()
                conn.close()
                
                bot.send_message(ADMIN_ID, f"✅ تم سحب مبلغ `{amount}` ل.س بنجاح من رصيد العميل `{target_user[0]}`.\nرصيده الجديد: `{new_bal}` ل.س", parse_mode="Markdown", reply_markup=get_admin_menu())
                try:
                    bot.send_message(target_t_id, f"⚠️ **إشعار من الإدارة:**\nتم خصم مبلغ `{amount}` ل.س من محفظتك.\nرصيدك الحالي: `{new_bal}` ل.س", parse_mode="Markdown")
                except:
                    pass
            
            del user_states[user_id]
        except ValueError:
            sent_msg = bot.send_message(ADMIN_ID, "❌ خطأ: يرجى إدخال قيمة رقمية صحيحة للمبلغ:", parse_mode="Markdown", reply_markup=get_admin_back_markup())
            bot.register_next_step_handler(sent_msg, process_admin_balance_modification)

def process_update_support(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        new_acc = message.text
        update_setting('support_account', new_acc)
        bot.send_message(ADMIN_ID, f"✅ تم تحديث حساب الدعم بنجاح إلى: `{new_acc}`", parse_mode="Markdown", reply_markup=get_admin_menu())

def process_update_usd(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        new_rate = message.text
        update_setting('usd_rate', new_rate)
        bot.send_message(ADMIN_ID, f"✅ تم تحديث سعر صرف الدولار بنجاح إلى: `{new_rate}`", parse_mode="Markdown", reply_markup=get_admin_menu())

def process_update_syriatel(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        new_nums = message.text
        update_setting('syriatel_numbers', new_nums)
        bot.send_message(ADMIN_ID, f"✅ تم تحديث أرقام سيرياتيل بنجاح.", parse_mode="Markdown", reply_markup=get_admin_menu())

def process_update_offers(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        new_offers = message.text
        update_setting('offers_text', new_offers)
        bot.send_message(ADMIN_ID, f"✅ تم تحديث العروض والبونصات بنجاح.", parse_mode="Markdown", reply_markup=get_admin_menu())

def process_broadcast_message(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        broadcast_text = message.text
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        for u in users:
            try:
                bot.send_message(u[0], f"📢 **إعلان من الإدارة:**\n\n{broadcast_text}", parse_mode="Markdown")
                success += 1
            except:
                pass
                
        bot.send_message(ADMIN_ID, f"✅ تمت الإذاعة بنجاح إلى `{success}` مشترك.", parse_mode="Markdown", reply_markup=get_admin_menu())

# ==========================================
# دوال العمليات المالية (إيداع وسحب وإهداء)
# ==========================================
def process_deposit_trx(message):
    user_id = message.from_user.id
    trx_id = message.text
    user_states[user_id] = {'trx_id': trx_id}
    sent_msg = bot.send_message(user_id, "أرسل الآن **المبلغ المراد شحنه** (بالليرة السورية):", parse_mode="Markdown", reply_markup=get_back_menu())
    bot.register_next_step_handler(sent_msg, process_deposit_amount)

def process_deposit_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        trx_id = user_states.get(user_id, {}).get('trx_id', 'غير محدد')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        username = message.from_user.username or message.from_user.first_name
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (telegram_id, type, amount, details, status, timestamp) VALUES (?, 'deposit', ?, ?, 'pending', ?)", 
                       (user_id, amount, f"رقم العملية: {trx_id}", timestamp))
        conn.commit()
        conn.close()
        
        try:
            tg_username = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"
            channel_msg = (
                f"📥 **طلب إيداع جديد قيد المراجعة**\n\n"
                f"▫️ اسم اللاعب: {username}\n"
                f"▫️ معرف تليجرام: {tg_username}\n"
                f"▫️ الآي دي: `{user_id}`\n"
                f"▫️ المبلغ: `{amount}` ل.س\n"
                f"▫️ رقم عملية التحويل: `{trx_id}`"
            )
            bot.send_message(DEPOSIT_WITHDRAW_CHANNEL_ID, channel_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending deposit notice to channel: {e}")
        
        if user_id in user_states:
            del user_states[user_id]
            
        bot.send_message(user_id, "✅ تم تسجيل طلب الإيداع بنجاح وهو قيد مراجعة الإدارة.", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
    except ValueError:
        sent_msg = bot.send_message(user_id, "❌ خطأ: يرجى إدخال قيمة رقمية صحيحة للمبلغ:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_deposit_amount)

def process_withdrawal_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (user_id,))
        current_balance = cursor.fetchone()[0]
        
        if current_balance < amount:
            bot.send_message(user_id, f"❌ رصيدك الحالي غير كافٍ. رصيدك المتوفر: `{current_balance}` ل.س", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
            conn.close()
            return
        
        conn.close()
        user_states[user_id] = {'withdraw_amount': amount}
        sent_msg = bot.send_message(user_id, "أرسل الآن **رقم محفظتك** أو رقم سيريتل كاش/شام كاش لاستقبال الحوالة عليه:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_withdrawal_wallet)
    except ValueError:
        sent_msg = bot.send_message(user_id, "❌ خطأ: يرجى إدخال رقم صحيح لمبلغ السحب:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_withdrawal_amount)

def process_withdrawal_wallet(message):
    user_id = message.from_user.id
    wallet_number = message.text
    amount = user_states.get(user_id, {}).get('withdraw_amount', 0.0)
    
    commission = amount * 0.10
    net_amount = amount - commission
    username = message.from_user.username or message.from_user.first_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if current_balance < amount:
        bot.send_message(user_id, "❌ رصيد غير كافٍ.", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
        conn.close()
        return
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, user_id))
    update_bot_treasury(amount, 'add')
    
    cursor.execute("INSERT INTO transactions (telegram_id, type, amount, details, status, timestamp) VALUES (?, 'withdrawal', ?, ?, 'pending', ?)", 
                   (user_id, amount, f"محفظة الاستقبال: {wallet_number} (عمولة 10%: {commission})", timestamp))
    conn.commit()
    conn.close()
    
    try:
        tg_username = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"
        channel_msg = (
            f"📤 **طلب سحب رصيد جديد**\n\n"
            f"▫️ اسم اللاعب: {username}\n"
            f"▫️ معرف تليجرام: {tg_username}\n"
            f"▫️ الآي دي: `{user_id}`\n"
            f"▫️ المبلغ المطلوب: `{amount}` ل.س\n"
            f"▫️ عمولة البوت (10%): `{commission}` ل.س\n"
            f"▫️ الصافي للعميل: `{net_amount}` ل.س\n"
            f"▫️ رقم المحفظة للاستقبال: `{wallet_number}`"
        )
        bot.send_message(DEPOSIT_WITHDRAW_CHANNEL_ID, channel_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending withdrawal notice to channel: {e}")
        
    if user_id in user_states:
        del user_states[user_id]
        
    bot.send_message(
        user_id, 
        f"✅ تم تقديم طلب السحب بنجاح بقيمة `{amount}` ل.س (شاملة عمولة 10%).\n"
        f"سيتم تحويل الصافي (`{net_amount}` ل.س) إلى محفظتك `{wallet_number}` قريباً.", 
        parse_mode="Markdown", 
        reply_markup=get_main_menu(user_id)
    )

def process_gift_target(message):
    user_id = message.from_user.id
    try:
        target_id = int(message.text)
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE telegram_id = ?", (target_id,))
        target_user = cursor.fetchone()
        
        if not target_user:
            sent_msg = bot.send_message(user_id, "❌ عذراً، لم يتم العثور على مستخدم بهذا المعرف. أعد إدخال المعرف الصحيح:", parse_mode="Markdown", reply_markup=get_back_menu())
            bot.register_next_step_handler(sent_msg, process_gift_target)
            conn.close()
            return
            
        user_states[user_id] = {'target_id': target_id, 'target_name': target_user[0]}
        sent_msg = bot.send_message(user_id, f"✅ تم العثور على الصديق: **{target_user[0]}**\nالآن أرسل المبلغ المراد إهداؤه:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_gift_amount)
        conn.close()
    except ValueError:
        sent_msg = bot.send_message(user_id, "❌ خطأ: معرف التلغرام يجب أن يتكون من أرقام صحيحة:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_gift_target)

def process_gift_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        target_id = user_states[user_id]['target_id']
        target_name = user_states[user_id]['target_name']
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (user_id,))
        sender_balance = cursor.fetchone()[0]
        
        if sender_balance < amount:
            bot.send_message(user_id, f"❌ رصيدك غير كافٍ لإتمام الهدية. رصيدك الحالي: `{sender_balance}` ل.س", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
            conn.close()
            return
            
        cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, user_id))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, target_id))
        conn.commit()
        conn.close()
        
        if user_id in user_states:
            del user_states[user_id]
        
        bot.send_message(user_id, f"🎁 تم إهداء مبلغ `{amount}` ل.س إلى الصديق **{target_name}** بنجاح!", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
        bot.send_message(target_id, f"🎁 لقد تلقيت هدية بقيمة `{amount}` ل.س في رصيد محفظتك من أحد الأصدقاء!", parse_mode="Markdown")
    except ValueError:
        sent_msg = bot.send_message(user_id, "❌ خطأ: يرجى إدخال رقم صحيح للمبلغ:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_gift_amount)

# ==========================================
# تشغيل البوت
# ==========================================
print("✨ بوت الألعاب والخزنة يعمل بكافة التعديلات والشروط المحدثة وقنوات الإشعارات ومعالج الـ API...")
bot.infinity_polling()