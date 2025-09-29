import requests
import pandas as pd
from datetime import datetime, timedelta

API_URL = "https://api.hh.ru/vacancies"

# Дата: неделя назад
date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

params = {
    "text": "Java разработчик NOT Android NOT QA NOT Тестировщик NOT Аналитик NOT C# NOT архитектор NOT PHP NOT Fullstack NOT 1С NOT Python NOT Frontend-разработчик",
    "area": 113,                  # Россия
    "schedule": "remote",         # удаленная работа
    "per_page": 50,
    "page": 0,
    "date_from": date_from,
    "professional_role": 96       # Java developer (ключевой фильтр)
}

vacancies = []

print("Поиск вакансий только для Java Developer...")

while True:
    resp = requests.get(API_URL, params=params)
    data = resp.json()

    for item in data.get("items", []):
        vacancy = {
            "Название": item.get("name"),
            "Компания": item.get("employer", {}).get("name"),
            "Город": item.get("area", {}).get("name"),
            "Зарплата": (
                f"{item['salary']['from']} - {item['salary']['to']} {item['salary']['currency']}"
                if item.get("salary") else "не указана"
            ),
            "Дата публикации": item.get("published_at", "")[:10],
            "Ссылка": item.get("alternate_url")
        }
        vacancies.append(vacancy)

    if data.get("pages") and params["page"] < data["pages"] - 1:
        params["page"] += 1
    else:
        break

print(f"Найдено {len(vacancies)} релевантных вакансий за последнюю неделю")

df = pd.DataFrame(vacancies)
df.to_excel("java_backend_vacancies_last_week.xlsx", index=False)

print("Сохранено в файл java_backend_vacancies_last_week.xlsx")
