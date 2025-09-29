import PyInstaller.__main__
import os

# Получаем текущую директорию
current_dir = os.path.dirname(os.path.abspath(__file__))

PyInstaller.__main__.run([
    'app.py',
    '--name=HH_Vacancy_App',
    '--onefile',
    '--windowed',
    '--add-data=templates;templates',
    '--icon=icon.ico',
    '--clean',
    '--noconfirm',
])

print("\n" + "="*60)
print("✅ Сборка завершена!")
print("📁 EXE файл находится в папке: dist/HH_Vacancy_App.exe")
print("="*60)