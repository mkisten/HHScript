from flask import Flask, render_template, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import webbrowser
from threading import Timer

app = Flask(__name__)

API_URL = "https://api.hh.ru/vacancies"
DATA_FILE = "vacancies_data.json"


def get_vacancies_from_api():
    """Получение вакансий с API HH.ru"""
    date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

    params = {
        "text": "Java разработчик NOT Android NOT QA NOT Тестировщик NOT Аналитик NOT C# NOT архитектор NOT PHP NOT Fullstack NOT 1С NOT Python NOT Frontend-разработчик",
        "area": [113, 16],
        "schedule": "remote",
        "per_page": 50,
        "page": 0,
        "date_from": date_from,
        "professional_role": 96
    }

    vacancies = []

    while True:
        try:
            resp = requests.get(API_URL, params=params, timeout=10)
            data = resp.json()

            for item in data.get("items", []):
                vacancy = {
                    "title": item.get("name"),
                    "company": item.get("employer", {}).get("name"),
                    "city": item.get("area", {}).get("name"),
                    "salary": (
                        f"{item['salary']['from']} - {item['salary']['to']} {item['salary']['currency']}"
                        if item.get("salary") else "не указана"
                    ),
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
    """Загрузка данных из файла"""
    if os.path.exists(DATA_FILE):
        df = pd.read_json(DATA_FILE)
        return df.to_dict('records')
    return []


def save_data(data):
    """Сохранение данных в файл"""
    df = pd.DataFrame(data)
    df.to_json(DATA_FILE, orient='records', indent=2)


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/vacancies')
def get_vacancies():
    """Получение списка вакансий"""
    data = load_data()
    return jsonify(data)


@app.route('/api/update')
def update_vacancies():
    """Обновление вакансий"""
    try:
        # Загружаем старые данные
        old_data = load_data()
        old_links = {v['link'] for v in old_data}

        # Помечаем все старые как OLD
        for vacancy in old_data:
            vacancy['status'] = 'OLD'

        # Получаем новые вакансии
        new_vacancies = get_vacancies_from_api()

        # Фильтруем только новые
        truly_new = [v for v in new_vacancies if v['link'] not in old_links]

        # Объединяем
        all_data = old_data + truly_new

        # Сортируем: NEW сверху, потом по дате
        all_data.sort(key=lambda x: (0 if x['status'] == 'NEW' else 1, x['date']), reverse=True)

        # Сохраняем
        save_data(all_data)

        return jsonify({
            'success': True,
            'new_count': len(truly_new),
            'total_count': len(all_data),
            'data': all_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def open_browser():
    """Открытие браузера"""
    webbrowser.open('http://127.0.0.1:5000')


if __name__ == '__main__':
    # Открываем браузер через 1.5 секунды после запуска
    Timer(1.5, open_browser).start()

    # Запускаем Flask
    app.run(debug=False, port=5000)
