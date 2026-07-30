import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import sqlite3
from datetime import datetime
import csv
import io

# ==========================================
# الثوابت والبيانات الأساسية
# ==========================================
TOKEN = '8805488820:AAE4jM7p19R-c3MlZ5t2zcjDTOgJhVlsP-U'
ADMIN_ID = 8576260469
BASE_URL = "https://yellow-eggs-type.loca.lt"

bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ حالات المستخدمين أثناء العمليات التفاعلية
user_states = {}

# ==========================================
# تهيئة قاعدة البيانات والإعدادات
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
    
    # الإعدادات الافتراضية
    default_settings = [
        ('bot_status', 'on'),
        ('trans_status', 'on'),
        ('support_account', '@Support_Admin'),
        ('usd_rate', '15000'),
        ('syriatel_numbers', '45696515'),
        ('offers_text', '🔹 لا توجد عروض أو بونصات نشطة حالياً. ترقبونا قريباً!')
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

# ==========================================
# لوحات المفاتيح المدمجة (Inline Keyboards)
# ==========================================
def get_main_menu(user_id):
    # جلب اسم الحساب المسجل من قاعدة البيانات لتمريره للعبة وضمان التطابق التام
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
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(InlineKeyboardButton("📊 إحصائيات البوت", callback_data="adm_stats"), InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm_broadcast"))
    markup.row(InlineKeyboardButton("⏳ طلبات السحب المعلقة", callback_data="adm_pending_withdrawals"), InlineKeyboardButton("💱 تحديث سعر الصرف", callback_data="adm_usd_rate"))
    markup.row(InlineKeyboardButton("🎁 إدارة العروض والبونصات", callback_data="adm_edit_offers"), InlineKeyboardButton("📞 تعيين حساب الدعم", callback_data="adm_support_acc"))
    markup.row(InlineKeyboardButton("📱 إدارة أرقام سيرياتيل", callback_data="adm_syriatel"))
    markup.row(InlineKeyboardButton(trans_status, callback_data="toggle_trans"), InlineKeyboardButton(bot_status, callback_data="toggle_bot"))
    markup.row(InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="btn_main_menu"))
    return markup

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
            "📜 **الشروط والأحكام لاستخدام بوت Promising Developer**\n\n"
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
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (telegram_id, username, password, balance) VALUES (?, ?, ?, 0.0)", 
                       (user_id, username, password))
        conn.commit()
        conn.close()
        
        del user_states[user_id]
        
        bot.send_message(
            user_id, 
            "🎉 **تم إنشاء وتفعيل حسابك بنجاح!**", 
            parse_mode="Markdown", 
            reply_markup=get_main_menu(user_id)
        )

