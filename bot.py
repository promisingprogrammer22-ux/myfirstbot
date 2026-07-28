import sqlite3
import telebot
from telebot import types

TOKEN = "8805488820:AAE4jM7p19R-c3MlZ5t2zcjDTOgJhVlsP-U"
ADMIN_ID = 8576260469

bot = telebot.TeleBot(TOKEN)
SYRIATEL_CASH_NUMBER = "45696515"

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            balance INTEGER DEFAULT 0,
            agreed_terms INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            receipt TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()
user_state = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, agreed_terms FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user and user[0] and user[1] == 1:
        bot.send_message(message.chat.id, f"أهلاً بك مجدداً يا {user[0]} في قمة التحدي! 🎮")
        show_main_menu(message.chat.id)
    else:
        user_state[user_id] = "waiting_username"
        bot.send_message(
            message.chat.id,
            "أهلاً بك في منصة الألعاب الرسمية! 🏆\n\nللبدء، يرجى إرسال **اسم المستخدم** الفريد الخاص بك:"
        )

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text

    if text == "🏛️ حسابك على المنصة":
        # استعلام لجلب كافة معلومات الحساب المطلوبة بدقة
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT username, password, balance FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user and user[0]:
            account_info = (
                f"👤 **معلومات حسابك الشخصي:**\n\n"
                f"📌 اسم المستخدم: `{user[0]}`\n"
                f"🔑 كلمة المرور: `{user[1]}`\n"
                f"🆔 معرف تيليجرام: `{user_id}`\n"
                f"💰 الرصيد الافتراضي: **{user[2]} ل.س**"
            )
            bot.send_message(message.chat.id, account_info, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "الرجاء البدء بالضغط على /start لتسجيل حسابك.")
            
    elif text == "⬆️ إيداع إلى المنصة":
        user_state[user_id] = "waiting_deposit_receipt"
        deposit_text = (
            f"💳 **شحن الرصيد عبر سيرياتيل كاش**\n\n"
            f"قم بتحويل المبلغ إلى المحفظة الرسمية الآتية:\n"
            f"📱 `{SYRIATEL_CASH_NUMBER}`\n\n"
            f"⚠️ الحد الأدنى للإيداع: 5,000 ل.س\n\n"
            f"بعد التحويل، **أرسل رقم العملية (Transaction ID)** هنا في المحادثة لتدقيقها:"
        )
        bot.send_message(message.chat.id, deposit_text, parse_mode="Markdown")
        
    elif text == "⬇️ سحب من المنصة":
        user_state[user_id] = "waiting_withdraw_details"
        bot.send_message(message.chat.id, "💸 **طلب سحب الأرباح (يدوي من الإدارة)**\nأرسل المبلغ المراد سحبه مع رقم محفظتك بدقة:")
        
    elif text == "🌐 المنصة":
        bot.send_message(message.chat.id, "اضغط هنا لفتح منصة التحديات والألعاب:", reply_markup=get_webapp_keyboard())
        
    elif text == "💬 مراسلة الدعم":
        bot.send_message(message.chat.id, "🛠️ للإبلاغ عن مشكلة أو استفسار تواصل مع: @Support_Admin")

    elif user_id in user_state and user_state[user_id] == "waiting_username":
        desired_username = text.strip()
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (desired_username,))
        existing_user = cursor.fetchone()
        conn.close()
        
        if existing_user and existing_user[0] != user_id:
            bot.send_message(message.chat.id, "⚠️ اسم المستخدم هذا مستخدم بالفعل من قبل شخص آخر!\nالرجاء اختيار اسم مستخدم فريد ومختلف:")
            return
            
        user_state[user_id] = {"state": "waiting_password", "username": desired_username}
        bot.send_message(message.chat.id, "ممتاز! 👤\nالآن أرسل **كلمة المرور** لتأمين حسابك:")
        
    elif user_id in user_state and isinstance(user_state[user_id], dict) and user_state[user_id].get("state") == "waiting_password":
        username = user_state[user_id]["username"]
        password = text.strip()
        
        try:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, password, balance, agreed_terms) 
                VALUES (?, ?, ?, 0, 0)
                ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, password=excluded.password
            ''', (user_id, username, password))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            bot.send_message(message.chat.id, "⚠️ حدث تكرار في البيانات، الرجاء كتابة /start والبدء باسم مستخدم غير مأخوذ.")
            del user_state[user_id]
            return
        
        del user_state[user_id]
        bot.send_message(message.chat.id, "✅ تم حفظ اسم المستخدم وكلمة المرور بنجاح!")
        show_terms(message.chat.id)
        
    elif user_id in user_state and user_state[user_id] == "waiting_deposit_receipt":
        receipt_id = text
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transactions (user_id, type, amount, receipt, status) VALUES (?, "deposit", 0, ?, "pending")', (user_id, receipt_id))
        conn.commit()
        conn.close()
        
        user_state[user_id] = "normal"
        bot.send_message(message.chat.id, "⏳ تم إرسال رقم العملية بنجاح إلى الإدارة للمراجعة والاعتماد الفوري.")
        
        admin_msg = f"🔔 **طلب إيداع جديد!**\n👤 المستخدم ID: `{user_id}`\n🧾 رقم العملية: `{receipt_id}`"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ قبول (10,000 ل.س)", callback_data=f"app_dep_{user_id}"),
            types.InlineKeyboardButton("❌ رفض", callback_data=f"rej_dep_{user_id}")
        )
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=markup)
        
    elif user_id in user_state and user_state[user_id] == "waiting_withdraw_details":
        withdraw_info = text
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transactions (user_id, type, amount, receipt, status) VALUES (?, "withdraw", 0, ?, "pending")', (user_id, withdraw_info))
        conn.commit()
        conn.close()
        
        user_state[user_id] = "normal"
        bot.send_message(message.chat.id, "⏳ تم استلام طلب السحب الخاص بك بنجاح، وهو قيد المراجعة اليدوية من الإدارة.")
        
        admin_msg = f"💸 **طلب سحب جديد معلق!**\n👤 المستخدم ID: `{user_id}`\n📝 التفاصيل: {withdraw_info}"
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        
    else:
        bot.send_message(message.chat.id, "اختر إحدى الخدمات من الأزرار أدناه 👇")

def show_terms(chat_id):
    terms_text = (
        "📜 **شروط وأحكام ألعاب التحدي والمنصة:**\n\n"
        "1️⃣ ألعاب التحدي (مثل الشطرنج والطرنيب) تتطلب رصيداً افتراضياً، ويتم اقتطاع حصة المشاركة من كلا الطرفين.\n"
        "2️⃣ عند انتهاء التحدي وفوز الفريق، يتم خصم عمولة المنصة (10%) ويحول الصافي للرابح.\n"
        "3️⃣ الإيداع يتم عبر قنوات الدفع الرسمية، أما السحب فيتم مراجعته ويدوياً حصراً.\n"
        "4️⃣ أي محاولة تلاعب تعرض الحساب للحظر النهائي.\n\n"
        "اضغط على زر الموافقة أدناه للدخول إلى المنصة:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ موافق وأوافق على الشروط", callback_data="accept_terms"))
    bot.send_message(chat_id, terms_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "accept_terms")
def handle_terms(call):
    user_id = call.from_user.id
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET agreed_terms = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, "تم قبول الشروط بنجاح! 🎉")
    try:
        bot.edit_message_text("✅ شكراً لموافقتك. تم تفعيل حسابك بالكامل وحفظ بياناتك بدقة!", call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    show_main_menu(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('app_dep_', 'rej_dep_')))
def admin_manage_deposit(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "غير مسموح لك بهذه الصلاحية!", show_alert=True)
        return
        
    action, _, target_user_id = call.data.split('_')
    target_user_id = int(target_user_id)
    
    if action == "app":
        added_amount = 10000
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (added_amount, target_user_id))
        conn.commit()
        conn.close()
        
        bot.send_message(target_user_id, f"🎉 مبروك! تم قبول إيداعك واعتماد مبلغ **{added_amount} ل.س** في رصيدك الافتراضي.")
        bot.edit_message_text(f"✅ تمت الموافقة وإضافة الرصيد للمستخدم {target_user_id} بنجاح.", call.message.chat.id, call.message.message_id)
    else:
        bot.send_message(target_user_id, "❌ عذراً، تم رفض عملية الإيداع من قبل الإدارة لعدم مطابقة بيانات التحويل.")
        bot.edit_message_text(f"❌ تم رفض إيداع المستخدم {target_user_id}.", call.message.chat.id, call.message.message_id)

def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🏛️ حسابك على المنصة")
    btn2 = types.KeyboardButton("⬆️ إيداع إلى المنصة")
    btn3 = types.KeyboardButton("⬇️ سحب من المنصة")
    btn4 = types.KeyboardButton("🌐 المنصة")
    btn5 = types.KeyboardButton("💬 مراسلة الدعم")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    bot.send_message(chat_id, "القائمة الرئيسية:", reply_markup=markup)

def get_webapp_keyboard():
    markup = types.InlineKeyboardMarkup()
    web_app = types.WebAppInfo(url="https://promisingprogrammer22-ux.github.io/myfirstbot/games_platform.html")
    markup.add(types.InlineKeyboardButton("🌐 افتح منصة الألعاب والتحديات", web_app=web_app))
    return markup

print("البوت يعمل الآن وعرض تفاصيل الحساب الشاملة مفعل بنجاح...")
bot.polling()