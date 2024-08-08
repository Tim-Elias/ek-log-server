import requests
import json
import re
import chardet

def clean_value(value):
    """ Clean unnecessary characters from the value. """
    value = re.sub(r'\\u0009', '', value)
    value = re.sub(r'\\n', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value

def extract_json_objects(response_text):
    """ Extract JSON-like structures from the response text. """
    json_objects = re.findall(r'\{(?:[^{}"]|"(?:\\.|[^"])*")*\}', response_text)
    return json_objects

def process_json_objects(json_objects):
    """ Process each JSON object to extract and clean data. """
    cleaned_data = []
    
    for json_obj in json_objects:
        try:
            obj = json.loads(json_obj)
            cleaned_obj = {
                'id': obj.get('id'),
                'number': obj.get('number'),
                'date': obj.get('date'),
                'type': obj.get('type'),
                'user': obj.get('user'),
                'uuid': obj.get('uuid'),
                'label': obj.get('label'),
                'hash': obj.get('hash'),
                'value': clean_value(obj.get('value', ''))
            }
            cleaned_data.append(cleaned_obj)
        except json.JSONDecodeError:
            print(f"Error decoding JSON: {json_obj}")
    
    return cleaned_data

def save_to_json_array(data, output_file):
    """ Save the cleaned data to a JSON array file. """
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def post_and_process(url, payload, headers, output_file):
    """ Perform POST request and process the response. """
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        
        if response.status_code == 200:
            encoding = chardet.detect(response.content)['encoding']
            response_text = response.content.decode(encoding, errors='replace')
            
            json_objects = extract_json_objects(response_text)
            cleaned_data = process_json_objects(json_objects)
            if cleaned_data:
                save_to_json_array(cleaned_data, output_file)
                print(f"Data saved to {output_file}")
            else:
                print("No data to save")
        else:
            print(f"Request failed with status code {response.status_code}")
    except requests.RequestException as e:
        print(f"Request error: {e}")




# Example usage
#url = 'https://kinetika-server.tw1.su/http/hs/agent/getlog/get'  # Change to your URL
#payload = {'key1': 'value1', 'key2': 'value2'}  # Change to your payload
#headers = {'Content-Type': 'application/json'}
#output_file = 'cleaned_response.json'

#post_and_process(url, payload, headers, output_file)
