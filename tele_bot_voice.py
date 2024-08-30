from PIL import Image
import io
import numpy as np
import telebot
import requests
import json
from dotenv import load_dotenv
import os
import openai 
from pydub import AudioSegment
from io import BytesIO
from telebot import types

load_dotenv()

from pydub import AudioSegment
from io import BytesIO
response=None

#класс наименованный BytesIO
class NamedBytesIO(BytesIO):
    def __init__(self, initial_bytes, name):
        super().__init__(initial_bytes)
        self.name = name
#транскрибирование аудио
def transcribe_audio(audio, file_format):
    # Create a BytesIO object with a name attribute
    audio_file = NamedBytesIO(audio, f"audio.{file_format}")
    # Ensure the BytesIO buffer is at the start
    audio_file.seek(0)
    try:
        #print('Дошло сюда')
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,  # Pass the file-like object (BytesIO)
            language="ru"  # Specify the language if needed
        )
        # Получаем текст из ответа
        transcribed_text = response.text
        #print(transcribed_text)
        return transcribed_text
    finally:
        # Закрываем файл BytesIO
        audio_file.close()
#анализ текста через GPT
def analyze_text_with_gpt(text, prompt):
    # Отправляем текст транскрипции в GPT-4-mini для анализа
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Используем нужную модель GPT
        messages=[
            {"role": "system", "content": "Вы - анализатор текста."},
            {"role": "user", "content": f'{prompt}{text}'}
        ]
    )
    
    # Извлекаем текст анализа из ответа
    analysis_text = response.choices[0].message.content
    total_tokens = response.usage.total_tokens
    #print(f"Потрачено токенов: {total_tokens}")
    return analysis_text, total_tokens
#отправление пост запроса в 1с, существует ли такая накладная
def post_and_process(payload, headers):
    """ Perform POST request and process the response. """
    try:
        url=url_1
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        #print(response)
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                #print("Response is not a valid JSON")
                return {'error': 'Response is not a valid JSON'}
        else:
            print(f"Request failed with status code {response.status_code}")
    except requests.RequestException as e:
        print(f"Request error: {e}")
#отправление пост запроса в 1с с загрузкой полученных данных
def post_request(response, headers):
    url=url_3
    payload = response
    print(payload)
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    if response.status_code == 200:
        try:
            print('успешно 1c')
            return response.json()
        except ValueError:
            #print("Response is not a valid JSON")
            return {'error': 'Response is not a valid JSON'}
    else:
        #print(f"Request failed with status code {response.status_code}")
        return {'error' : "Request failed"}
#процессинг накладной
def invoice_processing(message, response):
    invoice=response.get('number')
    #bot.send_message(message, f"Данные по накладной '{invoice}' успешно загружены.")
    #print(invoice)
    if invoice=='Номер накладной отсутствует':
            bot.send_message(message, f"Отсутствует номер накладной")
    else:
        payloads={"Number" : invoice}
        headers = {'Content-Type': 'application/json'}
        response=post_and_process(payloads, headers)
        if response.get('status')=='ok':
            #bot.send_message(message, f"Накладная '{invoice}' существует.")
            result=post_request(response, headers)
            if result.get('error')==False:
                bot.send_message(message, f"Данные по накладной '{invoice}' успешно загружены. {result.get('data')}")
            else:
                print('Ошибка при записи в 1c')
                error_msg=result.get('error_msg')
                bot.send_message(message, f"Ошибка при записи в 1с. Error: {error_msg}")
        else:
            bot.send_message(message, f"Ошибка при поиске накладной. Error: {response.get('data')}")

