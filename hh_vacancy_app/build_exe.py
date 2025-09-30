import PyInstaller.__main__
import os
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

# Сборка
PyInstaller.__main__.run([
    'app.py',
    '--name=HH_Vacancy_App',
    '--onefile',
    '--windowed',
    '--add-data=templates;templates',
    '--add-data=icon.png;.',
    f'--icon={ico_icon}',
    '--clean',
    '--noconfirm',
])

print("\n" + "="*60)
print("✅ Сборка завершена!")
print("📁 EXE файл находится в папке: dist/HH_Vacancy_App.exe")
print("="*60)