# ==========================================
# معالجة الأزرار المدمجة (Callbacks)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith(('btn_', 'adm_', 'toggle_', 'app_')))
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

    # --- العودة للوحة الأدمن من حالات الإدخال ---
    if action == "adm_back_to_panel":
        if str(user_id) == str(ADMIN_ID):
            bot.clear_step_handler_by_chat_id(user_id)
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())

    # --- القوائم العامة للمستخدمين ---
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
               f"بعد إتمام التحويل، أرسل قيمة المبلغ المودع في رسالة هنا:")
        bot.edit_message_text(chat_id=user_id, message_id=message_id, text=msg, parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(call.message, process_deposit_amount)

    elif action == "btn_withdraw":
        if get_setting('trans_status') == 'off' and str(user_id) != str(ADMIN_ID):
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚠️ عذراً، عمليات السحب متوقفة مؤقتاً من قبل الإدارة.", parse_mode="Markdown", reply_markup=get_back_menu())
            return

        msg = "💸 **سحب الأرباح:**\n\nأرسل المبلغ الذي تود سحبه من رصيدك:"
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

    # --- لوحة الأدمن والخيارات المخصصة ---
    elif action == "btn_admin":
        if str(user_id) == str(ADMIN_ID):
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text="⚙️ **لوحة تحكم الأدمن الرئيسية:**", parse_mode="Markdown", reply_markup=get_admin_menu())
        else:
            bot.answer_callback_query(call.id, "⚠️ هذه اللوحة مخصصة للمالك فقط.", show_alert=True)

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
            msg = f"💱 سعر صرف الدولار الحالي: `{get_setting('usd_rate')}`\n\nأرسل سعر الصرف الجديد (مخصص للشام كاش لاحقاً):"
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
                f"💰 مجموع أرصدة المستخدمين: `{total_user_balances}` ل.س\n"
                f"📥 مجموع الإيداعات العامة: `{total_deposits}` ل.س\n"
                f"📤 مجموع السحوبات العامة: `{total_withdrawals}` ل.س\n\n"
                f"📅 إيداعات اليوم: `{daily_deposit}` ل.س | سحوبات اليوم: `{daily_withdrawal}` ل.س\n"
                f"📆 إيداعات الأسبوع: `{weekly_deposit}` ل.س | سحوبات الأسبوع: `{weekly_withdrawal}` ل.س\n"
            )
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📥 تصدير تقرير Excel (CSV)", callback_data="adm_export_csv"))
            markup.row(InlineKeyboardButton("🔙 العودة للوحة الأدمن", callback_data="btn_admin"))
            
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

    elif action == "adm_pending_withdrawals":
        if str(user_id) == str(ADMIN_ID):
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT id, telegram_id, amount, timestamp FROM transactions WHERE type='withdrawal' AND status='pending'")
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                bot.answer_callback_query(call.id, "لا توجد طلبات سحب معلقة حالياً.", show_alert=True)
            else:
                for row in rows:
                    tx_id, t_id, amt, time_str = row
                    markup = InlineKeyboardMarkup(row_width=2)
                    markup.add(
                        InlineKeyboardButton("✅ قبول", callback_data=f"accept_w_{tx_id}"),
                        InlineKeyboardButton("❌ رفض واسترداد", callback_data=f"reject_w_{tx_id}")
                    )
                    bot.send_message(user_id, f"⏳ طلب سحب معلق:\n▪️ صاحب المعرف: `{t_id}`\n▪️ المبلغ: `{amt}` ل.س\n▪️ الوقت: {time_str}", parse_mode="Markdown", reply_markup=markup)

    elif action.startswith(('accept_w_', 'reject_w_')):
        if str(user_id) == str(ADMIN_ID):
            parts = action.split('_')
            decision = parts[0]
            tx_id = parts[2]
            
            conn = sqlite3.connect('bot_database.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, amount FROM transactions WHERE id = ?", (tx_id,))
            tx = cursor.fetchone()
            
            if tx:
                t_id, amt = tx[0], tx[1]
                if decision == 'accept_w':
                    cursor.execute("UPDATE transactions SET status = 'completed' WHERE id = ?", (tx_id,))
                    conn.commit()
                    bot.send_message(t_id, f"✅ تم قبول ومعالجة طلب السحب الخاص بك بقيمة `{amt}` ل.س بنجاح.", parse_mode="Markdown")
                    bot.answer_callback_query(call.id, "تم قبول الطلب بنجاح.")
                else:
                    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amt, t_id))
                    conn.commit()
                    bot.send_message(t_id, f"❌ تم رفض طلب السحب الخاص بك واسترداد مبلغ `{amt}` ل.س إلى محفظتك.", parse_mode="Markdown")
                    bot.answer_callback_query(call.id, "تم رفض الطلب واسترداد الرصيد.")
            conn.close()

# ==========================================
# خطوات إدخال الأدمن والنوافذ التفاعلية
# ==========================================
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
# دوال العمليات المالية (Next Step Handlers)
# ==========================================
def process_deposit_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (telegram_id, type, amount, status, timestamp) VALUES (?, 'deposit', ?, 'pending', ?)", 
                       (user_id, amount, timestamp))
        conn.commit()
        conn.close()
        
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
            
        cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, user_id))
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO transactions (telegram_id, type, amount, status, timestamp) VALUES (?, 'withdrawal', ?, 'pending', ?)", 
                       (user_id, amount, timestamp))
        conn.commit()
        conn.close()
        
        bot.send_message(user_id, f"✅ تم تقديم طلب سحب بقيمة `{amount}` ل.س بنجاح وهو قيد التنفيذ.", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
    except ValueError:
        sent_msg = bot.send_message(user_id, "❌ خطأ: يرجى إدخال رقم صحيح لمبلغ السحب:", parse_mode="Markdown", reply_markup=get_back_menu())
        bot.register_next_step_handler(sent_msg, process_withdrawal_amount)

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
print("✨ بوت Promising Developer يعمل بكافة التعديلات والشروط المحدثة...")
bot.infinity_polling()