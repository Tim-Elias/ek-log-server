import cv2
from pyzbar.pyzbar import decode
from PIL import Image
import io
import numpy as np
import telebot
import requests
import json
from botocore.client import Config
from botocore.exceptions import ClientError
import boto3
import base64
import hashlib
from dotenv import load_dotenv
import os
import speech_recognition as sr
from pydub import AudioSegment

load_dotenv()

s3 = boto3.client(
        's3',
        endpoint_url=os.getenv('ENDPOINT_URL'),
        region_name=os.getenv('REGION_NAME'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        config=Config(s3={'addressing_style': 'path'})
    )

# Создаем сессию с постоянными учетными данными
session = boto3.Session(s3)
bucket_name = os.getenv('BUCKET_NAME')

url_1=os.getenv('URL_1')
url_2=os.getenv('URL_2')


#распознавание qr-code
def get_QR(image):
    # Распознавание QR-кодов на изображении
    qr_codes = decode(image)

    if qr_codes:
        qr_data = qr_codes[0].data.decode('utf-8')
        print(f"Найден QR-код: {qr_data}")
        return qr_data
    else:
        print("QR-код не найден")

def convert_image_to_base64(image):
    # Преобразование изображения OpenCV в формат байтов
    _, buffer = cv2.imencode('.jpg', image)
    # Преобразование байтов в строку Base64
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return base64_str


#отправление пост запроса
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

def object_exists(bucket: str, key: str) -> bool:
    try:
        # Пытаемся получить метаданные объекта
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        # Проверяем ошибку "404 Not Found"
        if e.response['Error']['Code'] == '404':
            return False
        # Другие ошибки (например, проблемы с правами доступа) могут также возникнуть
        else:
            raise

def hash_string(data: str, algorithm: str = 'sha256') -> str:
    # Создаем объект хэш-функции
    hash_obj = hashlib.new(algorithm)
    # Обновляем объект хэш-функции данными (строка должна быть закодирована в байты)
    hash_obj.update(data.encode('utf-8'))
    # Получаем хэш-сумму в виде шестнадцатеричной строки
    return hash_obj.hexdigest()

def post_request(qr_data, s3_file_key, headers):
    url=url_2
    payload = {'Number' : qr_data, 'hash' : s3_file_key}
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    if response.status_code == 200:
        try:
            #print('успешно')
            return response.json()
        except ValueError:
            #print("Response is not a valid JSON")
            return {'error': 'Response is not a valid JSON'}
    else:
        #print(f"Request failed with status code {response.status_code}")
        return {'error' : "Request failed"}


#загрузка данных на s3
def post_s3(data, ext):
    try:
        hash = hash_string(data,'sha256')
        s3_file_key=f'{hash}.{ext}'
        #print(s3_file_key)
        #проверяем есть ли уже такой объект в бакете
        if not object_exists(bucket_name, s3_file_key):    
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_file_key,
                Body=data.encode('utf-8'),  # Преобразуем строку в байты
                ContentType='application/json'
                )
            response={'status' : 'created', 'data' : s3_file_key}
            #print('успешно загружено')
            return response, s3_file_key
        else:
            response={'status' : 'exists', 'data' : s3_file_key}
            #print('уже сущуствует')
            return response, s3_file_key
    except requests.RequestException as e:
        response={'status' : 'error', 'error' : str(e)}
        #print({"error": str(e)}), 500
        return response
        
def resize_image(image, scale_factor=2.0):
    # Увеличиваем изображение в два раза
    width = int(image.shape[1] * scale_factor)
    height = int(image.shape[0] * scale_factor)
    dim = (width, height)
    resized_image = cv2.resize(image, dim, interpolation=cv2.INTER_CUBIC)
    return resized_image

def handle_image(message, is_document):

    try:
        if is_document:
            file_info = bot.get_file(message.document.file_id)
        else:
            file_info = bot.get_file(message.photo[-1].file_id)
        # Получаем информацию о файле и его содержимом
        #file_info = bot.get_file(message.photo[-1].file_id)
        file_path = file_info.file_path
        # Определяем расширение файла
        file_extension = file_path.split('.')[-1]

        # Скачиваем файл в память
        downloaded_file = bot.download_file(file_path)

        image_stream = io.BytesIO(downloaded_file)
        pil_image = Image.open(image_stream)
        # Проверяем формат изображения
        pil_image = pil_image.convert("RGB")
        cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        # Преобразование изображения в Base64
        base64_image = convert_image_to_base64(cv_image)
        #print(base64_image)
        cv_image=resize_image(cv_image, scale_factor=2.0)
        # Обработка изображения
        qr_data=get_QR(cv_image)
        if qr_data==None:
            bot.reply_to(message, f"Не могу распознать QR-код")
        else:
            #print(qr_data)
            payloads={"Number" : qr_data}
            headers = {'Content-Type': 'application/json'}
            response=post_and_process(payloads, headers)
            #print(response)
            if response.get('status')=='ok':
                #print('ok')
                status, s3_file_key=post_s3(base64_image, file_extension)
                #print(status)
                error=post_request(qr_data, s3_file_key, headers)
                #print(error)
                if error.get('error')==False:
                    #print('error false')
                    if status['status']=='created':
                        bot.reply_to(message, f"Скан успешно сохранен и привязан к накладной '{qr_data}'")
                    elif status['status']=='exists':
                        bot.reply_to(message, f"Скан уже существует и привязан к накладной '{qr_data}'")
                    else:
                        bot.reply_to(message, f"Ошибка при записи в хранилище")
                else:
                    #print('error не false')
                    bot.reply_to(message, f"Ошибка при записи в хранилище")
            else:
                bot.reply_to(message, f"Ошибка при записи в хранилище. Error: {response.get('data')}")

    except Exception as e:
        #print(f"Ошибка: {e}")
        try:
            bot.reply_to(message, "Произошла ошибка при обработке изображения.")
        except:
            print("Произошла ошибка при ответе на сообщение")


tg_api_token=os.getenv('TG_API_TOKEN')
bot = telebot.TeleBot(tg_api_token)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я ваш бот. Чем могу помочь?")

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

# Обработчик фотографий
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    handle_image(message, is_document=False)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    # Проверяем, является ли документ изображением
    file_name = message.document.file_name
    if file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
        handle_image(message, is_document=True)
    else:
        bot.reply_to(message, "Пожалуйста, отправьте изображение в формате JPG или PNG.")

@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio(message):
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
        bot.reply_to(message, f"Получено аудио в формате: {file_format}")
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.reply_to(message, f"Произошла ошибка: {e}")

# Запуск бота
bot.polling()