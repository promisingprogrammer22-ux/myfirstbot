import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# توكن البوت الخاص بك
bot = telebot.TeleBot('8805488820:AAE4jM7p19R-c3MlZ5t2zcjDTOgJhVlsP-U')

bot.remove_webhook()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    name = message.from_user.first_name
    markup = InlineKeyboardMarkup(row_width=1)
    
    btn_account = InlineKeyboardButton("حسابك على المنصة", callback_data="account")
    btn_deposit = InlineKeyboardButton("إيداع الأموال", callback_data="deposit")
    
    # --- تعديل زر الألعاب ليفتح كمنصة ويب تفاعلية داخل التيليجرام ---
    # استبدل الرابط أدناه برابط موقع الألعاب الخاص بك (مثل رابط استضافة GitHub Pages للملف)
    game_url = 'https://example.com/games_platform.html'
    btn_games = InlineKeyboardButton("منصة الألعاب 🎮", web_app=WebAppInfo(url=game_url))
    
    btn_withdraw = InlineKeyboardButton("سحب الأموال", callback_data="withdraw")
    
    markup.add(btn_account, btn_deposit, btn_games, btn_withdraw)
    
    bot.send_message(message.chat.id, f"Hello {name}, welcome to our bot! 🚀", reply_markup=markup)

# استقبال الضغطات على الأزرار الأخرى
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    # --- قسم القائمة الرئيسية ---
    if call.data == "account":
        bot.answer_callback_query(call.id, "جلب معلومات حسابك...")
        bot.send_message(message_chat_id := call.message.chat.id, "📊 معلومات حسابك هنا.")

# تشغيل البوت
bot.polling()