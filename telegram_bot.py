import cv2
from pyzbar.pyzbar import decode
from PIL import Image
import io
import numpy as np
import telebot
from telebot import types
import requests
import json
from botocore.client import Config
from botocore.exceptions import ClientError
import boto3
import base64
import hashlib
from dotenv import load_dotenv
import os


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
invoice=None
base64_image=None
file_extension=None

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

def post_request(qr_data, s3_file_key, status, headers):
    url=url_2
    payload = {"Number" : f"{qr_data}", "hash" : f"{s3_file_key}", "status" : f"{status}"}
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
            print(s3_file_key)
            return response, s3_file_key
        else:
            print(s3_file_key)
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

def invoice_processing(message, status):
    global invoice, base64_image, file_extension
    payloads={"Number" : invoice}
    headers = {'Content-Type': 'application/json'}
    response=post_and_process(payloads, headers)
    if response.get('status')=='ok':
        status_s3, s3_file_key=post_s3(base64_image, file_extension)
        result=post_request(invoice, s3_file_key, status, headers)
        print(result)
        #print(status_s3)
        if result.get('error')==False:
            if status_s3['status']=='created':
                bot.send_message(message, f"Скан успешно сохранен и привязан к накладной '{invoice}'. {result.get('data')}")
            elif status_s3['status']=='exists':
                bot.send_message(message, f"Скан уже существует и привязан к накладной '{invoice}'. {result.get('data')}")
            else:
                #print('Ошибка при записи в s3')
                bot.send_message(message, f"Ошибка при записи в хранилище s3")
        else:
            #print('Ошибка при записи в 1c')
            error_msg=result.get('error_msg')
            bot.send_message(message, f"Ошибка при записи в 1с. Error: {error_msg}")
    else:
        bot.send_message(message, f"Ошибка при поиске накладной. Error: {response.get('data')}")

def handle_image(message, is_document):
    global invoice, base64_image, file_extension
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
        invoice=get_QR(cv_image)
        if invoice==None:
            bot.reply_to(message, f"Не могу распознать QR-код")
        else:
            # Отправляем сообщение с выбором дальнейших действий
            markup = types.ReplyKeyboardMarkup(row_width=3)
            button1 = types.KeyboardButton("Доставка накладной")
            button2 = types.KeyboardButton("Получение накладной")
            button3 = types.KeyboardButton("Прочее")
            markup.add(button1, button2, button3)

            bot.send_message(message.chat.id, f"Выберите действие с накладной {invoice}:", reply_markup=markup)
            

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

# Обработка выбора кнопки
@bot.message_handler(func=lambda message: message.text in ["Доставка накладной", "Получение накладной", "Прочее"])
def handle_action(message):
    global invoice, base64_image, file_extension
    
    if invoice is None:
        bot.send_message(message.chat.id, "Извините, накладная не найдена. Отправьте заново.")
        return

    if message.text == "Доставка накладной":
        bot.send_message(message.chat.id, f"Вы указали, что накладная {invoice} доставлена.")
        # Логика для Действия 1
        status="delivered"
        invoice_processing(message.chat.id, status)

    elif message.text == "Получение накладной":
        bot.send_message(message.chat.id, f"Вы указали, что накладная {invoice} получена.")
        # Логика для Действия 2
        status="received"
        invoice_processing(message.chat.id, status)

    elif message.text == "Прочее":
        bot.send_message(message.chat.id, "Вы выбрали прочее.")
        status=""
        invoice_processing(message.chat.id, status)
        #bot.send_message(message.chat.id, "Вы выбрали Действие 3.")
        # Логика для Действия 3
        # Пример: сохранение файла или дальнейшая обработка

    # После действия убираем клавиатуру
    bot.send_message(message.chat.id, "Действие с накладной завершено.", reply_markup=types.ReplyKeyboardRemove())

# Запуск бота
bot.polling()