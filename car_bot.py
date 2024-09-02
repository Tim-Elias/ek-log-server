import openai
import cv2
import telebot
from typing_extensions import override
#from openai import AssistantEventHandler
from PIL import Image
import io
from io import BytesIO
from pydub import AudioSegment
import os
from dotenv import load_dotenv
import re
from sqlalchemy import create_engine, Column, String, Integer, Date, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, exists, update
import sqlalchemy
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import time
import requests
import json
import base64
import gspread
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from telebot.types import BotCommand
from googleapiclient.http import MediaIoBaseUpload

load_dotenv()



#загружаем изображение в openai, чтобы ассистент мог с ним работать
def upload_image_to_openai(file_bytes, file_name):
    try:
        # Создаем файловый объект из байтов
        file = io.BytesIO(file_bytes)
        file.name = file_name  # Задаем имя файла, если необходимо
        
        # Загружаем файл в OpenAI
        response = client.files.create(
            file=file,
            purpose='vision'  # или другая цель
        )
        return response
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return None

#подгружаем базу данных
username = os.getenv('DB_USERNAME')
password = os.getenv('DB_PASSWORD')
host = os.getenv('DB_HOST')
port = os.getenv('DB_PORT')
database = os.getenv('DB_DATABASE')

DATABASE_URL = f'postgresql://{username}:{password}@{host}:{port}/{database}'

# Создание базы данных и настройка SQLAlchemy
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()
Base = sqlalchemy.orm.declarative_base()


# Определение модели для таблицы user_records
class DataRecord(Base):
    __tablename__ = 'user_records_cars'
    
    user_id = Column(String, primary_key=True)
    thread_id = Column(String)

#Определение модели для таблицы tokens
class ThreadRecord(Base):
    __tablename__ = 'tokens_cars'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String)
    thread_id = Column(String)
    prompt_tokens = Column(String)
    completion_tokens = Column(String)
    total_tokens = Column(String)
    model = Column(String)
    date = Column(Date, default=lambda: datetime.now(timezone.utc).date())
    time = Column(Time, default=lambda: datetime.now(timezone.utc).time())

# Создание таблицы в базе данных (если она еще не создана)
Base.metadata.create_all(engine)

