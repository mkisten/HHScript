import sys
import os
from pathlib import Path
import json
import webbrowser
import threading
import logging
from datetime import datetime, timedelta
from collections import defaultdict

import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QAbstractItemView, QCheckBox, QSpinBox,
    QFrame, QGroupBox, QSystemTrayIcon, QMenu, QTabWidget, QComboBox
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer
from PySide6.QtGui import QDesktopServices, QColor, QPalette, QFont, QIcon, QPixmap, QAction, QPainter
from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QValueAxis, QBarCategoryAxis, QCategoryAxis
from tinydb import TinyDB, Query



# Сразу после всех импортов добавьте:
print("=" * 50)
print("СТАРТ ПРОГРАММЫ")
print("=" * 50)

def resource_path(relative_path):
    """Возвращает абсолютный путь до ресурса, работает и в exe, и в dev-режиме"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

print("resource_path определен")


def get_data_dir():

    app_name = "HH_Vacancy"
    data_dir = Path(os.getenv('APPDATA')) / app_name
    data_dir.mkdir(exist_ok=True)  # Создаём папку, если нет
    return data_dir

data_dir = get_data_dir()
LOG_FILE = data_dir / "app.log"  # Для лога
DB_FILE = data_dir / "app.db"
db = TinyDB(DB_FILE, ensure_ascii=False, indent=2, encoding='utf-8')
Vacancy = Query()
Setting = Query()

# Настройка логирования
try:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding='utf-8'),  # Изменено: путь к LOG_FILE
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("ЛОГИРОВАНИЕ ИНИЦИАЛИЗИРОВАНО")
    logger.info("=" * 50)
    print("Логирование настроено успешно")
except Exception as e:
    print(f"ОШИБКА при настройке логирования: {e}")
    import traceback
    traceback.print_exc()
    # Добавьте: logger не используется здесь, так что OK


DEFAULT_SETTINGS = {
    "query": "Java разработчик",
    "exclude": "Android, QA, Тестировщик, Аналитик, C#, архитектор, PHP, Fullstack, 1С, Python, Frontend-разработчик",
    "days": 1,
    "theme": "light",
    "work_types": {
        "remote": True,
        "hybrid": False,
        "office": False
    },
    "countries": {
        "russia": True,
        "belarus": True
    },
    "auto_update": {
        "enabled": False,
        "interval_minutes": 30
    },
    "stats_mode": "Вакансии по часам (за день)",
    "stats_date": None
}

# Worker для фонового обновления
class UpdateWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, settings, old_links):
        super().__init__()
        self.settings = settings
        self.old_links = old_links  # set of existing links

    def run(self):
        try:
            logger.info("Фоновый поток: начало получения вакансий")
            new_vacancies = self.get_vacancies_from_api()
            truly_new = [v for v in new_vacancies if v['link'] not in self.old_links]
            logger.info(f"Найдено {len(truly_new)} новых вакансий")
            self.finished.emit(truly_new)
        except Exception as e:
            logger.exception("Ошибка в фоновом потоке")
            self.error.emit(str(e))

    def get_vacancies_from_api(self):
        date_from = (datetime.now() - timedelta(days=int(self.settings['days']))).strftime("%Y-%m-%dT%H:%M:%S")
        exclude_list = [w.strip() for w in self.settings['exclude'].split(',') if w.strip()]
        exclude_str = " NOT ".join(exclude_list)
        search_text = f"{self.settings['query']} NOT {exclude_str}" if exclude_str else self.settings['query']
        logger.debug(f"Поисковый запрос: {search_text}")

        # Определяем типы работы
        work_types = self.settings.get('work_types', {})
        schedules = []
        if work_types.get('remote'):
            schedules.append('remote')
        if work_types.get('hybrid'):
            schedules.append('hybrid')
        if work_types.get('office'):
            schedules.append('fullDay')

        # Определяем страны
        countries = self.settings.get('countries', {})
        areas = []
        if countries.get('russia'):
            areas.append(113)  # Россия
        if countries.get('belarus'):
            areas.append(16)  # Беларусь

        # Базовые параметры
        base_params = {
            "text": search_text,
            "per_page": 50,
            "page": 0,
            "date_from": date_from,
            "professional_role": 96
        }

        logger.debug(f"Выбранные типы работы: {schedules}")
        logger.debug(f"Выбранные страны: {areas}")

        vacancies = []
        API_URL = "https://api.hh.ru/vacancies"
        max_pages = 5

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Определяем, нужно ли использовать фильтр по schedule
        use_schedule_filter = True
        # Если выбраны ВСЕ типы работы, не используем фильтр schedule
        if len(schedules) == 3 and 'remote' in schedules and 'hybrid' in schedules and 'fullDay' in schedules:
            logger.info("Выбраны все типы работы. Фильтр 'schedule' будет пропущен.")
            use_schedule_filter = False

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Если фильтр schedule используется, но выбрано несколько значений,
        # нужно выполнить отдельные запросы для каждого значения.
        if use_schedule_filter and len(schedules) > 1:
            logger.info(f"Выбрано несколько типов работы ({schedules}). Выполняем отдельные запросы.")
            all_vacancies_aggregated = []
            for single_schedule in schedules:
                logger.debug(f"Запрашиваем вакансии для типа работы: {single_schedule}")
                # Создаем параметры для текущего типа работы
                current_params = base_params.copy()
                current_params['schedule'] = single_schedule
                if areas:  # Добавляем регионы, если они заданы
                    current_params['area'] = areas  # Передаем список регионов

                # Выполняем поиск для одного типа работы
                schedule_vacancies = self._fetch_vacancies(API_URL, current_params, max_pages)
                all_vacancies_aggregated.extend(schedule_vacancies)
            # Убираем дубликаты вакансий, которые могли быть найдены по разным типам работы
            seen_links = set()
            unique_vacancies = []
            for v in all_vacancies_aggregated:
                if v['link'] not in seen_links:
                    seen_links.add(v['link'])
                    unique_vacancies.append(v)
            vacancies = unique_vacancies

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Если фильтр schedule используется, но выбрано ОДНО значение
        elif use_schedule_filter and len(schedules) == 1:
            logger.info(f"Выбран один тип работы: {schedules[0]}. Выполняем обычный запрос.")
            current_params = base_params.copy()
            current_params['schedule'] = schedules[0]
            if areas:
                current_params['area'] = areas
            vacancies = self._fetch_vacancies(API_URL, current_params, max_pages)

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Если фильтр schedule НЕ используется (выбраны все)
        else:  # not use_schedule_filter
            logger.info("Фильтр 'schedule' пропущен. Выполняем запрос без него.")
            current_params = base_params.copy()
            if areas:
                current_params['area'] = areas
            vacancies = self._fetch_vacancies(API_URL, current_params, max_pages)

        logger.info(f"Получено {len(vacancies)} уникальных вакансий с API (после объединения/фильтрации)")
        return vacancies

    # --- ВСПОМОГАТЕЛЬНЫЙ МЕТОД ---
    def _fetch_vacancies(self, api_url, params, max_pages):
        """Вспомогательный метод для выполнения запросов к API с заданными параметрами."""
        fetched_vacancies = []
        current_params = params.copy()  # Работаем с копией, чтобы не менять оригинальные параметры
        page = current_params.get('page', 0)
        loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Дата и время загрузки для всех вакансий на этой странице
        while page < max_pages:
            try:
                logger.debug(f"Запрос страницы {page + 1} с параметрами: {current_params}")

                resp = requests.get(api_url, params=current_params, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"API вернул статус {resp.status_code} для параметров: {current_params}")
                    if resp.status_code == 400:
                        logger.error("Возможно, неверные параметры запроса. Проверьте логи выше.")
                    break
                data = resp.json()
                items = data.get("items", [])
                logger.debug(f"Получено {len(items)} вакансий на странице {page + 1}")

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

                    # Определяем тип работы
                    schedule = item.get("schedule", {})
                    schedule_name = schedule.get("name", "-") if isinstance(schedule, dict) else str(schedule)

                    fetched_vacancies.append({
                        "title": item.get("name", "-"),
                        "company": item.get("employer", {}).get("name", "-"),
                        "city": item.get("area", {}).get("name", "-"),
                        "salary": salary,
                        "date": date_str,
                        "link": item.get("alternate_url", "#"),
                        "schedule": schedule_name,
                        "status": "NEW",
                        "loaded_at": loaded_at  # Добавляем дату и время загрузки
                    })

                if page >= data.get("pages", 1) - 1:
                    break
                page += 1
                current_params['page'] = page  # Увеличиваем номер страницы в копии параметров
            except Exception as e:
                logger.error(f"Ошибка при получении данных на странице {page} с параметрами {current_params}: {e}")
                break
        return fetched_vacancies


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Поддержать разработчика")
        self.setModal(True)
        self.resize(400, 500)

        layout = QVBoxLayout(self)

        # Заголовок
        title_label = QLabel("<b>Спасибо, что пользуетесь 'Удобные Вакансии'!</b>")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Описание
        desc_label = QLabel("Если приложение оказалось полезным, вы можете поддержать разработчика:")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # QLabel для QR-кода
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)

        # Получаем путь к QR-коду
        qr_path = resource_path("qr-code.png")
        logger.info(f"Попытка загрузить QR-код из: {qr_path}")
        logger.info(f"Файл существует: {os.path.exists(qr_path)}")

        qr_pixmap = QPixmap(qr_path)
        if not qr_pixmap.isNull():
            scaled_pixmap = qr_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_label.setPixmap(scaled_pixmap)
            logger.info("QR-код успешно загружен")
        else:
            error_msg = f"QR-код не найден\nПуть: {qr_path}\nСуществует: {os.path.exists(qr_path)}"
            self.qr_label.setText(error_msg)
            self.qr_label.setStyleSheet("color: red; font-size: 10px;")
            logger.error(f"Не удалось загрузить QR-код из {qr_path}")
        layout.addWidget(self.qr_label)

        # Текст с пояснением и ссылками
        text_label = QLabel("""
        <br>
        Отсканируйте QR-код:<br><br>
        Любая сумма приветствуется!<br><br>
        """)
        text_label.setTextFormat(Qt.RichText)
        text_label.setOpenExternalLinks(True) # Позволяет открывать ссылки
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        # Кнопка Закрыть
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept) # Закрывает диалог
        layout.addWidget(close_button)

    # Опционально: переопределить closeEvent, если нужно что-то сделать при закрытии

class VacancyApp(QMainWindow):

    def parse_loaded_date(self, date_str):
        """Парсит строку даты загрузки в datetime, с fallback на min для сортировки."""
        if not date_str:
            return datetime.min
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Неверный формат loaded_at: {date_str}")
            return datetime.min

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Удобные Вакансии — HH.ru")
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            logger.info(f"Иконка приложения загружена: {icon_path}")
        else:
            logger.warning(f"Иконка приложения {icon_path} не найдена")
        self.resize(1500, 900)
        self.vacancies = []
        self.worker = None
        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.timeout.connect(self.auto_update_check)
        logger.info("Запуск приложения")
        # print(f"DEBUG: DATA_FILE = {DATA_FILE}")
        self.load_settings()
        self.init_ui()  # Сначала создаём UI
        self.apply_theme()
        self.load_vacancies_from_file()
        self.populate_stats_dates()  # Теперь stats_date_combo уже существует
        self.on_stats_mode_changed(self.stats_mode_combo.currentText())
        self.update_table()
        self.update_stats_chart()
        self.setup_auto_update()

        self.tray_icon = None
        self.setup_system_tray()

    def setup_system_tray(self):
        """Настройка системного трея"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("Системный трей не поддерживается на этой платформе")
            QMessageBox.warning(self, "Предупреждение",
                                "Системный трей не поддерживается. Приложение будет закрываться при нажатии на крестик.")
            return

        self.tray_icon = QSystemTrayIcon(self)
        tray_icon_path = resource_path("icon.png")
        if os.path.exists(tray_icon_path):
            self.tray_icon.setIcon(QIcon(tray_icon_path))
            logger.info(f"Иконка трея загружена: {tray_icon_path}")
        else:
            logger.warning(f"Иконка трея {tray_icon_path} не найдена, используется стандартная иконка")
            self.tray_icon.setIcon(self.windowIcon() or QIcon())

        self.tray_icon.setToolTip("Удобные Вакансии")

        tray_menu = QMenu()

        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show_and_restore)
        tray_menu.addAction(show_action)

        update_action = QAction("Обновить вакансии", self)
        update_action.triggered.connect(self.update_vacancies)
        tray_menu.addAction(update_action)

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close_application)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.tray_icon.show()
        if self.tray_icon.isVisible():
            logger.info("Иконка системного трея успешно отображается")
        else:
            logger.error("Иконка системного трея не отображается, проверьте настройки Windows 11")

    def show_and_restore(self):
        """Показать и восстановить окно"""
        self.show()
        self.setWindowState(Qt.WindowNoState)
        self.raise_()
        self.activateWindow()
        logger.info("Окно приложения восстановлено из трея")

    def tray_icon_activated(self, reason):
        """Обработка событий иконки трея"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_restore()
            logger.info("Окно приложения открыто по двойному клику на иконке трея")

    def closeEvent(self, event):
        """Переопределение события закрытия окна"""
        logger.info("closeEvent вызвано")
        if self.tray_icon:
            logger.info(f"isVisible в closeEvent: {self.tray_icon.isVisible()}")
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                "Удобные Вакансии",
                "Приложение свернуто в системный трей. Используйте контекстное меню для выхода.",
                QSystemTrayIcon.Information,
                3000
            )
            logger.info("Окно свернуто в системный трей")
        else:
            logger.info("Системный трей недоступен или не инициализирован, приложение будет закрыто")
            event.accept()

    def close_application(self):
        """Полное завершение приложения"""
        logger.info("Завершение приложения")
        self.auto_update_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        if self.tray_icon:
            self.tray_icon.hide()
            logger.info("Иконка трея скрыта")
        self.close()
        QApplication.quit()

    def update_stats_chart(self):
        """Обновление графика статистики в зависимости от выбранного режима"""
        # Проверяем, что все необходимые элементы UI созданы
        if not hasattr(self, 'stats_mode_combo') or not hasattr(self, 'stats_date_combo'):
            logger.warning("Комбобоксы статистики ещё не созданы, пропускаем обновление графика")
            return

        # Проверяем наличие вакансий
        if not self.vacancies:
            logger.info("Нет вакансий для отображения на графике")
            if hasattr(self, 'chart_view') and self.chart_view:
                # Очищаем график если он уже существует
                empty_chart = QChart()
                empty_chart.setTitle("Нет данных для отображения")
                empty_chart.setTheme(
                    QChart.ChartThemeDark if self.settings.get("theme") == "dark" else QChart.ChartThemeLight)
                self.chart_view.setChart(empty_chart)
            return

        # Получаем текущий режим и выбранную дату
        mode = self.stats_mode_combo.currentText()
        selected_date = self.stats_date_combo.currentData()

        # Создаем новый график
        chart = QChart()
        chart.setAnimationOptions(QChart.SeriesAnimations)

        # Выбираем тип графика в зависимости от режима
        try:
            if mode == "Вакансии по часам (за день)":
                self._update_hourly_chart(chart, selected_date)
            elif mode == "Вакансии по дням (неделя)":
                self._update_daily_chart(chart, 7)
            elif mode == "Вакансии по дням (месяц)":
                self._update_daily_chart(chart, 30)
            elif mode == "Вакансии по дням (3 месяца)":
                self._update_daily_chart(chart, 90)
            elif mode == "Вакансии по дням (6 месяцев)":
                self._update_daily_chart(chart, 180)
            else:
                logger.warning(f"Неизвестный режим статистики: {mode}")
                return
        except Exception as e:
            logger.error(f"Ошибка при создании графика: {e}")
            return

        # Применяем тему
        chart.setTheme(QChart.ChartThemeDark if self.settings.get("theme") == "dark" else QChart.ChartThemeLight)

        # Создаем или обновляем виджет графика
        if not hasattr(self, 'chart_view') or self.chart_view is None:
            self.chart_view = QChartView(chart)
            self.chart_view.setRenderHint(QPainter.Antialiasing)
            if hasattr(self, 'stats_chart_layout'):
                self.stats_chart_layout.addWidget(self.chart_view)
            else:
                logger.error("stats_chart_layout не найден")
        else:
            self.chart_view.setChart(chart)

        logger.info(f"График статистики обновлен в режиме: {mode}")

    def _update_hourly_chart(self, chart, selected_date):
        """Обновление графика по часам для конкретного дня"""
        hourly_counts = defaultdict(int)

        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    if selected_date and loaded_dt.date() == selected_date:
                        hour = loaded_dt.hour
                        hourly_counts[hour] += 1
                    elif not selected_date:
                        hour = loaded_dt.hour
                        hourly_counts[hour] += 1
                except ValueError:
                    logger.warning(f"Неверный формат loaded_at: {loaded_at_str}")

        date_str = selected_date.strftime("%d.%m.%Y") if selected_date else "все дни"
        chart.setTitle(f"Вакансии по часам ({date_str})")

        bar_set = QBarSet("Количество вакансий")

        # Добавляем значения и включаем отображение меток
        for hour in range(24):
            count = hourly_counts[hour]
            bar_set.append(count)

        # Включаем отображение значений на столбцах
        bar_set.setLabelColor(QColor("#E1E1E1") if self.settings.get("theme") == "dark" else QColor("#212121"))

        series = QBarSeries()
        series.append(bar_set)

        # Включаем отображение меток со значениями
        series.setLabelsVisible(True)
        series.setLabelsPosition(QBarSeries.LabelsOutsideEnd)
        series.setLabelsFormat("@value")

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        categories = [f"{h}ч" for h in range(24)]
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_value = max(hourly_counts.values()) if hourly_counts else 1
        axis_y = QValueAxis()
        # Увеличиваем диапазон, чтобы метки не обрезались
        axis_y.setRange(0, max_value + max(2, int(max_value * 0.15)))
        axis_y.setTitleText("Количество")
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def _update_daily_chart(self, chart, days_count):
        """Обновление графика по дням за указанный период"""
        daily_counts = defaultdict(int)

        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    date_key = loaded_dt.date()
                    daily_counts[date_key] += 1
                except ValueError:
                    logger.warning(f"Неверный формат loaded_at: {loaded_at_str}")

        if not daily_counts:
            chart.setTitle(f"Вакансии по дням (последние {days_count} дней) - нет данных")
            return

        end_date = max(daily_counts.keys())
        start_date = end_date - timedelta(days=days_count - 1)

        chart.setTitle(f"Вакансии по дням (последние {days_count} дней)")

        bar_set = QBarSet("Количество вакансий")
        categories = []

        current_date = start_date
        while current_date <= end_date:
            count = daily_counts.get(current_date, 0)
            bar_set.append(count)
            categories.append(current_date.strftime("%d.%m"))
            current_date += timedelta(days=1)

        # Включаем отображение значений на столбцах
        bar_set.setLabelColor(QColor("#E1E1E1") if self.settings.get("theme") == "dark" else QColor("#212121"))

        series = QBarSeries()
        series.append(bar_set)

        # Включаем отображение меток со значениями
        series.setLabelsVisible(True)
        series.setLabelsPosition(QBarSeries.LabelsOutsideEnd)
        series.setLabelsFormat("@value")

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_value = max(bar_set.at(i) for i in range(bar_set.count())) if bar_set.count() > 0 else 1
        axis_y = QValueAxis()
        # Увеличиваем диапазон, чтобы метки не обрезались
        axis_y.setRange(0, max_value + max(2, int(max_value * 0.15)))
        axis_y.setTitleText("Количество")
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def setup_auto_update(self):
        """Настройка автообновления"""
        auto_update_settings = self.settings.get('auto_update', {})
        enabled = auto_update_settings.get('enabled', False)
        interval = auto_update_settings.get('interval_minutes', 30)

        self.auto_update_timer.stop()

        if enabled:
            interval_ms = interval * 60 * 1000
            self.auto_update_timer.start(interval_ms)
            logger.info(f"Автообновление включено: каждые {interval} минут")
        else:
            logger.info("Автообновление выключено")

    def auto_update_check(self):
        logger.info("Запуск автообновления")
        if self.worker and self.worker.isRunning():
            logger.info("Обновление уже выполняется, пропускаем")
            return
        old_links = {v['link'] for v in self.vacancies}
        self.worker = UpdateWorker(self.settings.copy(), old_links)  # ← передаём old_links
        self.worker.finished.connect(self.on_auto_update_finished)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_auto_update_finished(self, truly_new):
        """Обработка результатов автообновления"""
        logger.info(f"Автообновление завершено: {len(truly_new)} новых вакансий")

        for v in truly_new:
            if 'status' not in v:
                v['status'] = 'NEW'

        self.vacancies.extend(truly_new)
        self.save_vacancies_to_file()
        self.populate_stats_dates()
        self.update_table()
        self.update_stats_chart()

        if truly_new:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Новые вакансии!")
            msg.setText(f"Найдено {len(truly_new)} новых вакансий!")
            msg.setInformativeText("Проверьте таблицу для просмотра деталей.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
            msg.show()
            msg.raise_()
            msg.activateWindow()
            logger.info("Показано уведомление о новых вакансиях")

    def load_settings(self):
        logger.info("Загрузка настроек из TinyDB")
        settings_table = db.table('settings')
        records = settings_table.all()
        if records:
            self.settings = records[0]
            # Убедимся, что все ключи из DEFAULT_SETTINGS присутствуют
            for key, default_val in DEFAULT_SETTINGS.items():
                if key not in self.settings:
                    self.settings[key] = default_val
            if 'work_types' not in self.settings:
                self.settings['work_types'] = DEFAULT_SETTINGS['work_types'].copy()
            if 'countries' not in self.settings:
                self.settings['countries'] = DEFAULT_SETTINGS['countries'].copy()
            if 'stats_date' not in self.settings:
                self.settings['stats_date'] = None
            logger.info("Настройки загружены из базы")
        else:
            self.settings = DEFAULT_SETTINGS.copy()
            logger.info("Используются настройки по умолчанию")

    def save_settings(self):
        logger.info("Сохранение настроек в TinyDB")
        settings_table = db.table('settings')
        settings_table.truncate()
        settings_table.insert(self.settings)
        logger.info("Настройки сохранены")

    def apply_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")

        if self.settings.get("theme") == "dark":
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#121212"))
            palette.setColor(QPalette.WindowText, QColor("#E1E1E1"))
            palette.setColor(QPalette.Base, QColor("#1E1E1E"))
            palette.setColor(QPalette.AlternateBase, QColor("#2D2D2D"))
            palette.setColor(QPalette.ToolTipBase, QColor("#2D2D2D"))
            palette.setColor(QPalette.ToolTipText, QColor("#E1E1E1"))
            palette.setColor(QPalette.Text, QColor("#E1E1E1"))
            palette.setColor(QPalette.Button, QColor("#2D2D2D"))
            palette.setColor(QPalette.ButtonText, QColor("#E1E1E1"))
            palette.setColor(QPalette.BrightText, QColor("#FF5252"))
            palette.setColor(QPalette.Link, QColor("#BB86FC"))
            palette.setColor(QPalette.Highlight, QColor("#BB86FC"))
            palette.setColor(QPalette.HighlightedText, QColor("#000000"))
            app.setPalette(palette)

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #121212;
                }
                QPushButton {
                    background-color: #BB86FC;
                    color: #000000;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #D7B5FF;
                }
                QPushButton:pressed {
                    background-color: #9965E0;
                }
                QPushButton:disabled {
                    background-color: #3D3D3D;
                    color: #6D6D6D;
                }
                QLabel {
                    color: #E1E1E1;
                    font-size: 13px;
                }
                QLineEdit, QSpinBox {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #BB86FC;
                }
                QComboBox {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QComboBox:focus {
                    border: 2px solid #BB86FC;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    selection-background-color: #BB86FC;
                    selection-color: #000000;
                }
                QTableWidget {
                    background-color: #1E1E1E;
                    alternate-background-color: #252525;
                    color: #E1E1E1;
                    gridline-color: #3D3D3D;
                    border: none;
                    border-radius: 12px;
                }
                QTableWidget::item {
                    padding: 8px;
                }
                QTableWidget::item:selected {
                    background-color: #BB86FC;
                    color: #000000;
                }
                QHeaderView::section {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    padding: 12px 8px;
                    border: none;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #E1E1E1;
                    spacing: 8px;
                    padding: 4px;
                    font-size: 13px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #BB86FC;
                    background-color: #2D2D2D;
                }
                QCheckBox::indicator:checked {
                    background-color: #BB86FC;
                    border: 2px solid #BB86FC;
                }
                QFrame#header {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                stop:0 #6A1B9A, stop:1 #8E24AA);
                    border-radius: 0px;
                }
                QFrame#statsCard {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                }
                QFrame#settingsCard {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                }
                QFrame#statsChartFrame {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    border: 2px solid #2D2D2D;
                }
                QGroupBox {
                    color: #E1E1E1;
                    border: 2px solid #3D3D3D;
                    border-radius: 8px;
                    margin-top: 12px;
                    padding-top: 12px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #3D3D3D;
                    background-color: #1E1E1E;
                }
                QTabBar::tab {
                    background-color: #2D2D2D;
                    color: #E1E1E1;
                    padding: 8px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #BB86FC;
                    color: #000000;
                }
                QChartView {
                    background-color: #1E1E1E;
                    border: none;
                }
            """)
        else:
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor("#F5F5F5"))
            palette.setColor(QPalette.WindowText, QColor("#212121"))
            palette.setColor(QPalette.Base, QColor("#FFFFFF"))
            palette.setColor(QPalette.AlternateBase, QColor("#FAFAFA"))
            palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
            palette.setColor(QPalette.ToolTipText, QColor("#212121"))
            palette.setColor(QPalette.Text, QColor("#212121"))
            palette.setColor(QPalette.Button, QColor("#FFFFFF"))
            palette.setColor(QPalette.ButtonText, QColor("#212121"))
            palette.setColor(QPalette.BrightText, QColor("#FF5252"))
            palette.setColor(QPalette.Link, QColor("#6200EE"))
            palette.setColor(QPalette.Highlight, QColor("#6200EE"))
            palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
            app.setPalette(palette)

            self.setStyleSheet("""
                QMainWindow {
                    background-color: #F5F5F5;
                }
                QPushButton {
                    background-color: #6200EE;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #7C4DFF;
                }
                QPushButton:pressed {
                    background-color: #5600D6;
                }
                QPushButton:disabled {
                    background-color: #E0E0E0;
                    color: #9E9E9E;
                }
                QLabel {
                    color: #212121;
                    font-size: 13px;
                }
                QLineEdit, QSpinBox {
                    background-color: #FFFFFF;
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 2px solid #6200EE;
                }
                QComboBox {
                    background-color: #FFFFFF;
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QComboBox:focus {
                    border: 2px solid #6200EE;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #FFFFFF;
                    color: #212121;
                    selection-background-color: #6200EE;
                    selection-color: #FFFFFF;
                }
                QTableWidget {
                    background-color: #FFFFFF;
                    alternate-background-color: #FAFAFA;
                    color: #212121;
                    gridline-color: #E0E0E0;
                    border: none;
                    border-radius: 12px;
                }
                QTableWidget::item {
                    padding: 8px;
                }
                QTableWidget::item:selected {
                    background-color: #6200EE;
                    color: #FFFFFF;
                }
                QHeaderView::section {
                    background-color: #FAFAFA;
                    color: #212121;
                    padding: 12px 8px;
                    border: none;
                    border-bottom: 2px solid #E0E0E0;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox {
                    color: #212121;
                    spacing: 8px;
                    padding: 4px;
                    font-size: 13px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #6200EE;
                    background-color: #FFFFFF;
                }
                QCheckBox::indicator:checked {
                    background-color: #6200EE;
                    border: 2px solid #6200EE;
                }
                QFrame#header {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                stop:0 #6200EE, stop:1 #9D46FF);
                    border-radius: 0px;
                }
                QFrame#statsCard {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                }
                QFrame#settingsCard {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                }
                QFrame#statsChartFrame {
                    background-color: #FFFFFF;
                    border-radius: 12px;
                    border: none;
                }
                QGroupBox {
                    color: #212121;
                    border: 2px solid #E0E0E0;
                    border-radius: 8px;
                    margin-top: 12px;
                    padding-top: 12px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #E0E0E0;
                    background-color: #FFFFFF;
                }
                QTabBar::tab {
                    background-color: #FAFAFA;
                    color: #212121;
                    padding: 8px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #6200EE;
                    color: #FFFFFF;
                }
                QChartView {
                    background-color: #FFFFFF;
                    border: none;
                }
            """)

    def toggle_theme(self):
        current = self.settings.get("theme", "light")
        self.settings["theme"] = "dark" if current == "light" else "light"
        self.save_settings()
        self.theme_btn.setText("Темная" if self.settings["theme"] == "light" else "Светлая")
        self.apply_theme()
        self.update_table()
        self.update_stats_chart()

    def init_ui(self):
        logger.info("Инициализация UI")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        menubar = self.menuBar()
        help_menu = menubar.addMenu("Справка")
        help_menu.addAction("О программе", self.show_about_dialog)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(80)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)

        title_layout = QVBoxLayout()
        title = QLabel("Удобные Вакансии")
        title.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        subtitle = QLabel("Удаленная работа • Россия и Беларусь")
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 12px;")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        buttons_layout = QHBoxLayout()
        self.update_btn = QPushButton("Обновить")
        self.theme_btn = QPushButton("Темная" if self.settings.get("theme") == "light" else "Светлая")
        self.about_btn = QPushButton("О программе")
        self.exit_btn = QPushButton("Выход")

        self.support_btn = QPushButton("Поддержать")
        self.support_btn.setFixedHeight(40)
        self.support_btn.clicked.connect(self.show_support_dialog)

        self.update_btn.setFixedHeight(40)
        self.theme_btn.setFixedSize(110, 40)
        self.about_btn.setMinimumWidth(140)
        self.about_btn.setFixedHeight(40)
        self.exit_btn.setFixedSize(110, 40)

        self.update_btn.clicked.connect(self.update_vacancies)
        self.exit_btn.clicked.connect(self.close_application)
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.about_btn.clicked.connect(self.show_about_dialog)

        buttons_layout.addWidget(self.update_btn)
        buttons_layout.addWidget(self.theme_btn)
        buttons_layout.addWidget(self.support_btn)
        buttons_layout.addWidget(self.about_btn)
        buttons_layout.addWidget(self.exit_btn)
        header_layout.addLayout(buttons_layout)

        main_layout.addWidget(header)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 12, 15, 12)
        content_layout.setSpacing(12)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # Вкладка "Вакансии"
        vacancies_tab = QWidget()
        vacancies_layout = QVBoxLayout(vacancies_tab)
        vacancies_layout.setContentsMargins(0, 0, 0, 0)
        vacancies_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        stats_card = QFrame()
        stats_card.setObjectName("statsCard")
        stats_card.setFixedHeight(85)
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(20, 12, 20, 12)

        total_layout = QVBoxLayout()
        total_layout.setSpacing(3)
        self.total_label = QLabel("0")
        self.total_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #6200EE;" if self.settings.get(
            "theme") == "light" else "font-size: 28px; font-weight: bold; color: #BB86FC;")
        total_text = QLabel("Всего")
        total_text.setStyleSheet("font-size: 11px; opacity: 0.7;")
        total_layout.addWidget(self.total_label)
        total_layout.addWidget(total_text)

        new_layout = QVBoxLayout()
        new_layout.setSpacing(3)
        self.new_label = QLabel("0")
        self.new_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #00C853;")
        new_text = QLabel("Новых")
        new_text.setStyleSheet("font-size: 11px; opacity: 0.7;")
        new_layout.addWidget(self.new_label)
        new_layout.addWidget(new_text)

        stats_layout.addLayout(total_layout)
        stats_layout.addSpacing(30)
        stats_layout.addLayout(new_layout)
        stats_layout.addStretch()

        top_row.addWidget(stats_card, 1)

        settings_card = QFrame()
        settings_card.setObjectName("settingsCard")
        settings_card.setFixedHeight(85)
        settings_layout = QHBoxLayout(settings_card)
        settings_layout.setContentsMargins(15, 12, 15, 12)
        settings_layout.setSpacing(10)

        settings_layout.addWidget(QLabel("Слово:"))
        self.query_input = QLineEdit()
        self.query_input.setText(self.settings.get("query", ""))
        self.query_input.setFixedWidth(200)
        self.query_input.setMinimumHeight(36)
        settings_layout.addWidget(self.query_input)

        settings_layout.addWidget(QLabel("Период:"))
        self.days_input = QSpinBox()
        self.days_input.setRange(1, 30)
        self.days_input.setValue(self.settings.get("days", 1))
        self.days_input.setFixedWidth(70)
        self.days_input.setMinimumHeight(32)
        settings_layout.addWidget(self.days_input)

        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator1)

        self.remote_checkbox = QCheckBox("Удаленка")
        self.remote_checkbox.setChecked(self.settings.get('work_types', {}).get('remote', True))
        self.remote_checkbox.setMinimumHeight(25)

        self.hybrid_checkbox = QCheckBox("Гибрид")
        self.hybrid_checkbox.setChecked(self.settings.get('work_types', {}).get('hybrid', False))
        self.hybrid_checkbox.setMinimumHeight(25)

        self.office_checkbox = QCheckBox("Офис")
        self.office_checkbox.setChecked(self.settings.get('work_types', {}).get('office', False))
        self.office_checkbox.setMinimumHeight(25)

        settings_layout.addWidget(self.remote_checkbox)
        settings_layout.addWidget(self.hybrid_checkbox)
        settings_layout.addWidget(self.office_checkbox)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator2)

        self.russia_checkbox = QCheckBox("RU")
        self.russia_checkbox.setChecked(self.settings.get('countries', {}).get('russia', True))
        self.russia_checkbox.setMinimumHeight(25)

        self.belarus_checkbox = QCheckBox("BY")
        self.belarus_checkbox.setChecked(self.settings.get('countries', {}).get('belarus', True))
        self.belarus_checkbox.setMinimumHeight(25)

        settings_layout.addWidget(self.russia_checkbox)
        settings_layout.addWidget(self.belarus_checkbox)

        separator3 = QFrame()
        separator3.setFrameShape(QFrame.VLine)
        separator3.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(separator3)

        self.auto_update_checkbox = QCheckBox("Автообновление")
        self.auto_update_checkbox.setChecked(
            self.settings.get('auto_update', {}).get('enabled', False)
        )
        self.auto_update_checkbox.setMinimumHeight(25)
        settings_layout.addWidget(self.auto_update_checkbox)

        self.auto_update_interval = QSpinBox()
        self.auto_update_interval.setRange(1, 1440)
        self.auto_update_interval.setValue(
            self.settings.get('auto_update', {}).get('interval_minutes', 30)
        )
        self.auto_update_interval.setSuffix(" мин")
        self.auto_update_interval.setFixedWidth(90)
        self.auto_update_interval.setMinimumHeight(32)
        settings_layout.addWidget(self.auto_update_interval)

        settings_layout.addStretch()

        self.save_settings_btn = QPushButton("Сохранить")
        self.save_settings_btn.setFixedSize(110, 38)
        self.save_settings_btn.clicked.connect(self.save_app_settings)
        settings_layout.addWidget(self.save_settings_btn)

        top_row.addWidget(settings_card, 2)
        vacancies_layout.addLayout(top_row)

        exclude_row = QHBoxLayout()
        exclude_label = QLabel("Исключить:")
        exclude_label.setFixedWidth(70)
        exclude_row.addWidget(exclude_label)

        self.exclude_input = QLineEdit()
        self.exclude_input.setText(self.settings.get("exclude", ""))
        self.exclude_input.setPlaceholderText("Через запятую: Android, QA, Тестировщик...")
        self.exclude_input.setMinimumHeight(35)
        exclude_row.addWidget(self.exclude_input)
        vacancies_layout.addLayout(exclude_row)

        self.action_widget = QWidget()
        self.action_widget.setFixedHeight(45)
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)

        self.select_all_btn = QPushButton("Выбрать все")
        self.mark_btn = QPushButton("Пометить просмотренными")
        self.select_all_btn.setFixedHeight(36)
        self.mark_btn.setFixedHeight(36)
        self.select_all_btn.clicked.connect(self.select_all_new)
        self.mark_btn.clicked.connect(self.mark_selected_as_old)

        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.mark_btn)
        action_layout.addStretch()
        self.action_widget.hide()
        vacancies_layout.addWidget(self.action_widget)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            ["", "Статус", "Название", "Компания", "Город", "Тип работы", "Зарплата", "Дата", "Дата загрузки",
             "Действие"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 45)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 120)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 350)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 110)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        header.resizeSection(7, 90)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        header.resizeSection(8, 150)
        header.setSectionResizeMode(9, QHeaderView.Fixed)
        header.resizeSection(9, 160)

        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setVisible(False)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self.on_cell_click)
        self.table.setShowGrid(False)

        vacancies_layout.addWidget(self.table)
        self.tab_widget.addTab(vacancies_tab, "Вакансии")

        # Вкладка "Статистика"
        stats_tab = QWidget()
        stats_tab_layout = QVBoxLayout(stats_tab)
        stats_tab_layout.setContentsMargins(15, 12, 15, 12)
        stats_tab_layout.setSpacing(12)

        stats_control_frame = QFrame()
        stats_control_frame.setObjectName("settingsCard")
        stats_control_frame.setFixedHeight(70)
        stats_control_layout = QHBoxLayout(stats_control_frame)
        stats_control_layout.setContentsMargins(15, 10, 15, 10)
        stats_control_layout.setSpacing(15)

        stats_control_layout.addWidget(QLabel("Режим:"))
        self.stats_mode_combo = QComboBox()
        self.stats_mode_combo.addItems([
            "Вакансии по часам (за день)",
            "Вакансии по дням (неделя)",
            "Вакансии по дням (месяц)",
            "Вакансии по дням (3 месяца)",
            "Вакансии по дням (6 месяцев)"
        ])
        self.stats_mode_combo.setMinimumWidth(220)
        self.stats_mode_combo.currentTextChanged.connect(self.on_stats_mode_changed)
        stats_control_layout.addWidget(self.stats_mode_combo)

        stats_control_layout.addWidget(QLabel("Дата:"))
        self.stats_date_combo = QComboBox()
        self.stats_date_combo.setMinimumWidth(130)
        self.stats_date_combo.currentIndexChanged.connect(self.update_stats_chart)
        stats_control_layout.addWidget(self.stats_date_combo)

        self.prev_btn = QPushButton("←")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.clicked.connect(self.go_older_date)
        self.prev_btn.setVisible(False)
        stats_control_layout.addWidget(self.prev_btn)

        self.today_btn = QPushButton("Сегодня")
        self.today_btn.setFixedWidth(120)
        self.today_btn.clicked.connect(self.today_date)
        self.today_btn.setVisible(False)
        stats_control_layout.addWidget(self.today_btn)

        self.next_btn = QPushButton("→")
        self.next_btn.setFixedWidth(80)
        self.next_btn.clicked.connect(self.go_newer_date)
        self.next_btn.setVisible(False)
        stats_control_layout.addWidget(self.next_btn)

        stats_control_layout.addStretch()
        stats_tab_layout.addWidget(stats_control_frame)

        self.stats_chart_frame = QFrame()
        self.stats_chart_frame.setObjectName("statsChartFrame")
        self.stats_chart_layout = QVBoxLayout(self.stats_chart_frame)
        self.stats_chart_layout.setContentsMargins(20, 12, 20, 12)
        self.chart_view = None
        stats_tab_layout.addWidget(self.stats_chart_frame)
        self.tab_widget.addTab(stats_tab, "Статистика")

        content_layout.addWidget(self.tab_widget)

        main_layout.addWidget(content_widget)

        # Подключение сохранения настроек для статистики
        def save_mode(text):
            self.settings['stats_mode'] = text
            self.save_settings()
        self.stats_mode_combo.currentTextChanged.connect(save_mode)

        def save_date():
            current_data = self.stats_date_combo.currentData()
            self.settings['stats_date'] = current_data.isoformat() if current_data else None
            self.save_settings()
            self.update_date_buttons()
        self.stats_date_combo.currentIndexChanged.connect(save_date)

        # Восстановление выбранного режима
        self.stats_mode_combo.setCurrentText(self.settings.get('stats_mode', "Вакансии по часам (за день)"))

    def go_older_date(self):
        """Переход к более старой дате (увеличение индекса)"""
        current_index = self.stats_date_combo.currentIndex()
        if current_index < self.stats_date_combo.count() - 1:
            self.stats_date_combo.setCurrentIndex(current_index + 1)

    def go_newer_date(self):
        """Переход к более новой дате (уменьшение индекса)"""
        current_index = self.stats_date_combo.currentIndex()
        if current_index > 0:
            self.stats_date_combo.setCurrentIndex(current_index - 1)

    # def prev_date(self):
    #     current_index = self.stats_date_combo.currentIndex()
    #     if current_index > 0:
    #         self.stats_date_combo.setCurrentIndex(current_index - 1)
    #
    # def next_date(self):
    #     current_index = self.stats_date_combo.currentIndex()
    #     if current_index < self.stats_date_combo.count() - 1:
    #         self.stats_date_combo.setCurrentIndex(current_index + 1)

    def today_date(self):
        today = datetime.now().date()
        for i in range(self.stats_date_combo.count()):
            if self.stats_date_combo.itemData(i) == today:
                self.stats_date_combo.setCurrentIndex(i)
                break

    def update_date_buttons(self):
        current_index = self.stats_date_combo.currentIndex()
        self.prev_btn.setEnabled(current_index < self.stats_date_combo.count() - 1)  # ← для старой: если не последняя
        self.next_btn.setEnabled(current_index > 0)  # → для новой: если не первая

    def save_app_settings(self):
        query = self.query_input.text().strip()
        exclude = self.exclude_input.text().strip()
        days = self.days_input.value()

        if not query:
            QMessageBox.warning(self, "Ошибка", "Укажите ключевое слово")
            return

        work_types = {
            'remote': self.remote_checkbox.isChecked(),
            'hybrid': self.hybrid_checkbox.isChecked(),
            'office': self.office_checkbox.isChecked()
        }

        countries = {
            'russia': self.russia_checkbox.isChecked(),
            'belarus': self.belarus_checkbox.isChecked()
        }

        auto_update = {
            'enabled': self.auto_update_checkbox.isChecked(),
            'interval_minutes': self.auto_update_interval.value()
        }

        self.settings.update({
            "query": query,
            "exclude": exclude,
            "days": days,
            "work_types": work_types,
            "countries": countries,
            "auto_update": auto_update
        })

        self.save_settings()
        self.setup_auto_update()
        QMessageBox.information(self, "Успех", "Настройки сохранены!")

    def update_table(self):
        logger.info("Обновление таблицы")
        new_count = sum(1 for v in self.vacancies if v.get('status') == 'NEW')
        self.total_label.setText(str(len(self.vacancies)))
        self.new_label.setText(str(new_count))

        if new_count > 0:
            self.action_widget.show()
        else:
            self.action_widget.hide()

        sorted_vacancies = sorted(self.vacancies, key=lambda x: self.parse_loaded_date(x.get('loaded_at', '')),
                                  reverse=True)
        sorted_vacancies.sort(key=lambda x: 0 if x.get('status') == 'NEW' else 1)

        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                self.table.removeCellWidget(row, 0)
                widget.deleteLater()

        self.table.setRowCount(len(sorted_vacancies))

        is_dark = self.settings.get("theme") == "dark"

        for row, v in enumerate(sorted_vacancies):
            if v.get('status') == 'NEW':
                checkbox = QCheckBox()
                self.table.setCellWidget(row, 0, checkbox)
            else:
                self.table.setItem(row, 0, QTableWidgetItem(""))

            status_text = "🆕 Новая" if v.get('status') == 'NEW' else "👁️ Просмотрена"
            status_item = QTableWidgetItem(status_text)

            if v.get('status') == 'NEW':
                if is_dark:
                    status_item.setBackground(QColor("#1B5E20"))
                    status_item.setForeground(QColor("#69F0AE"))
                else:
                    status_item.setBackground(QColor("#C8E6C9"))
                    status_item.setForeground(QColor("#1B5E20"))
            else:
                if is_dark:
                    status_item.setBackground(QColor("#424242"))
                    status_item.setForeground(QColor("#BDBDBD"))
                else:
                    status_item.setBackground(QColor("#F5F5F5"))
                    status_item.setForeground(QColor("#757575"))

            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            self.table.setItem(row, 1, status_item)

            self.table.setItem(row, 2, QTableWidgetItem(v.get('title', '-')))
            self.table.setItem(row, 3, QTableWidgetItem(v.get('company', '-')))
            self.table.setItem(row, 4, QTableWidgetItem(v.get('city', '-')))

            schedule = v.get('schedule', '-')
            schedule_item = QTableWidgetItem(schedule)
            self.table.setItem(row, 5, schedule_item)

            self.table.setItem(row, 6, QTableWidgetItem(v.get('salary', '-')))
            self.table.setItem(row, 7, QTableWidgetItem(v.get('date', '-')))
            self.table.setItem(row, 8, QTableWidgetItem(v.get('loaded_at', '-')))

            open_item = QTableWidgetItem("🔗 Открыть")
            open_item.setData(Qt.UserRole, v.get('link', ''))
            open_item.setTextAlignment(Qt.AlignCenter)
            open_item.setForeground(QColor("#BB86FC" if is_dark else "#6200EE"))
            font = open_item.font()
            font.setBold(True)
            open_item.setFont(font)
            self.table.setItem(row, 9, open_item)

        logger.info("Таблица обновлена")

    def on_cell_click(self, row, column):
        if column == 9:
            item = self.table.item(row, column)
            if item:
                link = item.data(Qt.UserRole)
                if link and link != "#":
                    logger.info(f"Открытие ссылки: {link}")
                    QDesktopServices.openUrl(link)

    def load_vacancies_from_file(self):
        logger.info("Загрузка вакансий из TinyDB")
        vacancies_table = db.table('vacancies')
        self.vacancies = vacancies_table.all()
        logger.info(f"Загружено {len(self.vacancies)} вакансий из базы")

    def save_vacancies_to_file(self):
        logger.info("Сохранение вакансий в TinyDB")
        vacancies_table = db.table('vacancies')
        vacancies_table.truncate()
        vacancies_table.insert_multiple(self.vacancies)
        logger.info("Вакансии сохранены")

    def update_vacancies(self):
        logger.info("Нажата кнопка 'Обновить'")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("⏳ Обновление...")
        old_links = {v['link'] for v in self.vacancies}
        self.worker = UpdateWorker(self.settings.copy(), old_links)  # ← передаём old_links
        self.worker.finished.connect(self.on_update_finished)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_update_finished(self, truly_new):
        logger.info(f"Обновление завершено: {len(truly_new)} новых вакансий")

        for v in truly_new:
            if 'status' not in v:
                v['status'] = 'NEW'
        self.vacancies.extend(truly_new)
        print(f"DEBUG: on_update_finished: {len(truly_new)} новых, вызываем save")
        self.save_vacancies_to_file()
        self.populate_stats_dates()
        self.update_table()
        self.update_stats_chart()

        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Обновить")

        if truly_new:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Успех")
            msg.setText(f"✅ Найдено {len(truly_new)} новых вакансий!")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Информация")
            msg.setText("ℹ️ Нет новых вакансий")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

    def on_update_error(self, error_msg):
        logger.error(f"Ошибка обновления: {error_msg}")
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Ошибка")
        msg.setText(f"❌ Ошибка при обновлении:\n{error_msg}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Обновить")

    def select_all_new(self):
        logger.info("Выбор всех новых вакансий")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and "Новая" in item.text():
                checkbox = self.table.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(True)

    def mark_selected_as_old(self):
        logger.info("Пометка выбранных как просмотренные")
        updated = 0
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                link_item = self.table.item(row, 9)
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
            self.update_stats_chart()
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Успех")
            msg.setText(f"✅ Помечено {updated} вакансий как просмотренные")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Внимание")
            msg.setText("⚠️ Не выбрано ни одной вакансии")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

    def show_about_dialog(self):
        """Показывает информацию о приложении и разработчике"""
        text = (
            "<b>Удобные Вакансии — HH.ru</b><br><br>"
            "Разработчик: Максим К.<br>"
            "Email: <a href='mailto:maximkisten@gmail.com'>maximkisten@gmail.com</a><br>"
            "Telegram: <a href='https://t.me/maximkisten'>@maximkisten</a><br><br>"
            "Все мысли и пожелания готов принимать по указанным контактам."
        )

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("О программе")
        msg.setTextFormat(Qt.RichText)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def show_support_dialog(self):
        """Открывает диалог с QR-кодом и просьбой о поддержке."""
        dialog = SupportDialog(self)
        dialog.exec()

    def populate_stats_dates(self):
        """Заполнение комбобокса с датами для статистики"""
        if not hasattr(self, 'stats_date_combo'):
            logger.warning("stats_date_combo ещё не создан, пропускаем populate_stats_dates")
            return

        dates = set()
        for v in self.vacancies:
            loaded_at_str = v.get('loaded_at', '')
            if loaded_at_str:
                try:
                    loaded_dt = datetime.strptime(loaded_at_str, "%Y-%m-%d %H:%M:%S")
                    dates.add(loaded_dt.date())
                except ValueError:
                    pass

        self.stats_date_combo.clear()

        if not dates:
            self.stats_date_combo.addItem("Нет данных")
            return

        for date in sorted(dates, reverse=True):
            self.stats_date_combo.addItem(date.strftime("%d.%m.%Y"), date)

        # Восстановить выбранную дату
        saved_date_str = self.settings.get('stats_date')
        if saved_date_str:
            try:
                saved_date = datetime.fromisoformat(saved_date_str).date()
                index = self.stats_date_combo.findData(saved_date)
                if index >= 0:
                    self.stats_date_combo.setCurrentIndex(index)
                else:
                    # Установить на последнюю (самую новую)
                    self.stats_date_combo.setCurrentIndex(0)
            except ValueError:
                # Неверный формат сохраненной даты
                self.stats_date_combo.setCurrentIndex(0)
        else:
            # Установить на последнюю (самую новую)
            self.stats_date_combo.setCurrentIndex(0)

        self.update_date_buttons()
        logger.info(f"Загружено {len(dates)} уникальных дат для статистики")

    def on_stats_mode_changed(self, mode):
        """Обработка изменения режима статистики"""
        is_hourly = mode == "Вакансии по часам (за день)"
        self.stats_date_combo.setVisible(is_hourly)
        self.prev_btn.setVisible(is_hourly)
        self.today_btn.setVisible(is_hourly)
        self.next_btn.setVisible(is_hourly)
        if is_hourly:
            self.update_date_buttons()

        for i in range(self.stats_date_combo.parentWidget().layout().count()):
            item = self.stats_date_combo.parentWidget().layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QLabel) and item.widget().text() == "Дата:":
                item.widget().setVisible(is_hourly)
                break

        self.update_stats_chart()


if __name__ == "__main__":
    print("=" * 50)
    print("Вход в main блок")
    print("=" * 50)
    try:
        logger.info("Запуск основного цикла приложения")
        print("Создание QApplication")
        app = QApplication(sys.argv)
        print("QApplication создан")

        app.setStyle("Fusion")
        print("Стиль установлен")

        print("Создание окна VacancyApp")
        window = VacancyApp()
        print("Окно создано")

        print("Показ окна")
        window.show()
        print("Окно показано")

        print("Запуск event loop")
        sys.exit(app.exec())
    except Exception as e:
        print(f"=" * 50)
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        print(f"=" * 50)
        import traceback

        traceback.print_exc()
        input("Нажмите Enter для выхода...")