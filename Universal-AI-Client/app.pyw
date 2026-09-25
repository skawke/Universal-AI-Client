import json
import os
import threading
import time
import tkinter as tk
import customtkinter as ctk
from openai import OpenAI

# Настройки оформления
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"
CHATS_FILE = "chats.json"

# Пресеты провайдеров
PRESETS = {
    "TokenClub": {
        "url": "https://tooken.club/v1",
        "default_model": "gpt-4o-mini"
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3-8b-instruct"
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini"
    },
    "ProxyAPI": {
        "url": "https://api.proxyapi.ru/openai/v1",
        "default_model": "gpt-4o-mini"
    },
    "Свой провайдер": {
        "url": "",
        "default_model": ""
    }
}


def setup_clipboard_and_hotkeys(widget, root):
    """Горячие клавиши (Ctrl+C/V/X/A) для любой раскладки и меню по ПКМ"""
    inner = getattr(widget, "_entry", getattr(widget, "_textbox", widget))
    is_text = isinstance(inner, tk.Text) or hasattr(inner, "tag_add")

    def copy_action(event=None):
        try:
            if is_text:
                text = inner.get("sel.first", "sel.last")
            else:
                text = inner.selection_get()
            if text:
                root.clipboard_clear()
                root.clipboard_append(text)
        except Exception:
            pass
        return "break"

    def paste_action(event=None):
        if str(inner.cget("state")) != "disabled":
            try:
                text = root.clipboard_get()
                if text:
                    try:
                        inner.delete("sel.first", "sel.last")
                    except Exception:
                        pass
                    inner.insert("insert", text)
            except Exception:
                pass
        return "break"

    def cut_action(event=None):
        if str(inner.cget("state")) != "disabled":
            try:
                if is_text:
                    text = inner.get("sel.first", "sel.last")
                    inner.delete("sel.first", "sel.last")
                else:
                    text = inner.selection_get()
                    inner.delete("sel.first", "sel.last")
                if text:
                    root.clipboard_clear()
                    root.clipboard_append(text)
            except Exception:
                pass
        return "break"

    def select_all_action(event=None):
        if is_text:
            inner.tag_add("sel", "1.0", "end")
        else:
            inner.select_range(0, "end")
            inner.icursor("end")
        return "break"

    def on_ctrl_key(event):
        code = event.keycode
        sym = event.keysym.lower()

        if code == 65 or sym in ("a", "cyrillic_ef"):
            return select_all_action()
        elif code == 67 or sym in ("c", "cyrillic_es"):
            return copy_action()
        elif code == 86 or sym in ("v", "cyrillic_em"):
            return paste_action()
        elif code == 88 or sym in ("x", "cyrillic_che"):
            return cut_action()

    inner.bind("<Control-KeyPress>", on_ctrl_key)

    menu = tk.Menu(inner, tearoff=0)
    menu.add_command(label="Копировать", command=copy_action)
    menu.add_command(label="Вставить", command=paste_action)
    menu.add_command(label="Вырезать", command=cut_action)
    menu.add_command(label="Выделить всё", command=select_all_action)

    inner.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))


class AIChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Universal AI Client")
        self.geometry("980x680")
        self.minsize(850, 550)

        self.chats = []
        self.current_chat_id = None
        self.is_generating = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_area()
        self._setup_all_hotkeys()

        self._load_config()
        self._load_chats()

        # Автосохранение при закрытии крестиком
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_propagate(False)

        # Вкладки: Чаты и Настройки
        self.tabview = ctk.CTkTabview(self.sidebar)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_chats = self.tabview.add("Чаты")
        self.tab_settings = self.tabview.add("Настройки")

        self._build_tab_chats()
        self._build_tab_settings()

    def _build_tab_chats(self):
        self.btn_new_chat = ctk.CTkButton(
            self.tab_chats, 
            text="+ Новый чат", 
            height=36,
            command=self._create_new_chat
        )
        self.btn_new_chat.pack(fill="x", padx=5, pady=(5, 10))

        self.chats_scroll = ctk.CTkScrollableFrame(self.tab_chats, fg_color="transparent")
        self.chats_scroll.pack(fill="both", expand=True, padx=0, pady=0)

    def _build_tab_settings(self):
        ctk.CTkLabel(self.tab_settings, text="Провайдер:").pack(padx=5, pady=(5, 2), anchor="w")
        self.preset_menu = ctk.CTkOptionMenu(
            self.tab_settings,
            values=list(PRESETS.keys()),
            command=self._on_preset_change
        )
        self.preset_menu.pack(padx=5, pady=(0, 8), fill="x")

        ctk.CTkLabel(self.tab_settings, text="Base URL:").pack(padx=5, pady=(5, 2), anchor="w")
        self.entry_url = ctk.CTkEntry(self.tab_settings, placeholder_text="https://tooken.club/v1")
        self.entry_url.pack(padx=5, pady=(0, 8), fill="x")

        ctk.CTkLabel(self.tab_settings, text="API Key:").pack(padx=5, pady=(5, 2), anchor="w")
        key_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        key_frame.pack(padx=5, pady=(0, 8), fill="x")

        self.entry_key = ctk.CTkEntry(key_frame, placeholder_text="sk-...", show="•")
        self.entry_key.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_paste_key = ctk.CTkButton(
            key_frame,
            text="Вставить",
            width=70,
            command=self._paste_api_key
        )
        self.btn_paste_key.pack(side="right")

        ctk.CTkLabel(self.tab_settings, text="Модель:").pack(padx=5, pady=(5, 2), anchor="w")
        self.entry_model = ctk.CTkEntry(self.tab_settings, placeholder_text="gpt-4o-mini")
        self.entry_model.pack(padx=5, pady=(0, 8), fill="x")

        ctk.CTkLabel(self.tab_settings, text="Системный промпт:").pack(padx=5, pady=(5, 2), anchor="w")
        self.entry_system = ctk.CTkTextbox(self.tab_settings, height=75)
        self.entry_system.insert("0.0", "Отвечай чётко и по делу.")
        self.entry_system.pack(padx=5, pady=(0, 10), fill="x")

        self.btn_save = ctk.CTkButton(self.tab_settings, text="Сохранить настройки", command=self._save_config)
        self.btn_save.pack(padx=5, pady=(0, 10), fill="x")

    def _build_chat_area(self):
        self.chat_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.chat_frame.grid_columnconfigure(0, weight=1)
        self.chat_frame.grid_rowconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(self.chat_frame, wrap="word", font=ctk.CTkFont(size=14))
        self.chat_box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        self.chat_box.configure(state="disabled")

        self.input_field = ctk.CTkEntry(
            self.chat_frame, 
            placeholder_text="Напиши сообщение... (Enter — отправить)",
            height=42
        )
        self.input_field.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.input_field.bind("<Return>", lambda event: self.send_message())

        self.btn_send = ctk.CTkButton(
            self.chat_frame, 
            text="Отправить", 
            width=100, 
            height=42, 
            command=self.send_message
        )
        self.btn_send.grid(row=1, column=1)

    def _setup_all_hotkeys(self):
        widgets = [
            self.entry_url, 
            self.entry_key, 
            self.entry_model, 
            self.entry_system, 
            self.input_field,
            self.chat_box
        ]
        for w in widgets:
            setup_clipboard_and_hotkeys(w, self)

    def _paste_api_key(self):
        try:
            text = self.clipboard_get().strip()
            self.entry_key.delete(0, "end")
            self.entry_key.insert(0, text)
        except Exception:
            pass

    def _on_preset_change(self, preset_name):
        preset = PRESETS.get(preset_name)
        if preset and preset_name != "Свой провайдер":
            self.entry_url.delete(0, "end")
            self.entry_url.insert(0, preset["url"])
            self.entry_model.delete(0, "end")
            self.entry_model.insert(0, preset["default_model"])

    def _get_current_chat(self):
        for c in self.chats:
            if c["id"] == self.current_chat_id:
                return c
        return None

    def _render_chat_messages(self):
        self.chat_box.configure(state="normal")
        self.chat_box.delete("0.0", "end")
        chat = self._get_current_chat()
        if chat:
            for m in chat.get("messages", []):
                role = "Ты" if m["role"] == "user" else "Бот"
                self.chat_box.insert("end", f"{role}: {m['content']}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _render_chats_list(self):
        for child in self.chats_scroll.winfo_children():
            child.destroy()

        for c in reversed(self.chats):
            is_active = (c["id"] == self.current_chat_id)
            row = ctk.CTkFrame(
                self.chats_scroll, 
                fg_color="#1F538D" if is_active else "#2B2B2B",
                corner_radius=6
            )
            row.pack(fill="x", pady=3, padx=2)

            title_text = c.get("title", "Диалог")
            if len(title_text) > 20:
                title_text = title_text[:17] + "..."

            btn_title = ctk.CTkButton(
                row,
                text=title_text,
                fg_color="transparent",
                hover_color="#14375E" if is_active else "#3A3A3A",
                anchor="w",
                command=lambda cid=c["id"]: self._switch_chat(cid)
            )
            btn_title.pack(side="left", fill="x", expand=True, padx=(5, 0))

            btn_del = ctk.CTkButton(
                row,
                text="✕",
                width=28,
                fg_color="transparent",
                hover_color="#C62828",
                text_color="#FF6B6B",
                command=lambda cid=c["id"]: self._delete_chat(cid)
            )
            btn_del.pack(side="right", padx=(0, 2))

    def _switch_chat(self, chat_id):
        if self.is_generating:
            return
        self.current_chat_id = chat_id
        self._render_chats_list()
        self._render_chat_messages()
        self._save_chats()

    def _create_new_chat(self):
        if self.is_generating:
            return
        new_id = str(int(time.time() * 1000))
        new_chat = {
            "id": new_id,
            "title": "Новый чат",
            "messages": []
        }
        self.chats.append(new_chat)
        self.current_chat_id = new_id
        self._render_chats_list()
        self._render_chat_messages()
        self._save_chats()

    def _delete_chat(self, chat_id):
        if self.is_generating:
            return
        self.chats = [c for c in self.chats if c["id"] != chat_id]
        if not self.chats:
            self._create_new_chat()
        else:
            if self.current_chat_id == chat_id:
                self.current_chat_id = self.chats[-1]["id"]
            self._render_chats_list()
            self._render_chat_messages()
            self._save_chats()

    def _append_text(self, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", text)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def send_message(self):
        if self.is_generating:
            return

        user_text = self.input_field.get().strip()
        if not user_text:
            return

        api_key = self.entry_key.get().strip()
        base_url = self.entry_url.get().strip()
        model = self.entry_model.get().strip()

        if not api_key:
            self._append_text("\n[Ошибка]: Введи API ключ в настройках!\n")
            return
        if not base_url:
            self._append_text("\n[Ошибка]: Укажи Base URL провайдера!\n")
            return
        if not model:
            self._append_text("\n[Ошибка]: Укажи название модели!\n")
            return

        # Автосохранение настроек при отправке
        self._save_config()

        chat = self._get_current_chat()
        if not chat:
            self._create_new_chat()
            chat = self._get_current_chat()

        if chat["title"] == "Новый чат":
            chat["title"] = user_text[:22]
            self._render_chats_list()

        self.input_field.delete(0, "end")
        self._append_text(f"Ты: {user_text}\n\nБот: ")

        chat["messages"].append({"role": "user", "content": user_text})
        self._save_chats()

        self.is_generating = True
        self.btn_send.configure(state="disabled")

        threading.Thread(
            target=self._stream_response, 
            args=(base_url, api_key, model, chat["id"]), 
            daemon=True
        ).start()

    def _stream_response(self, base_url, api_key, model, chat_id):
        try:
            client = OpenAI(base_url=base_url, api_key=api_key)

            system_prompt = self.entry_system.get("0.0", "end").strip()
            chat = self._get_current_chat()
            
            payload_messages = []
            if system_prompt:
                payload_messages.append({"role": "system", "content": system_prompt})
            if chat:
                payload_messages.extend(chat.get("messages", []))

            response = client.chat.completions.create(
                model=model,
                messages=payload_messages,
                stream=True
            )

            assistant_reply = ""
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    assistant_reply += delta
                    if self.current_chat_id == chat_id:
                        self.after(0, self._append_text, delta)

            # Сохраняем ответ в историю чата
            for c in self.chats:
                if c["id"] == chat_id:
                    c["messages"].append({"role": "assistant", "content": assistant_reply})
                    break

            if self.current_chat_id == chat_id:
                self.after(0, self._append_text, "\n\n")

            self._save_chats()

        except Exception as e:
            if self.current_chat_id == chat_id:
                self.after(0, self._append_text, f"\n[Ошибка запроса]: {str(e)}\n\n")

        finally:
            self.is_generating = False
            self.after(0, lambda: self.btn_send.configure(state="normal"))

    def _save_config(self):
        data = {
            "preset": self.preset_menu.get(),
            "url": self.entry_url.get().strip(),
            "key": self.entry_key.get().strip(),
            "model": self.entry_model.get().strip(),
            "system": self.entry_system.get("0.0", "end").strip()
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self._on_preset_change("TokenClub")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "preset" in data and data["preset"] in PRESETS:
                self.preset_menu.set(data["preset"])
            if "url" in data:
                self.entry_url.delete(0, "end")
                self.entry_url.insert(0, data["url"])
            if "key" in data:
                self.entry_key.delete(0, "end")
                self.entry_key.insert(0, data["key"])
            if "model" in data:
                self.entry_model.delete(0, "end")
                self.entry_model.insert(0, data["model"])
            if "system" in data:
                self.entry_system.delete("0.0", "end")
                self.entry_system.insert("0.0", data["system"])
        except Exception:
            pass

    def _save_chats(self):
        data = {
            "active_chat_id": self.current_chat_id,
            "chats": self.chats
        }
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_chats(self):
        if not os.path.exists(CHATS_FILE):
            self._create_new_chat()
            return

        try:
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.chats = data.get("chats", [])
            self.current_chat_id = data.get("active_chat_id")

            if not self.chats:
                self._create_new_chat()
            else:
                if not any(c["id"] == self.current_chat_id for c in self.chats):
                    self.current_chat_id = self.chats[-1]["id"]
                self._render_chats_list()
                self._render_chat_messages()
        except Exception:
            self._create_new_chat()

    def _on_close(self):
        self._save_config()
        self._save_chats()
        self.destroy()


if __name__ == "__main__":
    app = AIChatApp()
    app.mainloop()