#добавление данных в таблицу tokens
def add_thread_record(data):
    try:
        record=ThreadRecord(
            user_id=data['user_id'],
            thread_id=data['thread_id'],
            prompt_tokens=data['prompt_tokens'],
            completion_tokens=data['completion_tokens'],
            total_tokens=data['total_tokens'],
            model=data['model'],
        )
        session.add(record)
        session.commit()
        print("Data record added successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()

# Добавление новых данных в таблицу user_records
def add_data_record(data):
    try:
        record = DataRecord(
            user_id=data['user_id'],
            thread_id=data['thread_id'],
        )
        session.add(record)
        session.commit()
        print("Data record added successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()

#класс BytesIO с именем
class NamedBytesIO(BytesIO):
    def __init__(self, initial_bytes, name):
        super().__init__(initial_bytes)
        self.name = name

#транскрибация аудио
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

#работа с изображением
def handle_image(message, user_id, thread_id, is_document):
    try:
        if is_document:
            file_info = bot.get_file(message.document.file_id)
        else:
            file_info = bot.get_file(message.photo[-1].file_id)
        file_path = file_info.file_path
        file_extension = file_path.split('.')[-1]
        downloaded_file = bot.download_file(file_path)
        username = message.from_user.username
        file_name=f"/image/{username}_{thread_id}.{file_extension}"
        link = upload_to_drive(file_name, downloaded_file)
        result=update_google_sheet(thread_id, link)
        response = upload_image_to_openai(downloaded_file, file_name)
        #print(response)
        file_id=response.id
        # Формируем контент для Assistant API
        content = [
            {
                "type": "text",
                "text": "Тебе прислали изображение. Будь готов его проанализировать и ответить на вопросы"
            },
            {
                "type": "image_file",
                "image_file": {"file_id": file_id}
            }
        ]
        # Отправляем сообщение в поток Assistant API
        user_input=content
        response, is_put=create_run(message, user_input, thread_id, user_id)
        # Выводим информацию о загруженном файле"""
        bot.reply_to(message, response)
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.reply_to(message, f"Произошла ошибка: {e}")

#запускаем новый ран с user_input
def create_run(message, user_input, thread_id, user_id):
    # Добавление сообщения пользователя в поток
    client.beta.threads.messages.create(thread_id=thread_id,
                                      role="user",
                                      content=user_input)
    is_put=False
    # Запуск помощника
    run = client.beta.threads.runs.create(thread_id=thread_id,
                                        assistant_id=assistant_id,
                                        max_prompt_tokens = 5000,
                                        max_completion_tokens = 10000)
    # Проверка необходимости действия в ходе выполнения
    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id,
                                                   run_id=run.id)
    
    # Вывод статуса выполнения: {run_status.status}
        if run_status.status == 'completed':
            run_data=run_status.json()
            run_data=json.loads(run_data)
            #print(run_data)
            new_record={
                "user_id" : user_id,
                "thread_id" : thread_id,
                "prompt_tokens" : run_data.get("usage", {}).get("prompt_tokens"),
                "completion_tokens" : run_data.get("usage", {}).get("completion_tokens"),
                "total_tokens" : run_data.get("usage", {}).get("total_tokens"),
                "model" : run_data.get("model")
            }
            add_thread_record(new_record)
            # Получение и возврат последнего сообщения от помощника
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            if messages.data:
                #print(messages.data[0].content[0])
                response = messages.data[0].content[0].text.value  # Здесь response является строкой
            else:
                response = "Ошибка получения ответа от помощника."
            break
        elif run_status.status=='incomplete':
            #print(run_status.json())
            response=f'Ошибка получения ответа от помощника. {run_status.status}'
        elif run_status.status == 'requires_action':
        # Обработка вызова функции
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                if tool_call.function.name == "get_car_data":
                    # Создание лидов
                    arguments = json.loads(tool_call.function.arguments)
                    output = 'true'
                    client.beta.threads.runs.submit_tool_outputs(thread_id=thread_id,
                                                                run_id=run.id,
                                                                tool_outputs=[{
                                                                    "tool_call_id":
                                                                    tool_call.id,
                                                                    "output":
                                                                    json.dumps(output)
                                                                }])
                    print(arguments)
                    put_data_into_sheets(message, thread_id, arguments)
                    is_put=True

        else:
            print(run_status.status)
        time.sleep(1)  # Ожидание одной секунды перед следующей проверкой

    # Получение и возврат последнего сообщения от помощника
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    if messages.data:
        #print(messages.data[0].content[0])
        
        response = messages.data[0].content[0].text.value  # Здесь response является строкой
        print(response)
    else:
        response = "Ошибка получения ответа от помощника."
    return response, is_put

#получаем данные для аутентификации в гугле
def get_credentials():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    creds = flow.run_local_server(port=63515)  # Убедитесь, что порт совпадает
    return creds

#добавление данных из функции в гугл таблицы
def put_data_into_sheets(message, thread_id, arguments):
    creds = get_credentials()
    #print('получили creds')
    # Создание клиента для доступа к Google Sheets API
    service = build('sheets', 'v4', credentials=creds)
    # Чтение данных из таблицы
    sheet = service.spreadsheets().values().get(spreadsheetId=spread_sheet_id, range='Sheet1!B:H').execute()
    values = sheet.get('values', [])

    # Поиск строки с нужным thread_id
    row_number = None
    for i, row in enumerate(values):
        if row and row[0] == thread_id:
            row_number = i + 1  # Нумерация строк начинается с 1
            break

    # Чтение данных
    current_datetime = str(datetime.now())
    sheet = service.spreadsheets()
    car_model=arguments.get('car_model')
    car_number=arguments.get('car_number')
    damage=arguments.get('damage')
    text=arguments.get('text')
    # Новые данные, которые вы хотите добавить (список списков)
    new_values = [
        [current_datetime, car_model, car_number, damage, text]
    ]
        # Подготовка тела запроса
    body = {
        'values': new_values
    }
    if row_number is not None:
        # Обновление ячейки в столбце G (6-й столбец)
        range_name = f'Sheet1!C{row_number}:G{row_number}'
        result = service.spreadsheets().values().update(
            spreadsheetId=spread_sheet_id, range=range_name,
            valueInputOption='RAW', body=body).execute()
    #print(f'{result.get("updates").get("updatedCells")} ячеек обновлено.')
    if result:
        bot.send_message(message.chat.id,"Данные успешно загружены в таблицу")
    else:
        bot.send_message(message.chat.id,"Возникла проблема с внесением данных в таблицу")

#загрузка изображения в гугл диск, возвращает ссылку
def upload_to_drive(file_name, file_data):
    creds = get_credentials()
    # Подключение к Google Drive API
    service = build('drive', 'v3', credentials=creds)
    
    # Загрузка файла на Google Диск
    file_metadata = {
        'name': file_name,
        'parents': [folder_id],  # Здесь указываем ID папки
        'mimeType': 'image/jpeg'
    }
    media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype='image/jpeg')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    # Получение ссылки на файл
    file_id = file.get('id')
    service.permissions().create(fileId=file_id, body={'role': 'reader', 'type': 'anyone'}).execute()
    link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

    return link

