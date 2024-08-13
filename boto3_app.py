from flask import Flask, request, jsonify, abort
import requests
import json
import boto3
from botocore.client import Config
import hashlib
from botocore.exceptions import ClientError
from functools import wraps
from dotenv import load_dotenv
import os

app = Flask(__name__)

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

file_service_secret_key = os.getenv('SECRET_KEY')

def hash_string(data: str, algorithm: str = 'sha256') -> str:
    # Создаем объект хэш-функции
    hash_obj = hashlib.new(algorithm)
    # Обновляем объект хэш-функции данными (строка должна быть закодирована в байты)
    hash_obj.update(data.encode('utf-8'))
    # Получаем хэш-сумму в виде шестнадцатеричной строки
    return hash_obj.hexdigest()

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

def get_object_content(key: str) -> str:
    try:
        # Получаем объект из корзины
        response = s3.get_object(Bucket=bucket_name, Key=key)
        # Читаем и декодируем содержимое объекта
        content = response['Body'].read().decode('utf-8')
        return content
    except ClientError as e:
        # Проверяем ошибку "404 Not Found"
        if e.response['Error']['Code'] == '404':
            return None
        else:
            raise


def requires_secret_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Получаем secret_key из заголовков запроса
        secret_key = request.headers.get('key')
        
        # Проверяем, совпадает ли он с правильным значением
        if secret_key != file_service_secret_key:
            return jsonify({'error': 'Invalid secret key'}), 403
        
        return f(*args, **kwargs)
    return decorated_function



# Маршрут для проверки статуса приложения
@app.route('/')
def home():
    return "The service is running."

@app.route('/get-object/<file_id>', methods=['GET'])
@requires_secret_key
def get_request(file_id):
    # Получаем имя объекта из параметров запроса
    #file_id = request.args.get('file_id')
    
    # Отладочный вывод
    print(f"Received request with file_id: {file_id}")

    if not file_id:
        abort(400, description="Параметр 'file_id' обязателен.")

    # Получаем содержимое объекта
    content = get_object_content(file_id)
    
    if content is None:
        abort(404, description="Объект не найден.")
    
    # Возвращаем содержимое объекта в виде ответа
    return jsonify({'content': content})


@app.route('/post-object', methods=['POST'])
@requires_secret_key
def post_request():
    data = request.json  # Получаем данные из тела запроса
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    try:
        #response = json.loads(data)
        response_body=data['data']
        hash_string=hash_string(response_body,'sha256')
        s3_file_key=f'{hash_string}'
        #проверяем есть ли уже такой объект в бакете
        response = s3.list_objects_v2(Bucket=bucket_name)
        if not (bucket_name, s3_file_key):    
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_file_key,
                Body=response_body.encode('utf-8'),  # Преобразуем строку в байты
                ContentType='application/json'
            )
            print(f'JSON-данные успешно загружены в {bucket_name}/{s3_file_key}')
        else:
            print('Такой файл уже существует')
        return s3_file_key
        # Возвращаем ответ от внешнего API клиенту
        #return jsonify(response.json()), response.status_code
        #вместо джейсона мы должны будем возвращать ключ после помещения файла в базу

    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)