# desktop_app.py
import customtkinter as ctk
from tkinter import ttk, messagebox, BooleanVar
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import webbrowser
import threading

# Настройки
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

DATA_FILE = "vacancies_data.json"
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1
}

class VacancyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Java Backend Вакансии — HH.ru")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 700)

        self.vacancies = []
        self.check_vars = []  # для чекбоксов

        self.load_settings()
        self.create_widgets()
        self.load_vacancies_from_file()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            except:
                self.settings = DEFAULT_SETTINGS.copy()
        else:
            self.settings = DEFAULT_SETTINGS.copy()

    def save_settings(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def build_search_text(self):
        exclude_list = [w.strip() for w in self.settings['exclude'].split(',') if w.strip()]
        exclude_str = " NOT ".join(exclude_list)
        return f"{self.settings['query']} NOT {exclude_str}" if exclude_str else self.settings['query']

    def get_vacancies_from_api(self):
        date_from = (datetime.now() - timedelta(days=int(self.settings['days']))).strftime("%Y-%m-%dT%H:%M:%S")
        search_text = self.build_search_text()

        params = {
            "text": search_text,
            "area": [113, 16],
            "schedule": "remote",
            "per_page": 50,
            "page": 0,
            "date_from": date_from,
            "professional_role": 96
        }

        vacancies = []
        API_URL = "https://api.hh.ru/vacancies"

        while True:
            try:
                resp = requests.get(API_URL, params=params, timeout=10)
                if resp.status_code != 200:
                    break
                data = resp.json()

                for item in data.get("items", []):
                    salary_info = item.get("salary")
                    if salary_info:
                        s_from = salary_info.get('from') or ''
                        s_to = salary_info.get('to') or ''
                        curr = salary_info.get('currency') or ''
                        salary_parts = []
                        if s_from: salary_parts.append(str(s_from))
                        if s_to: salary_parts.append(str(s_to))
                        salary = " - ".join(salary_parts)
                        if curr: salary += f" {curr}"
                        if not salary: salary = "не указана"
                    else:
                        salary = "не указана"

                    raw_date = item.get("published_at")
                    date_str = raw_date[:10] if isinstance(raw_date, str) and len(raw_date) >= 10 else ''

                    vacancies.append({
                        "title": item.get("name", "-"),
                        "company": item.get("employer", {}).get("name", "-"),
                        "city": item.get("area", {}).get("name", "-"),
                        "salary": salary,
                        "date": date_str,
                        "link": item.get("alternate_url", "#"),
                        "status": "NEW"
                    })

                if data.get("pages") and params["page"] < data["pages"] - 1:
                    params["page"] += 1
                else:
                    break
            except Exception as e:
                print(f"Ошибка API: {e}")
                break
        return vacancies

    def load_vacancies_from_file(self):
        if os.path.exists(DATA_FILE):
            try:
                df = pd.read_json(DATA_FILE, encoding='utf-8')
                self.vacancies = df.to_dict('records')
            except:
                self.vacancies = []
        else:
            self.vacancies = []
        self.update_table()

    def save_vacancies_to_file(self):
        df = pd.DataFrame(self.vacancies)
        df.to_json(DATA_FILE, orient='records', indent=2, force_ascii=False)

    def create_widgets(self):
        # Верхняя панель
        top_frame = ctk.CTkFrame(self.root)
        top_frame.pack(fill="x", padx=10, pady=10)

        # Статистика
        stats_frame = ctk.CTkFrame(top_frame)
        stats_frame.pack(side="left", padx=5)

        self.total_label = ctk.CTkLabel(stats_frame, text="Всего: 0", font=("Arial", 14, "bold"))
        self.total_label.pack(side="left", padx=10)
        self.new_label = ctk.CTkLabel(stats_frame, text="Новых: 0", font=("Arial", 14, "bold"))
        self.new_label.pack(side="left", padx=10)

        # Кнопки
        btn_frame = ctk.CTkFrame(top_frame)
        btn_frame.pack(side="right", padx=5)

        ctk.CTkButton(btn_frame, text="Загрузить", command=self.load_vacancies).pack(side="left", padx=5)
        self.update_btn = ctk.CTkButton(btn_frame, text="Обновить", command=self.update_vacancies, state="disabled")
        self.update_btn.pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Выход", command=self.root.quit).pack(side="left", padx=5)

        # Настройки
        settings_frame = ctk.CTkFrame(self.root)
        settings_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(settings_frame, text="Ключевое слово:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.query_entry = ctk.CTkEntry(settings_frame, width=250)
        self.query_entry.grid(row=0, column=1, padx=5, pady=5)
        self.query_entry.insert(0, self.settings['query'])

        ctk.CTkLabel(settings_frame, text="Исключить (через запятую):").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.exclude_entry = ctk.CTkEntry(settings_frame, width=250)
        self.exclude_entry.grid(row=0, column=3, padx=5, pady=5)
        self.exclude_entry.insert(0, self.settings['exclude'])

        ctk.CTkLabel(settings_frame, text="Период (дней):").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.days_entry = ctk.CTkEntry(settings_frame, width=60)
        self.days_entry.grid(row=0, column=5, padx=5, pady=5)
        self.days_entry.insert(0, str(self.settings['days']))

        ctk.CTkButton(settings_frame, text="Сохранить настройки", command=self.save_app_settings).grid(row=0, column=6, padx=10, pady=5)

        # Кнопки управления (появятся позже)
        self.action_frame = ctk.CTkFrame(self.root)
        self.action_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.action_frame.pack_forget()  # скрыто по умолчанию

        self.select_all_btn = ctk.CTkButton(self.action_frame, text="Выбрать все новые", command=self.select_all_new)
        self.select_all_btn.pack(side="left", padx=5)
        self.mark_btn = ctk.CTkButton(self.action_frame, text="Пометить выбранные как просмотренные", command=self.mark_selected_as_old)
        self.mark_btn.pack(side="left", padx=5)

        # Таблица
        table_frame = ctk.CTkFrame(self.root)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side="right", fill="y")

        # Treeview
        self.tree = ttk.Treeview(
            table_frame,
            columns=("Status", "Title", "Company", "City", "Salary", "Date", "Link"),
            show="headings",
            yscrollcommand=tree_scroll.set
        )
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("Status", text="Статус")
        self.tree.heading("Title", text="Название")
        self.tree.heading("Company", text="Компания")
        self.tree.heading("City", text="Город")
        self.tree.heading("Salary", text="Зарплата")
        self.tree.heading("Date", text="Дата")
        self.tree.heading("Link", text="Ссылка")

        self.tree.column("Status", width=100, anchor="center")
        self.tree.column("Title", width=300)
        self.tree.column("Company", width=200)
        self.tree.column("City", width=100)
        self.tree.column("Salary", width=150)
        self.tree.column("Date", width=100, anchor="center")
        self.tree.column("Link", width=200)

        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.on_link_click)

    def save_app_settings(self):
        query = self.query_entry.get().strip()
        exclude = self.exclude_entry.get().strip()
        try:
            days = int(self.days_entry.get())
            if days < 1: days = 1
            if days > 30: days = 30
        except:
            days = 1

        if not query:
            messagebox.showerror("Ошибка", "Укажите ключевое слово")
            return

        self.settings = {"query": query, "exclude": exclude, "days": days}
        self.save_settings()
        messagebox.showinfo("Успех", "Настройки сохранены!")

    def update_table(self):
        # Обновить статистику
        new_count = sum(1 for v in self.vacancies if v['status'] == 'NEW')
        self.total_label.configure(text=f"Всего: {len(self.vacancies)}")
        self.new_label.configure(text=f"Новых: {new_count}")

        # Показать/скрыть кнопки
        if new_count > 0:
            self.action_frame.pack()
        else:
            self.action_frame.pack_forget()

        # Очистить таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Сортировка: сначала NEW, потом по дате (новые выше)
        def sort_key(v):
            priority = 0 if v['status'] == 'NEW' else 1
            date_val = v['date'] or '0000-00-00'
            return (priority, date_val)

        sorted_vacancies = sorted(self.vacancies, key=sort_key, reverse=False)
        # Но дата должна быть в обратном порядке → инвертируем дату
        sorted_vacancies.sort(key=lambda x: x['date'] or '0000-00-00', reverse=True)
        sorted_vacancies.sort(key=lambda x: 0 if x['status'] == 'NEW' else 1)

        self.check_vars = []
        for v in sorted_vacancies:
            status_text = "Новая" if v['status'] == 'NEW' else "Просмотрена"
            self.tree.insert("", "end", values=(
                status_text,
                v['title'],
                v['company'],
                v['city'],
                v['salary'],
                v['date'],
                v['link']
            ))

    def on_link_click(self, event):
        item = self.tree.focus()
        if item:
            values = self.tree.item(item, "values")
            link = values[6]
            if link and link != "#":
                webbrowser.open(link)

    def load_vacancies(self):
        if not self.vacancies:
            self.update_vacancies()
        else:
            self.update_table()
            self.update_btn.configure(state="normal")

    def update_vacancies(self):
        def _update():
            try:
                old_links = {v['link'] for v in self.vacancies}
                new_vac = self.get_vacancies_from_api()
                truly_new = [v for v in new_vac if v['link'] not in old_links]
                self.vacancies.extend(truly_new)
                self.save_vacancies_to_file()
                self.root.after(0, self.update_table)
                self.root.after(0, lambda: self.update_btn.configure(state="normal"))
                self.root.after(0, lambda: messagebox.showinfo("Успех", f"Найдено {len(truly_new)} новых вакансий"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))

        threading.Thread(target=_update, daemon=True).start()

    def select_all_new(self):
        # CustomTkinter не поддерживает чекбоксы в Treeview напрямую,
        # поэтому реализуем через выделение строк
        items = self.tree.get_children()
        to_select = []
        for item in items:
            values = self.tree.item(item, "values")
            if values[0] == "Новая":
                to_select.append(item)
        if to_select:
            self.tree.selection_set(to_select)

    def mark_selected_as_old(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите вакансии для пометки")
            return

        updated = 0
        for item in selected:
            values = self.tree.item(item, "values")
            if values[0] == "Новая":
                # Найти вакансию по ссылке и обновить статус
                link = values[6]
                for v in self.vacancies:
                    if v['link'] == link:
                        v['status'] = 'OLD'
                        updated += 1
                        break

        if updated > 0:
            self.save_vacancies_to_file()
            self.update_table()
            messagebox.showinfo("Успех", f"Помечено {updated} вакансий как просмотренные")

# Запуск
if __name__ == "__main__":
    root = ctk.CTk()
    app = VacancyApp(root)
    root.mainloop()