from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import parser
from apscheduler.schedulers.background import BackgroundScheduler
import json
from flask import Flask, jsonify
import requests
from dotenv import load_dotenv
import os

app = Flask(__name__)




load_dotenv()

username = os.getenv('DB_USERNAME')
password = os.getenv('DB_PASSWORD')
host = os.getenv('DB_HOST')
port = os.getenv('DB_PORT')
database = os.getenv('DB_DATABASE')
ek_url = os.getenv('EK_URL')

print(username, password)
DATABASE_URL = f'postgresql://{username}:{password}@{host}:{port}/{database}'



# Создание базы данных и настройка SQLAlchemy
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

# Определение модели для таблицы DataRecord
class DataRecord(Base):
    __tablename__ = 'data_record'
    
    id = Column(String, primary_key=True)
    number = Column(String)
    date = Column(String)
    type = Column(String)
    user = Column(String)
    uuid = Column(String)
    label = Column(String)
    hash = Column(String)
    value = Column(String)

# Создание таблицы в базе данных (если она еще не создана)
Base.metadata.create_all(engine)

# Добавление новых данных
def add_data_record(data):
    try:
        record = DataRecord(
            id=data['id'],
            number=data['number'],
            date=data['date'],
            type=data['type'],
            user=data['user'],
            uuid=data['uuid'],
            label=data['label'],
            hash=data['hash'],
            value=data['value']
        )
        session.add(record)
        session.commit()
        print("Data record added successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()



def post_ids(ids):
    url = f'{ek_url}/deletelog/delete'
    headers = {'Content-Type': 'application/json'}
    body = {"ids": ids}
    try:
        response = requests.post(url, json=body, headers=headers)
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                print("Response is not a valid JSON")
                return {'error': 'Response is not a valid JSON'}
        else:
            print(f"Received unexpected status code {response.status_code}")
            return {'error': f"Received unexpected status code {response.status_code}"}
    except Exception as e:
        print(f"An error occurred while making POST request: {e}")
        return {'error': str(e)}


# Функция для загрузки данных из JSON-файла и добавления в базу данных
def load_data_from_json(json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if isinstance(data, list):  # Если данные представляют собой список объектов
                ids=[]
                for item in data:
                    add_data_record(item)
                    ids.append(item['id']) # После добавления всех записей в базу данных, получить список ID
              
                response = post_ids(ids)  # Выполнить POST запросы по этим ID
                print(response)  # Вывести ответы
                global error
                error=response["error"]
            else:
                print("JSON file does not contain a list of records.")
    except Exception as e:
        print(f"An error occurred while loading JSON: {e}")



def fetch_and_store_data():
    
    url = f'{ek_url}/getlog/get'
    payload = {'key1': 'value1', 'key2': 'value2'}
    headers = {'Content-Type': 'application/json'}
    output_file = 'cleaned_response.json'
    parser.post_and_process(url, payload, headers, output_file)
    load_data_from_json(output_file)


error=False

while error==False:
    fetch_and_store_data()
#scheduler = BackgroundScheduler()
#scheduler.add_job(func=fetch_and_store_data, trigger="interval", minutes=10)
#scheduler.start()




# Маршрут для проверки статуса приложения
@app.route('/')
def home():
    return "Data fetching and storing service is running."

@app.route('/data/get-by-id/<id>', methods=['GET'])
def get_data_by_id(id):
    try:
        # Запрос к базе данных для получения записи по ID
        record = session.query(DataRecord).filter_by(id=id).first()
        if record:
            # Если запись найдена, возвращаем её в формате JSON
            result = {
                'id': record.id,
                'number': record.number,
                'date': record.date,
                'type': record.type,
                'user': record.user,
                'uuid': record.uuid,
                'label': record.label,
                'hash': record.hash,
                'value': record.value
            }
            return jsonify(result)
        else:
            # Если запись не найдена, возвращаем 404 ошибку
            return jsonify({'error': 'Record not found'}), 404
    except Exception as e:
        # Обработка возможных ошибок
        return jsonify({'error': str(e)}), 500
    

@app.route('/data/get-by-uuid/<uuid>', methods=['GET'])
def get_records_by_uuid(uuid):
    try:
        # Выполнение запроса к базе данных для получения всех записей с заданным uuid
        records = session.query(DataRecord).filter_by(uuid=uuid).all()
        
        if records:
            # Формирование списка записей в формате JSON
            result = [
                {
                    'id': record.id,
                    'number': record.number,
                    'date': record.date,
                    'type': record.type,
                    'user': record.user,
                    'uuid': record.uuid,
                    'label': record.label,
                    'hash': record.hash,
                    'value': record.value
                } for record in records
            ]
            return jsonify(result)
        else:
            # Записи не найдены
            return jsonify({'message': 'No records found for the given UUID'}), 404
    except Exception as e:
        # Ошибка при выполнении запроса
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
