import PyInstaller.__main__
import os
import sys
from PIL import Image

# Получаем текущую директорию
current_dir = os.path.dirname(os.path.abspath(__file__))

# Генерация icon.ico из icon.png
png_icon = os.path.join(current_dir, "icon.png")
ico_icon = os.path.join(current_dir, "icon.ico")

if os.path.exists(png_icon):
    img = Image.open(png_icon)
    img.save(ico_icon, sizes=[(16,16), (32,32), (48,48), (256,256)])
    print("✅ icon.ico создан из icon.png")

# Проверяем наличие файлов
qr_code_file = os.path.join(current_dir, "qr-code.png")
if os.path.exists(qr_code_file):
    print(f"✅ QR-код найден: {qr_code_file}")
else:
    print(f"⚠️ ВНИМАНИЕ: QR-код НЕ найден: {qr_code_file}")

# Определяем разделитель для --add-data в зависимости от ОС
separator = ';' if sys.platform == 'win32' else ':'

# Сборка
PyInstaller.__main__.run([
    'app.py',
    '--name=HH_Vacancy_App',
    '--onefile',
    '--windowed',
    f'--add-data=icon.png{separator}.',
    f'--add-data=qr-code.png{separator}.',
    f'--icon={ico_icon}',
    '--clean',
    '--noconfirm',
])

print("\n" + "="*60)
print("✅ Сборка завершена!")
print("📁 EXE файл находится в папке: dist/HH_Vacancy_App.exe")
print("="*60)