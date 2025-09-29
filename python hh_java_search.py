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
    # Все предыдущие вакансии помечаем как OLD
    old_df["Статус"] = "OLD"
    old_links = set(old_df["Ссылка"].tolist())
    print(f"Найден предыдущий отчёт: {len(old_links)} вакансий помечено как OLD")
else:
    old_df = pd.DataFrame()
    old_links = set()
    print("Предыдущий отчёт не найден — создаём новый")

print("Поиск вакансий для Java Developer...")

# Собираем текущие вакансии
current_vacancies = []

while True:
    resp = requests.get(API_URL, params=params)
    data = resp.json()

    for item in data.get("items", []):
        link = item.get("alternate_url")

        # Определяем статус: NEW если вакансии не было, иначе пропускаем (она уже есть как OLD)
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
                "Ссылка": link,
                "Статус": "NEW"
            }
            current_vacancies.append(vacancy)

    if data.get("pages") and params["page"] < data["pages"] - 1:
        params["page"] += 1
    else:
        break

print(f"Найдено {len(current_vacancies)} новых вакансий")

# Объединяем старые (OLD) и новые (NEW) данные
if not old_df.empty:
    new_df = pd.concat([old_df, pd.DataFrame(current_vacancies)], ignore_index=True)
else:
    new_df = pd.DataFrame(current_vacancies)

# Сохраняем обновлённый отчёт
if os.path.exists(file_name):
    try:
        os.remove(file_name)
    except PermissionError:
        print(f"\nОШИБКА: Закройте файл {file_name} в Excel и запустите скрипт снова")
        exit(1)

new_df.to_excel(file_name, index=False)
print(f"Отчёт обновлён: всего {len(new_df)} вакансий ({len(old_df)} OLD + {len(current_vacancies)} NEW)")