# Находим номер следующего пустого столбца
def find_next_empty_column(service, spreadsheet_id, row_number, start_col_letter):
    # Определяем номер стартового столбца
    start_col_index = ord(start_col_letter) - ord('A') + 1
    #print(start_col_index)
    # Формируем диапазон для получения данных от стартового столбца до конца строки
    range_name = f'Sheet1!{start_col_letter}{row_number}:Z{row_number}'
    #print(f"Запрашиваем диапазон: {range_name}")
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    
    # Получаем значения строки
    row_values = result.get('values', [[]])
    #print(f"Полученные значения: {row_values}")
    
    # Если строка не пуста, используем значения, иначе создаем пустой список нужной длины
    if row_values and row_values[0]:
        row_values = row_values[0]
    else:
        # Создаем список длиной от стартового столбца до конца (например, до Z)
        row_values = [''] * (26 - (start_col_index - 1))  # Количество столбцов от стартового до Z
    
    # Печатаем значения строки для отладки
    #print(f"Значения строки: {row_values}")
    
    # Ищем первую пустую ячейку после стартового столбца
    for i in range(start_col_index - 1, len(row_values)):
        if not row_values[i]:  # Проверяем на пустое значение
            print(f"Первая пустая ячейка: {i + 1}")
            return i + 1  # Возвращаем индекс первой пустой ячейки
    
    # Если не найдено пустых ячеек, возвращаем следующий столбец после последнего
    next_col = len(row_values) + 8
    #print(f"Следующий столбец после последнего заполненного: {next_col}")
    return next_col

# Заносим данные в строку
def insert_data_in_row(service, spreadsheet_id, data, row_number, start_col_letter):
    # Найти первую пустую ячейку
    next_empty_col = find_next_empty_column(service, spreadsheet_id, row_number, start_col_letter)
    
    # Определить диапазон для вставки данных
    end_col = next_empty_col + len(data) - 1
    range_name = f'Sheet1!{chr(ord("A") + next_empty_col - 1)}{row_number}:{chr(ord("A") + end_col - 1)}{row_number}'
    
    body = {
        'values': [data]
    }
    
    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_name,
        valueInputOption='RAW', body=body).execute()
    return result

# Добавляем ссылку на гугл диск
def update_google_sheet(thread_id, link):
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')  # Замените на ваш идентификатор таблицы

    # Чтение данных из таблицы
    range_name = 'Sheet1!A:Z'
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    values = result.get('values', [])
    
    start_col_letter = 'H'
    row_number = None
    
    # Поиск строки с нужным thread_id
    for i, row in enumerate(values):
        if row and row[1] == thread_id:
            row_number = i + 1  # Нумерация строк начинается с 1
            break
    print(row_number)
    if row_number is not None:
        insert_data_in_row(service, spreadsheet_id, [link], row_number, start_col_letter)
        return "ok"
    else:
        return "thread_id не найден"

