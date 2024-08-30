import requests
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv
import os
import openai 
import base64
import cv2
import numpy as np
from PIL import Image
import json
import io
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:/Program Files/Tesseract-OCR/tesseract.exe'

app = Flask(__name__)

load_dotenv()
#проверка ориентации изображения
def check_text_orientation(image):
    # Преобразуем изображение в градации серого
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray)
    # Определяем количество символов. Если их достаточно, считаем изображение правильным.
    return len(text) > 10
#поворот изображения на 90 градусов
def rotate_image_90_degrees(image, clockwise=False):
    # Поворот изображения на 90 градусов
    if clockwise:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    else:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
#конвертация изображения в base64
def convert_image_to_base64(image):
    # Преобразование изображения OpenCV в формат байтов
    _, buffer = cv2.imencode('.jpg', image)
    # Преобразование байтов в строку Base64
    base64_str = base64.b64encode(buffer).decode('utf-8')
    return base64_str
#извлечение номера накладной с помощью openai
def get_invoice_from_image(base64_image):
    try:
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                    },
                    },
                ],
                }
            ],
            max_tokens=300,
        )
        # Извлечение содержимого content
        content = response.choices[0].message.content
        print(content)
        return content
    except Exception as e:
        print(f"Произошла ошибка: {e}")

openai.api_key=os.getenv('OPENAI_API_KEY')
client = openai.OpenAI()
prompt="""Тебе присылают курьерскую накладную. Если это она, то запиши в поле "error" "False", если же тебе прислали что-то другое, то напиши в этом поле "True".
Найди на этой картинке номер накладной и выведи его и только его в качестве ответа, все, что после номера игнорируй (например, если написано "АЗ-22-04 от 29.12.2022", то номер это  "АЗ-22-04"), 
не добавляй никаких слов от себя. Это самая крупная надпись печатными цифрами в левом или правом верхнем углу. Это запиши в поле "number".
Если номера нет, напиши "Номер накладной отсутствует".
Возвращай ответ в виде строки вида {"number" : "номер накладной", "error" : "True" или "False"}"""

@app.route('/post-image/', methods=['POST'])
def post_request():
    data=request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    try:
        base64_image=data['base64_image']
        image_data = base64.b64decode(base64_image)
        try:
            image_stream = io.BytesIO(image_data)
            pil_image = Image.open(image_stream)
            # Проверяем формат изображения
            pil_image = pil_image.convert("RGB")
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            if not check_text_orientation(cv_image):
                # Если текст не читается, поворачиваем изображение
                for _ in range(3):  # Максимум три поворота
                    cv_image = rotate_image_90_degrees(cv_image, clockwise=False)
                    if check_text_orientation(cv_image):
                        break
            base64_image=convert_image_to_base64(cv_image)
            invoice_data=get_invoice_from_image(base64_image)
            return invoice_data
        finally:
            # Закрываем изображение и поток
            pil_image.close()
            image_stream.close()
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500 
    finally:
        del image_data, image_stream, pil_image, cv_image
    


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5011)