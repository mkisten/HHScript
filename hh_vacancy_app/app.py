import sys
import os
import json
import webbrowser
import threading
import logging
from datetime import datetime, timedelta

import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QDesktopServices, QColor, QPalette

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = "vacancies_data.json"
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1,
    "theme": "light"
}


# Worker для фонового обновления
class UpdateWorker(QThread):
    finished = Signal(list)  # Сигнал с новыми вакансиями
    error = Signal(str)  # Сигнал с ошибкой

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def run(self):
        try:
            logger.info("Фоновый поток: начало получения вакансий")

            # Загружаем текущие вакансии из файла
            current_vacancies = []
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        current_vacancies = json.load(f)
                    logger.debug(f"Загружено {len(current_vacancies)} вакансий из файла")
                except Exception as e:
                    logger.error(f"Ошибка загрузки из файла: {e}")

            old_links = {v['link'] for v in current_vacancies}

            # Получаем новые вакансии с API
            new_vacancies = self.get_vacancies_from_api()
            truly_new = [v for v in new_vacancies if v['link'] not in old_links]

            logger.info(f"Найдено {len(truly_new)} новых вакансий")

            # Сохраняем обновленный список
            if truly_new:
                all_vacancies = current_vacancies + truly_new
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_vacancies, f, ensure_ascii=False, indent=2)
                logger.info("Вакансии сохранены в файл")

            # Отправляем сигнал с результатом
            self.finished.emit(truly_new)

        except Exception as e:
            logger.exception("Ошибка в фоновом потоке")
            self.error.emit(str(e))

    def get_vacancies_from_api(self):
        date_from = (datetime.now() - timedelta(days=int(self.settings['days']))).strftime("%Y-%m-%dT%H:%M:%S")

        # Формируем поисковый запрос
        exclude_list = [w.strip() for w in self.settings['exclude'].split(',') if w.strip()]
        exclude_str = " NOT ".join(exclude_list)
        search_text = f"{self.settings['query']} NOT {exclude_str}" if exclude_str else self.settings['query']

        logger.debug(f"Поисковый запрос: {search_text}")

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
        max_pages = 5

        while params["page"] < max_pages:
            try:
                logger.debug(f"Запрос страницы {params['page'] + 1}")
                resp = requests.get(API_URL, params=params, timeout=10)

                if resp.status_code != 200:
                    logger.warning(f"API вернул статус {resp.status_code}")
                    break

                data = resp.json()
                items = data.get("items", [])
                logger.debug(f"Получено {len(items)} вакансий на странице {params['page'] + 1}")

                for item in items:
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

                if params["page"] >= data.get("pages", 1) - 1:
                    break
                params["page"] += 1

            except Exception as e:
                logger.error(f"Ошибка при получении данных: {e}")
                break

        logger.info(f"Получено {len(vacancies)} вакансий с API")
        return vacancies


class VacancyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Java Backend Вакансии — HH.ru")
        self.resize(1400, 900)
        self.vacancies = []
        self.worker = None
        logger.info("Запуск приложения")
        self.load_settings()
        self.apply_theme()
        self.init_ui()
        self.load_vacancies_from_file()
        self.update_table()

    def load_settings(self):
        logger.info("Загрузка настроек")
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                logger.info("Настройки загружены из файла")
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                self.settings = DEFAULT_SETTINGS.copy()
        else:
            self.settings = DEFAULT_SETTINGS.copy()
            logger.info("Используются настройки по умолчанию")

    def save_settings(self):
        logger.info("Сохранение настроек")
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            logger.info("Настройки сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")

    def apply_theme(self):
        app = QApplication.instance()
        if self.settings.get("theme") == "dark":
            app.setStyle("Fusion")
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            app.setPalette(palette)
        else:
            app.setStyle("Fusion")
            app.setPalette(app.style().standardPalette())

    def toggle_theme(self):
        current = self.settings.get("theme", "light")
        self.settings["theme"] = "dark" if current == "light" else "light"
        self.save_settings()
        self.apply_theme()
        self.theme_btn.setText(f"Тема: {self.settings['theme'].capitalize()}")
        self.update_table()

    def init_ui(self):
        logger.info("Инициализация UI")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Верхняя панель
        top_layout = QHBoxLayout()
        self.total_label = QLabel("Всего: 0")
        self.new_label = QLabel("Новых: 0")
        top_layout.addWidget(self.total_label)
        top_layout.addWidget(self.new_label)
        top_layout.addStretch()

        self.update_btn = QPushButton("Обновить")
        self.exit_btn = QPushButton("Выход")
        self.theme_btn = QPushButton(f"Тема: {self.settings.get('theme', 'light').capitalize()}")

        self.update_btn.clicked.connect(self.update_vacancies)
        self.exit_btn.clicked.connect(self.close)
        self.theme_btn.clicked.connect(self.toggle_theme)

        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.theme_btn)
        top_layout.addWidget(self.exit_btn)
        main_layout.addLayout(top_layout)

        # Настройки
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Ключевое слово:"))
        self.query_input = QLineEdit()
        self.query_input.setText(self.settings.get("query", ""))
        settings_layout.addWidget(self.query_input)

        settings_layout.addWidget(QLabel("Исключить (через запятую):"))
        self.exclude_input = QLineEdit()
        self.exclude_input.setText(self.settings.get("exclude", ""))
        settings_layout.addWidget(self.exclude_input)

        settings_layout.addWidget(QLabel("Период (дней):"))
        self.days_input = QSpinBox()
        self.days_input.setRange(1, 30)
        self.days_input.setValue(self.settings.get("days", 1))
        settings_layout.addWidget(self.days_input)

        self.save_settings_btn = QPushButton("Сохранить настройки")
        self.save_settings_btn.clicked.connect(self.save_app_settings)
        settings_layout.addWidget(self.save_settings_btn)
        main_layout.addLayout(settings_layout)

        # Кнопки управления
        self.action_widget = QWidget()
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.select_all_btn = QPushButton("Выбрать все новые")
        self.mark_btn = QPushButton("Пометить выбранные как просмотренные")
        self.select_all_btn.clicked.connect(self.select_all_new)
        self.mark_btn.clicked.connect(self.mark_selected_as_old)
        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.mark_btn)
        action_layout.addStretch()
        self.action_widget.hide()
        main_layout.addWidget(self.action_widget)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["", "Статус", "Название", "Компания", "Город", "Зарплата", "Дата", "Действие"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellClicked.connect(self.on_cell_click)
        main_layout.addWidget(self.table)

    def save_app_settings(self):
        query = self.query_input.text().strip()
        exclude = self.exclude_input.text().strip()
        days = self.days_input.value()
        if not query:
            QMessageBox.warning(self, "Ошибка", "Укажите ключевое слово")
            return
        self.settings.update({"query": query, "exclude": exclude, "days": days})
        self.save_settings()
        QMessageBox.information(self, "Успех", "Настройки сохранены!")

    def update_table(self):
        logger.info("Обновление таблицы")
        new_count = sum(1 for v in self.vacancies if v.get('status') == 'NEW')
        self.total_label.setText(f"Всего: {len(self.vacancies)}")
        self.new_label.setText(f"Новых: {new_count}")

        if new_count > 0:
            self.action_widget.show()
        else:
            self.action_widget.hide()

        # Сортировка
        sorted_vacancies = sorted(self.vacancies, key=lambda x: x.get('date', '') or '0000-00-00', reverse=True)
        sorted_vacancies.sort(key=lambda x: 0 if x.get('status') == 'NEW' else 1)

        self.table.setRowCount(len(sorted_vacancies))
        for row, v in enumerate(sorted_vacancies):
            # Чекбокс
            if v.get('status') == 'NEW':
                checkbox = QCheckBox()
                self.table.setCellWidget(row, 0, checkbox)
            else:
                self.table.setItem(row, 0, QTableWidgetItem(""))

            # Статус
            status_text = "Новая" if v.get('status') == 'NEW' else "Просмотрена"
            status_item = QTableWidgetItem(status_text)
            if v.get('status') == 'NEW':
                status_item.setBackground(QColor("#d1fae5" if self.settings.get("theme") == "light" else "#1e5f3e"))
            else:
                status_item.setBackground(QColor("#fee2e2" if self.settings.get("theme") == "light" else "#5f1e1e"))
            self.table.setItem(row, 1, status_item)

            self.table.setItem(row, 2, QTableWidgetItem(v.get('title', '-')))
            self.table.setItem(row, 3, QTableWidgetItem(v.get('company', '-')))
            self.table.setItem(row, 4, QTableWidgetItem(v.get('city', '-')))
            self.table.setItem(row, 5, QTableWidgetItem(v.get('salary', '-')))
            self.table.setItem(row, 6, QTableWidgetItem(v.get('date', '-')))

            # Кнопка "Открыть"
            open_item = QTableWidgetItem("Открыть")
            open_item.setData(Qt.UserRole, v.get('link', ''))
            open_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 7, open_item)

        logger.info("Таблица обновлена")

    def on_cell_click(self, row, column):
        if column == 7:
            item = self.table.item(row, column)
            if item:
                link = item.data(Qt.UserRole)
                if link and link != "#":
                    logger.info(f"Открытие ссылки: {link}")
                    QDesktopServices.openUrl(link)

    def load_vacancies_from_file(self):
        logger.info("Загрузка вакансий из файла")
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.vacancies = json.load(f)
                logger.info(f"Загружено {len(self.vacancies)} вакансий из файла")
            except Exception as e:
                logger.error(f"Ошибка загрузки вакансий: {e}")
                self.vacancies = []
        else:
            self.vacancies = []
            logger.info("Файл данных не найден")

    def save_vacancies_to_file(self):
        logger.info("Сохранение вакансий в файл")
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.vacancies, f, ensure_ascii=False, indent=2)
            logger.info("Вакансии сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения вакансий: {e}")

    def update_vacancies(self):
        logger.info("Нажата кнопка 'Обновить'")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Обновление...")

        # Создаем worker
        self.worker = UpdateWorker(self.settings.copy())
        self.worker.finished.connect(self.on_update_finished)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_update_finished(self, truly_new):
        logger.info(f"Обновление завершено: {len(truly_new)} новых вакансий")

        # Добавляем новые вакансии
        self.vacancies.extend(truly_new)

        # Обновляем таблицу
        self.update_table()

        # Восстанавливаем кнопку
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Обновить")

        # Показываем сообщение
        if truly_new:
            QMessageBox.information(self, "Успех", f"Найдено {len(truly_new)} новых вакансий")
        else:
            QMessageBox.information(self, "Информация", "Нет новых вакансий")

    def on_update_error(self, error_msg):
        logger.error(f"Ошибка обновления: {error_msg}")
        QMessageBox.critical(self, "Ошибка", f"Ошибка при обновлении:\n{error_msg}")
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Обновить")

    def select_all_new(self):
        logger.info("Выбор всех новых вакансий")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == "Новая":
                checkbox = self.table.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(True)

    def mark_selected_as_old(self):
        logger.info("Пометка выбранных как просмотренные")
        updated = 0
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                link_item = self.table.item(row, 7)
                link = link_item.data(Qt.UserRole) if link_item else ""
                if link:
                    for v in self.vacancies:
                        if v.get('link') == link:
                            v['status'] = 'OLD'
                            updated += 1
                            break

        if updated > 0:
            self.save_vacancies_to_file()
            self.update_table()
            QMessageBox.information(self, "Успех", f"Помечено {updated} вакансий как просмотренные")
        else:
            QMessageBox.warning(self, "Внимание", "Не выбрано ни одной вакансии")


if __name__ == "__main__":
    logger.info("Запуск основного цикла приложения")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VacancyApp()
    window.show()
    sys.exit(app.exec())