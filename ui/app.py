import customtkinter as ctk
import tksheet
import base64
import io
import tkinter as tk
from datetime import datetime
from sqlmodel import Session
from PIL import Image, ImageTk

from ui.database import Experiments, Measurements, engine

import os
import pandas as pd
from pathlib import Path
import json
from sqlmodel import select

from ui.cpp_bridge import run_measurement_pipeline, save_measurement_run


_ORIGINAL_TK_PHOTO_IMAGE = tk.PhotoImage


def _safe_photo_image(*args, **kwargs):
    """
    Fallback for older Tk builds on macOS that cannot decode PNG data
    embedded inside newer tksheet versions.
    """
    try:
        return _ORIGINAL_TK_PHOTO_IMAGE(*args, **kwargs)
    except tk.TclError:
        data = kwargs.get("data")
        if not isinstance(data, str):
            raise

        try:
            image_bytes = base64.b64decode(data)
            image = Image.open(io.BytesIO(image_bytes))
            return ImageTk.PhotoImage(image)
        except Exception:
            raise


tk.PhotoImage = _safe_photo_image


class LoginWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Авторизация")
        self.geometry("350x200")
        self.attributes("-topmost", True)
        self.after(100, self._center_window)
        self.grab_set()

        ctk.CTkLabel(self, text="Введите ФИО оператора", font=("Arial", 14)).pack(pady=(30, 10))
        self.entry = ctk.CTkEntry(self, placeholder_text="Иванов И.И.", width=220)
        self.entry.pack(pady=10)
        self.entry.bind("<Return>", lambda e: self.submit())

        ctk.CTkButton(self, text="Войти", command=self.submit).pack(pady=20)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def submit(self):
        name = self.entry.get().strip()
        if name:
            self.parent.operator_name = name
            self.parent.update_operator_info()
            self.destroy()
        else:
            self.entry.configure(border_color="red")

    def on_closing(self):
        self.parent.destroy()


class RegistrationSetupWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Параметры регистрации")
        self.geometry("460x400")
        self.attributes("-topmost", True)
        self.grab_set()
        self.after(100, self._center_window)

        ctk.CTkLabel(self, text="Настройка условий", font=("Arial", 16, "bold")).pack(pady=15)

        ctk.CTkLabel(self, text="Название эксперимента*:").pack(anchor="w", padx=30)
        self.experiment_name_entry = ctk.CTkEntry(self, width=340)
        self.experiment_name_entry.pack(pady=(5, 15), padx=30)

        ctk.CTkLabel(self, text="Количество кадров:").pack(anchor="w", padx=30)
        self.frames_entry = ctk.CTkEntry(self, width=340)
        self.frames_entry.insert(0, "2000")
        self.frames_entry.pack(pady=(5, 20), padx=30)

        self.btn_start = ctk.CTkButton(self, text="Начать регистрацию", 
                                       command=self.start_action, height=40)
        self.btn_start.pack(pady=10)

        # Область загрузки
        self.loading_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="", font=("Arial", 13))
        self.loading_label.pack(pady=(0, 8))
        self.progress_bar = ctk.CTkProgressBar(self.loading_frame, width=340, height=12)
        self.progress_bar.pack()
        self.progress_bar.set(0)
        self.loading_frame.pack_forget()

    def _center_window(self):
        x = self.master.winfo_x() + (self.master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.master.winfo_y() + (self.master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def start_action(self):
        name = self.experiment_name_entry.get().strip()
        frames_raw = self.frames_entry.get().strip()

        if not name:
            self.experiment_name_entry.configure(border_color="red")
            return
        if not frames_raw.isdigit() or int(frames_raw) < 1:
            self.frames_entry.configure(border_color="red")
            return

        n_frames = int(frames_raw)

        with Session(engine) as session:
            new_experiment = Experiments(
                name=name,
                operator=self.master.operator_name
            )
            session.add(new_experiment)
            session.commit()
            session.refresh(new_experiment)

            # сохраняем id, чтобы потом привязать измерения
            self.experiment_id = new_experiment.id

        self.master.add_log(f"Эксперимент '{name}' создан (ID={self.experiment_id})")

        self.experiment_name_entry.configure(border_color=["#979DA2", "#565B5E"])
        self.frames_entry.configure(border_color=["#979DA2", "#565B5E"])

        self.loading_frame.pack(fill="x", padx=30, pady=15)
        self.loading_label.configure(text="Регистрация данных...")
        self.progress_bar.set(0)
        self.btn_start.configure(state="disabled", text="Идёт регистрация...")

        self.after(50, lambda: self._run_generation(name, n_frames))

    def _run_generation(self, name, n_frames):
        self.master.add_log(f"Старт регистрации: '{name}' ({n_frames} кадров)")

        def update_progress(current, total):
            if total <= 0:
                return
            if current % max(1, total // 20) != 0 and current != total:
                return

            progress = current / total
            self.progress_bar.set(progress)
            self.loading_label.configure(text=f"Регистрация... {int(progress * 100)}%")
            self.update_idletasks()

        try:
            result = run_measurement_pipeline(
                frame_count=n_frames,
                progress_callback=update_progress,
            )
            save_measurement_run(self.experiment_id, result)
        except Exception as error:
            self.loading_label.configure(text="Ошибка регистрации")
            self.btn_start.configure(state="normal", text="Начать регистрацию")
            self.master.add_log(f"❌ Ошибка регистрации: {error}")
            return

        new_data = [self.master.headers[:]]
        new_data.extend(result.rows)

        self.progress_bar.set(1)
        self.loading_label.configure(text="Регистрация завершена")
        self.master.set_full_data(new_data)
        self.master.add_log(f"✅ Зарегистрировано {len(result.rows)} кадров")
        self.master.add_log(f"⏹ Эксперимент завершён (ID={self.experiment_id})")
        self.master.download_btn.configure(state="normal")
        self.destroy()


class AboutWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("О программе")
        self.geometry("400x350")
        self.attributes("-topmost", True)
        self.grab_set()
        self.resizable(False, False)
        self.after(100, self._center_window)

        ctk.CTkLabel(self, text="📊", font=("Arial", 60)).pack(pady=(20, 10))
        ctk.CTkLabel(self, text="Система регистрации и обработки данных", 
                     font=("Arial", 18, "bold")).pack()
        desc = "Комплекс программных средств\nдля регистрации и обработки данных измерений"
        ctk.CTkLabel(self, text=desc, font=("Arial", 13), justify="center").pack(pady=20)

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(pady=10)
        ctk.CTkLabel(info, text="Разработчик:", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=5, sticky="e")
        ctk.CTkLabel(info, text="Бригада №1", font=("Arial", 12)).grid(row=0, column=1, padx=5, sticky="w")

        ctk.CTkButton(self, text="Закрыть", width=100, command=self.destroy).pack(pady=(20, 10))

    def _center_window(self):
        x = self.master.winfo_x() + (self.master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.master.winfo_y() + (self.master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

class DataManagementWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title("Управление данными")
        self.geometry("500x800")
        self.grab_set()
        self.attributes("-topmost", True)

        ctk.CTkLabel(self, text="Выбор эксперимента", font=("Arial", 16, "bold")).pack(pady=10)

        # ===== Список экспериментов =====
        self.exp_combo = ctk.CTkComboBox(self, width=300)
        self.exp_combo.pack(pady=10)

        self.experiments_map = {}
        self.exp_combo.configure(command=lambda _: self.update_frame_range())

        # ===== Диапазон кадров (ПЕРЕНЕСЁН ВЫШЕ!) =====
        ctk.CTkLabel(self, text="Диапазон кадров:", font=("Arial", 14)).pack(pady=(15, 5))

        range_frame = ctk.CTkFrame(self, fg_color="transparent")
        range_frame.pack()

        self.frame_from = ctk.CTkEntry(range_frame, width=100)
        self.frame_from.pack(side="left", padx=5)

        self.frame_to = ctk.CTkEntry(range_frame, width=100)
        self.frame_to.pack(side="left", padx=5)

        # ===== Чекбоксы каналов =====
        ctk.CTkLabel(self, text="Выберите каналы:", font=("Arial", 14)).pack(pady=10)

        self.channels = [
            ("Кадр", "number"),
            ("Канал 1", "channel_1"),
            ("Канал 2", "channel_2"),
            ("Канал 3", "channel_3"),
            ("Канал 4", "channel_4"),
            ("Канал 5", "channel_5"),
            ("Канал 6 Среднее", "channel_6_avg"),
            ("Канал 6 Дисперсия", "channel_6_disp"),
            ("Канал 19", "channel_19"),
            ("Канал 49", "channel_49"),
            ("Канал 69 F", "channel_69_func"),
        ]

        self.check_vars = {}

        frame = ctk.CTkFrame(self)
        frame.pack(pady=10, fill="both", expand=True)

        for text, field in self.channels:
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(frame, text=text, variable=var)
            cb.pack(anchor="w", padx=20, pady=2)
            self.check_vars[field] = var

        # ===== Кнопка =====
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(fill="x", pady=10)

        ctk.CTkButton(
            bottom_frame,
            text="Загрузить данные",
            command=self.load_data,
            height=40
        ).pack(pady=10)
        self.load_experiments()

    # =========================
    def load_experiments(self):
        with Session(engine) as session:
            exps = session.exec(select(Experiments)).all()

            names = []
            for exp in exps:
                display = f"{exp.id} | {exp.name}"
                names.append(display)
                self.experiments_map[display] = exp.id

            if names:
                self.exp_combo.configure(values=names)
                self.exp_combo.set(names[-1])
                self.update_frame_range()

    # =========================
    def update_frame_range(self):
        selected = self.exp_combo.get()

        if selected not in self.experiments_map:
            return

        exp_id = self.experiments_map[selected]

        with Session(engine) as session:
            statement = select(Measurements.number).where(
                Measurements.experiment_id == exp_id
            ).order_by(Measurements.number.desc()).limit(1)

            max_frame = session.exec(statement).first()

        if max_frame:
            self.frame_from.delete(0, "end")
            self.frame_from.insert(0, "1")

            self.frame_to.delete(0, "end")
            self.frame_to.insert(0, str(max_frame))

    # =========================
    def load_data(self):
        selected = self.exp_combo.get()

        if selected not in self.experiments_map:
            self.parent.add_log("❌ Эксперимент не выбран")
            return

        exp_id = self.experiments_map[selected]

        selected_fields = [f for f, v in self.check_vars.items() if v.get()]

        if not selected_fields:
            self.parent.add_log("❌ Не выбраны каналы")
            return

        # диапазон
        try:
            frame_from = int(self.frame_from.get())
        except:
            frame_from = 1

        try:
            frame_to = int(self.frame_to.get())
        except:
            frame_to = 10**9

        if frame_from > frame_to:
            self.parent.add_log("❌ Неверный диапазон кадров")
            return

        # запрос
        with Session(engine) as session:
            statement = select(Measurements).where(
                Measurements.experiment_id == exp_id,
                Measurements.number >= frame_from,
                Measurements.number <= frame_to
            ).order_by(Measurements.number)

            rows = session.exec(statement).all()

        if not rows:
            self.parent.add_log("❌ Нет данных")
            return

        # заголовки
        headers_map = {field: text for text, field in self.channels}
        headers = [headers_map[f] for f in selected_fields]

        data = [headers]

        for r in rows:
            data.append([getattr(r, f) for f in selected_fields])

        self.parent.headers = headers
        self.parent.sheet.headers(headers)
        self.parent.set_full_data(data)

        self.parent.add_log(f"📥 Загружен эксперимент ID={exp_id} | кадров: {len(rows)}")

        self.destroy()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.download_btn = None

        self.operator_name = "—"
        self.all_data = []
        self.current_page = 0
        self.rows_per_page = 100

        self.title("Система мониторинга")
        self.after(0, self._maximize_window)

        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Верхняя панель
        self.top_panel = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.top_panel.grid(row=0, column=0, sticky="nsew")

        btn_frame = ctk.CTkFrame(self.top_panel, fg_color="transparent")
        btn_frame.pack(side="left", padx=10)

        buttons = [
            # ("Регистрация данных", self.open_registration_setup),
            ("Управление данными", self.open_data_management),
            ("Научно-технический расчет", self.open_calculation_window),
            ("О программе", self.open_about),
        ]

        self.registration_btn = ctk.CTkButton(btn_frame, text="Регистрация данных", width=150, command=self.open_registration_setup).pack(side="left", padx=5, pady=10)

        self.download_btn = ctk.CTkButton(btn_frame, text="Скачать данные эксперимента", 
                                        width=160, command=self.download_last_experiment)
        self.download_btn.pack(side="left", padx=5, pady=10)
        self.download_btn.configure(state="disabled")   # изначально отключена

        for text, cmd in buttons:
            ctk.CTkButton(btn_frame, text=text, width=150, command=cmd).pack(side="left", padx=5, pady=10)

        self.operator_label = ctk.CTkLabel(self.top_panel, text=f"Оператор: {self.operator_name}", 
                                           font=("Arial", 14, "bold"))
        self.operator_label.pack(side="right", padx=20)

        # Область таблицы
        self.table_frame = ctk.CTkFrame(self)
        self.table_frame.grid(row=1, column=0, padx=10, pady=(10, 5), sticky="nsew")

        self.sheet = tksheet.Sheet(
            self.table_frame,
            show_row_index=True,
            font=("Arial", 14, "normal"),
            header_font=("Arial", 16, "bold"),
            theme="dark",
            all_columns_displayed_stretched=True,
        )
        self.sheet.enable_bindings(
            (
                "single_select",  # Разрешить выделение ячеек
                "drag_select",  # Разрешить выделение диапазонов
                "copy",  # Разрешить копирование текста (Ctrl + C)
                "arrowkeys",  # Навигация стрелками
                "column_width_resize",  # Изменение ширины колонок
                "row_height_resize",  # Изменение высоты строк
            )
        )

        self.sheet.pack(expand=True, fill="both", padx=5, pady=5)
        self.sheet.refresh()
        # Панель пагинации
        self.pagination_frame = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        self.pagination_frame.pack(fill="x", pady=(0, 10))

        self.btn_prev = ctk.CTkButton(self.pagination_frame, text="◀ Предыдущая", width=130,
                                      command=self.prev_page, state="disabled")
        self.btn_prev.pack(side="left", padx=10)

        self.page_label = ctk.CTkLabel(self.pagination_frame, text="Страница 1 / 1", font=("Arial", 12))
        self.page_label.pack(side="left", expand=True)

        self.btn_next = ctk.CTkButton(self.pagination_frame, text="Следующая ▶", width=130,
                                      command=self.next_page, state="disabled")
        self.btn_next.pack(side="right", padx=10)

        # Журнал
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=2, column=0, padx=10, pady=(5, 20), sticky="nsew")

        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(log_header, text="Журнал событий", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkButton(log_header, text="Очистить", width=80, height=24,
                      fg_color="gray", hover_color="#666666",
                      command=self.clear_logs).pack(side="right")

        self.log_view = ctk.CTkTextbox(self.log_frame, font=("Courier", 14), height=10)
        self.log_view.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_view.configure(state="disabled")

        self.headers = ["Кадр", "Канал 1", "Канал 2", "Канал 3", "Канал 4", "Канал 5",
                        "Канал 6 Среднее", "Канал 6 Дисперсия", "Канал 19", "Канал 49", "Канал 69 F"]

        self.sheet.headers(self.headers)
        self.sheet.set_all_column_widths()
        self.sheet.redraw()
        self.ask_user_info()

    # ====================== МЕТОДЫ ======================

    def _maximize_window(self):
        """Пытается развернуть окно кроссплатформенно без падения на unsupported state."""
        try:
            self.state("zoomed")
            return
        except Exception:
            pass

        try:
            self.attributes("-zoomed", True)
            return
        except Exception:
            pass

        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.configure(state="normal")
        self.log_view.insert("end", f"[{timestamp}] {message}\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def clear_logs(self):
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    def set_full_data(self, full_data):
        self.all_data = full_data
        self.current_page = 0
        self.show_current_page()

    def auto_fit_columns(self):
        """Автоматически подгоняет ширину всех колонок под содержимое"""
        try:
            self.sheet.set_all_column_widths()   # основной метод tksheet для авто-fit
        except:
            # запасной вариант (ручной расчёт)
            for col in range(self.sheet.get_total_columns()):
                self.sheet.column_width(col, value = "text") 

    def show_current_page(self):
        if not self.all_data:
            return

        total_rows = len(self.all_data) - 1
        total_pages = max(1, (total_rows + self.rows_per_page - 1) // self.rows_per_page)

        start = 1 + self.current_page * self.rows_per_page
        end = start + self.rows_per_page
        page_data = self.all_data[start:end]

        self.sheet.set_sheet_data(page_data)

        self.page_label.configure(text=f"Страница {self.current_page + 1} / {total_pages}")

        self.btn_prev.configure(state="normal" if self.current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")

        # Авторастяжение колонок после загрузки данных
        self.after(10, self.auto_fit_columns)   # небольшая задержка для корректного рендера

        self.sheet.see(row = 0, column = 0)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.show_current_page()

    def next_page(self):
        total_rows = len(self.all_data) - 1
        total_pages = max(1, (total_rows + self.rows_per_page - 1) // self.rows_per_page)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.show_current_page()

    def clear_table(self):
        self.sheet.set_sheet_data([])
        self.all_data = []
        self.current_page = 0
        self.add_log("Таблица очищена")

    def update_operator_info(self):
        self.operator_label.configure(text=f"Оператор: {self.operator_name}")
        self.add_log(f"Оператор {self.operator_name} вошел в систему")

    def open_registration_setup(self):
        RegistrationSetupWindow(self)
        self.add_log("Открыто окно 'Регистрации данных'")

    def open_data_management(self):
        DataManagementWindow(self)
        self.add_log("Открыто окно 'Управление данными'")
    def open_calculation_window(self):
        CalculationWindow(self)
        self.add_log("Открыто окно 'Научно-технический расчёт'")

    def open_about(self):
        AboutWindow(self)
        self.add_log("Открыто окно 'О программе'")

    def ask_user_info(self):
        self.after(200, lambda: LoginWindow(self))

    def download_last_experiment(self):
        """Скачивает данные последнего эксперимента в XLSX"""
        try:
            with Session(engine) as session:
                # Получаем последний эксперимент
                statement = select(Experiments).order_by(Experiments.id.desc()).limit(1)
                last_exp = session.exec(statement).first()

                if not last_exp:
                    self.add_log("❌ Нет сохранённых экспериментов")
                    return

                # Получаем все измерения
                meas_statement = select(Measurements).where(
                    Measurements.experiment_id == last_exp.id
                ).order_by(Measurements.number)
                
                measurements = session.exec(meas_statement).all()

                if not measurements:
                    self.add_log("❌ В эксперименте нет данных")
                    return

            # Подготовка данных для Excel
            data = []
            for m in measurements:
                data.append([
                    m.number,
                    m.channel_1, m.channel_2, m.channel_3, m.channel_4, m.channel_5,
                    m.channel_6_avg, m.channel_6_disp, m.channel_19, m.channel_49,
                    m.channel_69_func
                ])

            df = pd.DataFrame(data, columns=self.headers)

            # Создаём папку data, если её нет
            Path("data").mkdir(exist_ok=True)

            # Формируем имя файла
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in last_exp.name)
            filename = f"{last_exp.id}_{safe_name}_{last_exp.operator}.xlsx"
            filepath = os.path.join("data", filename)

            df.to_excel(filepath, index=False, engine='openpyxl')

            self.add_log(f"✅ Данные сохранены: {filepath}")
            
            # Опционально: открываем папку после сохранения
            # os.startfile(os.path.abspath("data"))  # для Windows

        except Exception as e:
            self.add_log(f"❌ Ошибка при выгрузке: {e}")

    def open_data_management(self):
        DataManagementWindow(self)
