import telebot
from dotenv import load_dotenv
import os
import requests
import json
from flask import Flask, jsonify, request
import threading


load_dotenv()

app = Flask(__name__)


tg_api_token=os.getenv('TG_API_TOKEN_1C')
bot = telebot.TeleBot(tg_api_token)
base_url='https://kinetika-server.tw1.su/http/hs/agent'
headers_tg={
        'Content-Type': 'application/x-www-form-urlencoded'
    }
headers_1c={'Content-Type': 'application/json'}

url_tg=f'https://api.telegram.org/bot{tg_api_token}/sendMessage'

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    chat = message.chat
    user_id=user.id
    message_text=message.text
    username=user.username
    if len(message_text)>7:
        message_text=message_text.split(' ')
        #print(message_text)
        key=message_text[1]
        print(key)
        # Отправка ответа пользователю (по желанию)
        endpoint='/tguser/add'
        payload={"key" : key, "username" : username, "id" : user_id}
        print(payload)
        response=requests.post(base_url+endpoint, data=json.dumps(payload), headers=headers_1c)
        print(response.text)
        print(response)
        bot.reply_to(message, f"Ваше сообщение получено! {response.text}")
    else:
        bot.reply_to(message, f"Не получил значение 'key'.")

# Обработка команды /help
@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, "Команды бота:/n/start - Начать работу с ботом/n/help - Получить справку")

# Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def echo_message(message):
    user = message.from_user
    user_id=str(user.id)
    endpoint='/tgmessage/post'
    payload={"userid" : user_id, "text" : message.text}
    response=requests.post(base_url+endpoint,data=json.dumps(payload), headers=headers_1c)
    print(response.text)
    bot.reply_to(message, f"{response.text}")



# Flask маршруты
@app.route('/')
def home():
    return 'Hello from Flask!'

@app.route('/sent-message/', methods=['POST'])
def post_request():
    json_data = request.json  # Получение данных из тела POST запроса
    data={"chat_id" : json_data['userid'], "text" : json_data['text']}
    print(data)
    response=requests.post(url_tg, data=data, headers=headers_tg)
    return response.json()

# Запуск Flask в отдельном потоке
def run_flask():
    app.run(debug=False, host='0.0.0.0', port=5010)


def run_bot():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    # Запуск Flask в отдельном потоке
    threading.Thread(target=run_flask).start()
    
    # Запуск Telegram бота в основном потоке
    run_bot()