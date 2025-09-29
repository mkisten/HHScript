import requests
import pandas as pd
from datetime import datetime, timedelta
import os

API_URL = "https://api.hh.ru/vacancies"

# Дата: день назад
date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

params = {
    "text": "Java разработчик NOT Android NOT QA NOT Тестировщик NOT Аналитик NOT C# NOT архитектор NOT PHP NOT Fullstack NOT 1С NOT Python NOT Frontend-разработчик",
    "area": 113,  # Россия
    "schedule": "remote",  # удаленная работа
    "per_page": 50,
    "page": 0,
    "date_from": date_from,
    "professional_role": 96  # Java developer
}

file_name = "java_backend_vacancies_last_week.xlsx"

# Загружаем предыдущие данные (если файл есть)
if os.path.exists(file_name):
    old_df = pd.read_excel(file_name)
    old_links = set(old_df["Ссылка"].tolist())
    print(f"Найден предыдущий отчёт: {len(old_links)} вакансий")
else:
    old_links = set()
    print("Предыдущий отчёт не найден — создаём новый")

print("Поиск новых вакансий для Java Developer...")

# Собираем только новые вакансии
new_vacancies = []

while True:
    resp = requests.get(API_URL, params=params)
    data = resp.json()

    for item in data.get("items", []):
        link = item.get("alternate_url")

        # Сохраняем только если вакансии не было в старом списке
        if link not in old_links:
            vacancy = {
                "Название": item.get("name"),
                "Компания": item.get("employer", {}).get("name"),
                "Город": item.get("area", {}).get("name"),
                "Зарплата": (
                    f"{item['salary']['from']} - {item['salary']['to']} {item['salary']['currency']}"
                    if item.get("salary") else "не указана"
                ),
                "Дата публикации": item.get("published_at", "")[:10],
                "Ссылка": link
            }
            new_vacancies.append(vacancy)

    if data.get("pages") and params["page"] < data["pages"] - 1:
        params["page"] += 1
    else:
        break

print(f"\nНайдено {len(new_vacancies)} новых вакансий")

# Сохраняем ТОЛЬКО новые вакансии (заменяя старый файл)
if new_vacancies:
    new_df = pd.DataFrame(new_vacancies)
    new_df.to_excel(file_name, index=False)
    print(f"Отчёт обновлён: сохранено {len(new_df)} новых вакансий")
else:
    print("Новых вакансий не найдено, файл не обновлён")