#данные
tg_api_token=os.getenv('TG_API_TOKEN')
bot = telebot.TeleBot(tg_api_token)
url_1=os.getenv('URL_1')
url_2=os.getenv('URL_2')
url_3=os.getenv('URL_3')
openai.api_key=os.getenv('OPENAI_API_KEY')
client = openai.OpenAI()
prompt="""
Перед тобой распознанное голосовое сообщение от доставщика, который получил или передал накладную. Это распознанный текст, поэтому некоторые слова могут быть не в тему. Проанализируй этот текст по следующим пунктам:
Пункт 1. Определи по тексту статус доставки: начата (то есть забрарали накладную или посылку у отправителя):"received", завершена (отдали посылку или накладную получателю):"delivered", возникли проблемы:"problems". Это будет 'status'. Возможны только эти три значения.
Пункт 2. Есть ли в тексте упоминание номера накладной? Номер накладной идет от первой встретившейся цифры в тексте до последней, не считая даты и времени, их надо распозновать отдельно. Дата идет либо да номера, либо после.
Если да, запиши его без пробелов и только его в качестве ответа, преобразуй распознанные русские буквы в латиницу. 
Если между цифрами есть пробелы, считай, что их нет. Если цифры записаны словами, преобразуй их в цифры, они часть номера накладной. 
Все слова между наборами цифр превращай в дефис '-'. Например, если написано "92, адрес 1-2-3-4-5-6", то номер накладной 92-123456. Или "Эн Эс Ка" это "NSK". "НСК, дефис 1, дефис 997993054" это "NSK-1-997993054".
Но если в распознаном тексте написано "1-2-1-1-7-5-4-4-7", то это просто "121175447". То есть если не сказано слова, то цифры или буквы идут подряд.
Если номер отсутствует, то напиши четко "Номер накладной отсутствует". Это будет "number"
Пункт 3.Есть ли в тексте дата и время? Если да, запиши их. Если сказано "сегодня" или "вчера", то приведи к нужной дате по внутренним часам. Если чего-от нет, оставь поле пустым. Это будут "date" и "time".
пункт 4. Есть ли в тексте упоминание Фамилии, Имени и Отчества получателя?  Если упоминаний нет, то оставь ФИО пустым. Это будет "name".
пункт 5. Запиши в поле "text" полученный тобой распознанный текст. 
Пункт 6. Все пустые значения должны заключаться в двойные кавычки, то есть выглядеть так: "". Используй везде двойные кавычки, а не одинарные.
Пункт 7. Запиши ответ в виде такой строки: {"status" : "статус доставки", "number" : "номер накладной", "date" : "дата", "time" : "время", "name" : "ФИО", "text" : "полученный тобой текст"}.
"""

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я ваш бот. Чем могу помочь?")


#обработчки входящих аудиосообщений
@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio(message):
    global response
    try:
        if message.content_type == 'voice':
            # Работа с голосовыми сообщениями
            file_info = bot.get_file(message.voice.file_id)
            file_format = 'ogg'
        elif message.content_type == 'audio':
            # Работа с аудиофайлами
            file_info = bot.get_file(message.audio.file_id)
            file_format = message.audio.mime_type.split('/')[1]  # Определяем формат аудиофайла
        # Скачиваем файл в память
        file_path = file_info.file_path
        downloaded_file = bot.download_file(file_path)
        try:
            #транскрибируем аудио
            text = transcribe_audio(downloaded_file, file_format)
            print(text)
            response, tokens=analyze_text_with_gpt(text, prompt)
            response=json.loads(response)
            print(response.get('number'))
            bot.reply_to(message, f"Вот, что мне удалось распознать: {response}")
            # Отправляем сообщение с выбором дальнейших действий
            markup = types.ReplyKeyboardMarkup(row_width=2)
            button1 = types.KeyboardButton("Да, все верно")
            button2 = types.KeyboardButton("Нет, данные неверны")
            markup.add(button1, button2)
            bot.send_message(message.chat.id, "Подтвердите распознанные данные", reply_markup=markup)
            print(f"Потрачено токенов: {tokens}")
        finally:
            # Очищаем загруженный файл из памяти
            del downloaded_file
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.reply_to(message, f"Произошла ошибка: {e}")

# Обработка выбора кнопки
@bot.message_handler(func=lambda message: message.text in ["Да, все верно", "Нет, данные неверны"])
def handle_action(message):
    global response
    invoice=response.get('number')
    #print(invoice)
    if message.text == "Да, все верно":
        #bot.send_message(message.chat.id, f"Данные о накладной {invoice} получены.")
        invoice_processing(message.chat.id, response)
        # Логика для Действия 1

    elif message.text == "Нет, данные неверны":
        bot.send_message(message.chat.id, "Проговорите данные заново.")
        # Логика для Действия 2

    # После действия убираем клавиатуру
    #bot.send_message(message.chat.id, "Действие с аудиосообщением завершено.", reply_markup=types.ReplyKeyboardRemove())

# Запуск бота
bot.polling()