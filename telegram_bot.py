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
def post_s3(data):
    try:
        s3_file_key=hash_string(data,'sha256')
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
        


api_token=os.getenv('API_TOKEN')
bot = telebot.TeleBot(api_token)

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
    try:
        # Получаем информацию о файле и его содержимом
        file_info = bot.get_file(message.photo[-1].file_id)
        file_path = file_info.file_path

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
        # Обработка изображения
        qr_data=get_QR(cv_image)
        if qr_data==None:
            bot.reply_to(message, f"Не смогу рапознать QR-код")
        else:
            #print(qr_data)
            payloads={"Number" : qr_data}
            headers = {'Content-Type': 'application/json'}
            response=post_and_process(payloads, headers)
            #print(response)
            if response.get('status')=='ok':
                #print('ok')
                status, s3_file_key=post_s3(base64_image)
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
        bot.reply_to(message, "Произошла ошибка при обработке изображения.")

    

# Запуск бота
bot.polling()