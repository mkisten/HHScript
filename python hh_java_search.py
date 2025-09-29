import requests
import pandas as pd
from datetime import datetime, timedelta
import os
from openpyxl import load_workbook

API_URL = "https://api.hh.ru/vacancies"

# Дата: день назад
date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

params = {
    "text": "Java разработчик NOT Android NOT QA NOT Тестировщик NOT Аналитик NOT C# NOT архитектор NOT PHP NOT Fullstack NOT 1С NOT Python NOT Frontend-разработчик",
    "area": [113, 16],  # Россия и Беларусь
    "schedule": "remote",  # удаленная работа
    "per_page": 50,
    "page": 0,
    "date_from": date_from,
    "professional_role": 96  # Java developer
}

file_name = "java_backend_vacancies_last_week.xlsx"

print("=" * 60)
print("Начало работы скрипта")
print("=" * 60)

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

print("\n" + "=" * 60)
print("Поиск вакансий для Java Developer (Россия и Беларусь)...")
print("=" * 60 + "\n")

# Собираем текущие вакансии
current_vacancies = []

while True:
    resp = requests.get(API_URL, params=params)
    data = resp.json()

    print(f"Обработка страницы {params['page'] + 1}...")

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

print(f"\n{'=' * 60}")
print(f"Найдено {len(current_vacancies)} новых вакансий")
print("=" * 60 + "\n")

# Объединяем старые (OLD) и новые (NEW) данные
if not old_df.empty:
    new_df = pd.concat([old_df, pd.DataFrame(current_vacancies)], ignore_index=True)
else:
    new_df = pd.DataFrame(current_vacancies)

# Сортировка: сначала NEW сверху, затем по дате (новые даты сверху)
# Создаём временную колонку для сортировки статуса (NEW = 0, OLD = 1)
new_df['_sort_status'] = new_df['Статус'].apply(lambda x: 0 if x == 'NEW' else 1)

# Сортируем: сначала по статусу (NEW сверху), потом по дате (новые сверху)
new_df = new_df.sort_values(
    by=['_sort_status', 'Дата публикации'],
    ascending=[True, False]
).drop(columns=['_sort_status']).reset_index(drop=True)

# Сохраняем обновлённый отчёт
if os.path.exists(file_name):
    try:
        os.remove(file_name)
    except PermissionError:
        print(f"\nОШИБКА: Закройте файл {file_name} в Excel и запустите скрипт снова")
        exit(1)

new_df.to_excel(file_name, index=False)

print("Подстройка ширины колонок...")

# Автоматическая подстройка ширины колонок
wb = load_workbook(file_name)
ws = wb.active

for column in ws.columns:
    max_length = 0
    column_letter = column[0].column_letter

    for cell in column:
        try:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        except:
            pass

    adjusted_width = min(max_length + 2, 100)  # +2 для отступов, максимум 100
    ws.column_dimensions[column_letter].width = adjusted_width

wb.save(file_name)

print("\n" + "=" * 60)
print(f"Отчёт обновлён: всего {len(new_df)} вакансий ({len(old_df)} OLD + {len(current_vacancies)} NEW)")
print("=" * 60)