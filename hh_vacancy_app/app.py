from flask import Flask, render_template, jsonify, request
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import webbrowser
import sys
from threading import Timer
import signal
import json

app = Flask(__name__)

API_URL = "https://api.hh.ru/vacancies"
DATA_FILE = "vacancies_data.json"
SETTINGS_FILE = "settings.json"

# Значения по умолчанию
DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Валидация
                settings.setdefault('query', DEFAULT_SETTINGS['query'])
                settings.setdefault('exclude', DEFAULT_SETTINGS['exclude'])
                settings.setdefault('days', DEFAULT_SETTINGS['days'])
                return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def build_search_text(query, exclude_words):
    exclude_list = [w.strip() for w in exclude_words.split(',') if w.strip()]
    exclude_str = " NOT ".join(exclude_list)
    if exclude_str:
        return f"{query} NOT {exclude_str}"
    return query

def get_vacancies_from_api():
    """Получение вакансий с API HH.ru с учётом настроек"""
    settings = load_settings()
    date_from = (datetime.now() - timedelta(days=int(settings['days']))).strftime("%Y-%m-%dT%H:%M:%S")
    search_text = build_search_text(settings['query'], settings['exclude'])

    params = {
        "text": search_text,
        "area": [113, 16],  # Россия и Беларусь
        "schedule": "remote",
        "per_page": 50,
        "page": 0,
        "date_from": date_from,
        "professional_role": 96  # Backend-разработчик
    }

    vacancies = []

    while True:
        try:
            resp = requests.get(API_URL, params=params, timeout=10)
            if resp.status_code != 200:
                print(f"Ошибка API: {resp.status_code}")
                break
            data = resp.json()

            for item in data.get("items", []):
                salary_info = item.get("salary")
                if salary_info:
                    salary_from = salary_info.get('from') or ''
                    salary_to = salary_info.get('to') or ''
                    currency = salary_info.get('currency') or ''
                    salary = f"{salary_from} - {salary_to} {currency}".strip()
                    if salary.startswith('-'):
                        salary = salary[2:]
                else:
                    salary = "не указана"

                vacancy = {
                    "title": item.get("name"),
                    "company": item.get("employer", {}).get("name"),
                    "city": item.get("area", {}).get("name"),
                    "salary": salary,
                    "date": item.get("published_at", "")[:10],
                    "link": item.get("alternate_url"),
                    "status": "NEW"
                }
                vacancies.append(vacancy)

            if data.get("pages") and params["page"] < data["pages"] - 1:
                params["page"] += 1
            else:
                break
        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            break

    return vacancies

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_json(DATA_FILE)
            return df.to_dict('records')
        except Exception:
            return []
    return []

def save_data(data):
    df = pd.DataFrame(data)
    df.to_json(DATA_FILE, orient='records', indent=2, force_ascii=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/vacancies')
def get_vacancies():
    data = load_data()
    return jsonify(data)

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify(load_settings())

@app.route('/api/settings', methods=['POST'])
def set_settings():
    try:
        data = request.json
        query = data.get('query', '').strip()
        exclude = data.get('exclude', '').strip()
        days = int(data.get('days', 1))
        if days < 1:
            days = 1
        if days > 30:
            days = 30
        if not query:
            return jsonify({'success': False, 'error': 'Ключевое слово не может быть пустым'}), 400

        settings = {'query': query, 'exclude': exclude, 'days': days}
        save_settings(settings)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/update')
def update_vacancies():
    try:
        old_data = load_data()
        old_links = {v['link'] for v in old_data}

        for vacancy in old_data:
            vacancy['status'] = 'OLD'

        new_vacancies = get_vacancies_from_api()
        truly_new = [v for v in new_vacancies if v['link'] not in old_links]
        all_data = old_data + truly_new

        # Сначала сортируем по дате: новые — выше
        all_data.sort(key=lambda x: x['date'] or '0000-00-00', reverse=True)
        # Затем поднимаем NEW наверх, сохраняя порядок дат внутри групп
        all_data.sort(key=lambda x: 0 if x['status'] == 'NEW' else 1)
        save_data(all_data)

        return jsonify({
            'success': True,
            'new_count': len(truly_new),
            'total_count': len(all_data),
            'data': all_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/exit', methods=['POST'])
def exit_app():
    # Завершаем процесс
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({'success': True})

def open_browser():
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    Timer(1.5, open_browser).start()
    try:
        app.run(debug=False, port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("\nПриложение завершено.")
        sys.exit(0)