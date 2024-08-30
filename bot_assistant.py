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
from telebot.types import BotCommand

load_dotenv()


# First, we create a EventHandler class to define
# how we want to handle the events in the response stream.



# Функция для очистки результата от ненужного текста
def clean_text(text: str) -> str:
    # Удаление начального текста
    cleaned_text = re.sub(r'^Text\(annotations=\[\], value=\'\w+\'\)', '', text)
    # Удаление других возможных нежелательных частей
    cleaned_text = cleaned_text.strip()
    return cleaned_text
#конвертация изображения в base64
def convert_image_to_base64(image):
    # Преобразование изображения OpenCV в формат байтов
    _, buffer = cv2.imencode('.jpg', image)
    # Преобразование байтов в строку Base64
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return base64_str

def extract_text_from_messages(messages):
    text_content = ""
    for message in messages.data:
        for content_block in message.content:
            if content_block.type == 'text':
                text_content += content_block.text.value + "\n"
    return text_content.strip()

def convert_image_to_base64(image):
    # Преобразование изображения OpenCV в формат байтов
    _, buffer = cv2.imencode('.jpg', image)
    # Преобразование байтов в строку Base64
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return base64_str

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
    __tablename__ = 'user_records'
    
    user_id = Column(String, primary_key=True)
    thread_id = Column(String)
#Определение модели для таблицы tokens
class ThreadRecord(Base):
    __tablename__ = 'tokens'
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
            #date=data['date'],
            #time=data['time']
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
        file_name=f"/image/{thread_id}.{file_extension}"
        response = upload_image_to_openai(downloaded_file, file_name)
        print(response)
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
        response=create_run(user_input, thread_id, user_id)
        # Выводим информацию о загруженном файле"""
        bot.reply_to(message, response)
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.reply_to(message, f"Произошла ошибка: {e}")

def create_run(user_input, thread_id, user_id):
    # Добавление сообщения пользователя в поток
    client.beta.threads.messages.create(thread_id=thread_id,
                                      role="user",
                                      content=user_input)
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
                print(response)
            else:
                response = "Ошибка получения ответа от помощника."
            break
        elif run_status.status=='incomplete':
            #print(run_status.json())
            response=f'Ошибка получения ответа от помощника. {run_status.status}'
        else:
            print(run_status.status)
        time.sleep(1)  # Ожидание одной секунды перед следующей проверкой

    # Получение и возврат последнего сообщения от помощника
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    if messages.data:
        print(messages.data[0].content[0])
        response = messages.data[0].content[0].text.value  # Здесь response является строкой
    else:
        response = "Ошибка получения ответа от помощника."
    return response


openai.api_key=os.getenv('OPENAI_API_KEY')
openai_api_key=os.getenv('OPENAI_API_KEY')
tg_api_token=os.getenv('TG_API_TOKEN')
bot = telebot.TeleBot(tg_api_token)
assistant_id=os.getenv('ASSISTANTS_ID')
client = openai.OpenAI()
# Сохранение состояния для пользователей (хранение сессий)
user_threads = {}


# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    thread = openai.beta.threads.create()
    user_threads[user_id] = thread.id
    #event_handler = EventHandler()
    user_id=str(user_id)
    thread_id=str(thread.id)
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
    bot.reply_to(message, "Привет! Я твой бот. Задай мне вопрос.")

# Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_question(message):
    user_id = message.chat.id
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
    user_input=message.text
    thread_id = user_threads[user_id]
    print(user_input)
    response=create_run(user_input, thread_id, user_id)
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
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id

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
        response=create_run(user_input, thread_id, user_id)
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