import os
import sys

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

from ui import App
from ui.database import create_database_and_tables

def initialize_project():
    """Проверяет наличие необходимых папок и файлов"""
    if not os.path.exists("data"):
        os.makedirs("data")
        print("Создана папка /data")

def main():
    # Инициализация (создание папок, если их нет)
    initialize_project()

    create_database_and_tables()

    # Запуск приложения
    app = App()
    
    # Можно задать тему через main, чтобы не хардкодить в классе
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    
    app.mainloop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