#создание новой строки в гугл таблице
def create_new_row(username, thread_id):
    creds=get_credentials()

    # Подключение к Google Sheets API
    service = build('sheets', 'v4', credentials=creds)
    # Новые данные, которые вы хотите добавить (список списков)
    new_values = [
        [username, thread_id]
    ]
        # Подготовка тела запроса
    body = {
        'values': new_values
    }
    result = service.spreadsheets().values().append(
        spreadsheetId=spread_sheet_id,
        range='Sheet1!A:B',
        valueInputOption="RAW",  # Существуют также варианты 'USER_ENTERED' для формул и форматирования
        insertDataOption="INSERT_ROWS",  # Можно использовать 'INSERT_ROWS' или 'OVERWRITE'
        body=body
    ).execute()
    #print(f'{result.get("updates").get("updatedCells")} ячеек обновлено.')
    
#данные
openai.api_key=os.getenv('OPENAI_API_KEY')
openai_api_key=os.getenv('OPENAI_API_KEY')
tg_api_token=os.getenv('TG_API_TOKEN_CAR')
bot = telebot.TeleBot(tg_api_token)
assistant_id=os.getenv('ASSISTANTS_ID_CAR')
client = openai.OpenAI()

# Сохранение состояния для пользователей (хранение сессий)
user_threads = {}

# Определите область доступа
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']

# Путь к вашему файлу с учетными данными
CREDS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# ID таблицы и диапазон данных
spread_sheet_id = os.getenv('SPREADSHEET_ID')
RANGE_NAME = 'Sheet1!A2:H100'
folder_id=os.getenv('FOLDER_ID')


# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    thread = openai.beta.threads.create()
    user_threads[user_id] = thread.id
    #event_handler = EventHandler()
    user_id=str(user_id)
    thread_id=str(thread.id)
    username = message.from_user.username
    create_new_row(username, thread_id)
    exists_query = session.query(exists().where(DataRecord.user_id == user_id)).scalar()
    if exists_query:
        # Выполнение запроса на обновление
        session.query(DataRecord).filter(DataRecord.user_id == user_id).update({
            DataRecord.thread_id: thread_id
        })
        # Сохранение изменений в базе данных
        session.commit()
    else:
        data={'user_id' : user_id, 'thread_id' : thread_id}
        add_data_record(data)
    
    bot.reply_to(message, "Здравствуйте. Расскажите о вашей проблеме.")

# Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_question(message):
    user_id = message.chat.id
    username = message.from_user.username
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
        thread_id = user_threads[user_id]
        create_new_row(username, thread_id)
    user_input=message.text
    thread_id = user_threads[user_id]
    print(user_input)
    response, is_put=create_run(message, user_input, thread_id, user_id)
    if is_put:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
        thread_id=user_threads[user_id]
        create_new_row(username, thread_id)
    #response = messages.data[0].content[0].text.value
    bot.reply_to(message, response)


# Обработчик фотографий
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
    #user_text=message.text
    thread_id = user_threads[user_id]
    handle_image(message, user_id, thread_id, is_document=False)


@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.chat.id
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
    #user_text=message.text
    thread_id = user_threads[user_id]
    # Проверяем, является ли документ изображением
    file_name = message.document.file_name
    if file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
        handle_image(message, user_id, thread_id, is_document=True)
    else:
        bot.reply_to(message, "Пожалуйста, отправьте изображение в формате JPG или PNG.")


@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio(message):
    user_id = message.chat.id
    username = message.from_user.username
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
        thread_id = user_threads[user_id]
        create_new_row(username, thread_id)

    thread_id = user_threads[user_id]
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
        finally:
            # Очищаем загруженный файл из памяти
            del downloaded_file
        user_input=text
        response, is_put=create_run(message, user_input, thread_id, user_id)
        if is_put:
            thread = openai.beta.threads.create()
            user_threads[user_id] = thread.id
            thread_id=user_threads[user_id]
            create_new_row(username, thread_id)
        bot.reply_to(message, response)
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.reply_to(message, f"Произошла ошибка: {e}")


def set_bot_commands(bot):
    commands = [
        BotCommand(command="/start", description="Начать новый дилог"),
    ]
    bot.set_my_commands(commands)

# Вызов функции при запуске бота
set_bot_commands(bot)


# Запуск бота
try:
    bot.polling(none_stop=True)
except Exception as e:
    print(f"Ошибка: {e}")