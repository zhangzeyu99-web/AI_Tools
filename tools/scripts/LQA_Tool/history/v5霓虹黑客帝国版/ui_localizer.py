import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import google.generativeai as genai
import os
import time
import threading
import pyperclip
import json
from datetime import datetime

# 忽略 Google 的弃用警告，保持界面清爽
import warnings
warnings.filterwarnings("ignore")

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- 文件路径 ---
CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"

# --- 核心 Prompt ---
BASE_PROMPT = """
[角色设定]
你是一位拥有15年经验的资深游戏/应用本地化总监 (Localization Director)。

[任务目标]
对视频进行全量、逐帧的**深度审计(Audit)**。
目标用户是**中文开发者**，你需要用**中文**清晰地解释英文文案中的错误。

[核心审计维度]
1. 拼写错误 (Spelling)
2. 中式英语 (Chinglish)
3. 语气不当 (Tone/Register)
4. UI 截断/溢出 (UI Layout)
5. 冗余表达 (Redundancy)
"""

FORMAT_PROMPT = """
[输出格式要求]
1. **严禁**使用 Markdown 表格符号。
2. 请输出**纯文本**。
3. 列与列之间，**必须**使用键盘上的【Tab键】( \\t ) 进行分隔。
4. 每一行数据占一行。

[表头 (Tab分隔)]
时间	界面/位置	❌ 原文	⚠️ 问题类型	🟢 优化方案 (English)	💡 深度解析 (中文)
"""

class CyberpunkButton(ctk.CTkButton):
    """自定义赛博风格按钮"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(corner_radius=4, border_width=1, font=("Microsoft YaHei UI", 12, "bold"))

class VideoLocalizationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- 🎨 赛博朋克配色 (内嵌版，防止丢失) ---
        self.colors = {
            "bg": "#0B0F19",         # 深空黑背景
            "sidebar": "#111625",    # 侧边栏
            "card": "#1A2236",       # 卡片背景
            "accent": "#00F0FF",     # 赛博青 (主操作)
            "evo": "#BC13FE",        # 电光紫 (进化核心)
            "text": "#E0E6ED",       # 冰银色文本
            "danger": "#FF2A6D",     # 故障红
            "input_bg": "#0F131F"    # 输入框背景
        }

        self.title("GEMINI 3 // AUDIT PROTOCOL [v8.1 Stable]")
        self.geometry("1450x950")
        self.configure(fg_color=self.colors["bg"]) 

        self.file_path = None
        self.processing = False
        self.history_data = []
        self.evolution_memory = []
        
        # 模型列表
        self.model_list = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.0-flash"]

        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _init_ui(self):
        # === 布局框架 ===
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------
        # 1. 左侧：数据档案库
        # ---------------------------------------------------------
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=self.colors["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(3, weight=1)

        # Logo / Title
        self.lbl_logo = ctk.CTkLabel(self.sidebar, text="PROJECT\nGEMINI", font=("Impact", 32), text_color=self.colors["accent"])
        self.lbl_logo.grid(row=0, column=0, padx=20, pady=(30, 10), sticky="w")
        
        self.lbl_ver = ctk.CTkLabel(self.sidebar, text="SYSTEM STATUS: ONLINE", font=("Consolas", 10), text_color="#00FF99")
        self.lbl_ver.grid(row=1, column=0, padx=24, pady=(0, 20), sticky="w")

        self.lbl_hist_title = ctk.CTkLabel(self.sidebar, text="[ ARCHIVES / 历史档案 ]", font=("Consolas", 12, "bold"), text_color="gray")
        self.lbl_hist_title.grid(row=2, column=0, padx=20, pady=(10,5), sticky="w")

        # 历史列表
        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", label_text="")
        self.history_list_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        # 删除按钮 (这里之前报错，现在修复了)
        self.btn_del = CyberpunkButton(self.sidebar, text="PURGE DATA / 删除记录", command=self.delete_current_history, 
                                       fg_color="transparent", 
                                       border_color=self.colors["danger"], 
                                       text_color=self.colors["danger"], 
                                       hover_color="#2A0F15")
        self.btn_del.grid(row=4, column=0, padx=20, pady=20, sticky="ew")


        # ---------------------------------------------------------
        # 2. 右侧：主指挥中心
        # ---------------------------------------------------------
        self.main_area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        
        # --- A. 顶部 HUD ---
        self.top_bar = ctk.CTkFrame(self.main_area, fg_color=self.colors["card"], height=60, corner_radius=0)
        self.top_bar.pack(fill="x", padx=0, pady=0)
        
        # API Key
        self.lbl_key = ctk.CTkLabel(self.top_bar, text="ACCESS KEY:", font=("Consolas", 12, "bold"), text_color=self.colors["accent"])
        self.lbl_key.pack(side="left", padx=(20, 10))
        
        self.api_key_var = tk.StringVar()
        self.api_entry = ctk.CTkEntry(self.top_bar, textvariable=self.api_key_var, show="•", width=280, 
                                      fg_color=self.colors["input_bg"], border_color="#333", text_color="white", font=("Consolas", 12))
        self.api_entry.pack(side="left")

        # 模型选择
        self.model_combo = ctk.CTkComboBox(self.top_bar, values=self.model_list, width=220, 
                                           fg_color=self.colors["input_bg"], border_color=self.colors["accent"], 
                                           text_color="white", dropdown_fg_color=self.colors["sidebar"])
        self.model_combo.set("gemini-3-flash-preview")
        self.model_combo.pack(side="right", padx=20)
        self.lbl_model = ctk.CTkLabel(self.top_bar, text="NEURAL ENGINE:", font=("Consolas", 12, "bold"), text_color=self.colors["accent"])
        self.lbl_model.pack(side="right", padx=5)

        # --- B. 进化核心 ---
        self.evo_container = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.evo_container.pack(fill="x", padx=20, pady=20)

        self.evo_frame = ctk.CTkFrame(self.evo_container, fg_color="#180526", border_color=self.colors["evo"], border_width=2, corner_radius=8)
        self.evo_frame.pack(fill="x", ipady=5)

        self.lbl_evo_icon = ctk.CTkLabel(self.evo_frame, text="🧬", font=("Segoe UI Emoji", 28))
        self.lbl_evo_icon.pack(side="left", padx=(20, 10))

        self.lbl_evo_title = ctk.CTkLabel(self.evo_frame, text="EVOLUTION CORE / 进化记忆矩阵", font=("Microsoft YaHei UI", 16, "bold"), text_color="white")
        self.lbl_evo_title.pack(side="left", pady=5)
        
        self.lbl_evo_count = ctk.CTkLabel(self.evo_frame, text="ACTIVE NODES: 0", font=("Consolas", 12), text_color=self.colors["evo"])
        self.lbl_evo_count.pack(side="left", padx=15, pady=(8,0))

        self.btn_add_evo = CyberpunkButton(self.evo_frame, text="+ INJECT KNOWLEDGE / 注入新规则", command=self.add_evolution_rule, 
                                           fg_color=self.colors["evo"], hover_color="#9900CC", text_color="white")
        self.btn_add_evo.pack(side="right", padx=20, pady=10)

        # --- C. 操作区 ---
        self.ctrl_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.ctrl_frame.pack(fill="x", padx=20)

        self.btn_select = CyberpunkButton(self.ctrl_frame, text="📂 LOAD VIDEO SOURCE", command=self.select_file,
                                          fg_color="transparent", border_color="#555", text_color="#AAA", width=200)
        self.btn_select.pack(side="left")
        
        self.lbl_filename = ctk.CTkLabel(self.ctrl_frame, text="NO SOURCE DETECTED", font=("Consolas", 12), text_color="#555")
        self.lbl_filename.pack(side="left", padx=15)

        self.btn_run = CyberpunkButton(self.ctrl_frame, text="INITIATE SCAN / 开始审计", command=self.start_analysis_thread, 
                                       fg_color=self.colors["accent"], text_color="black", hover_color="#00C4D6", width=200, height=35)
        self.btn_run.pack(side="right")

        # --- D. 状态条 ---
        self.progressbar = ctk.CTkProgressBar(self.main_area, mode="indeterminate", width=800, progress_color=self.colors["accent"])
        self.progressbar.pack(pady=(20, 5), padx=20, fill="x")
        self.progressbar.set(0)
        
        self.lbl_status = ctk.CTkLabel(self.main_area, text="SYSTEM IDLE", text_color="#555", font=("Consolas", 11))
        self.lbl_status.pack()

        # --- E. 终端显示区 ---
        self.current_display_label = ctk.CTkLabel(self.main_area, text="> OUTPUT TERMINAL", font=("Consolas", 14, "bold"), text_color=self.colors["accent"])
        self.current_display_label.pack(pady=(10, 5), anchor="w", padx=25)

        self.textbox = ctk.CTkTextbox(self.main_area, 
                                      font=("Consolas", 12), 
                                      fg_color="#080a0f", 
                                      text_color="#00FF99", 
                                      border_color="#333", 
                                      border_width=1,
                                      activate_scrollbars=True)
        self.textbox.pack(pady=5, padx=20, fill="both", expand=True)
        
        welcome_msg = """
        [SYSTEM] INITIALIZING GEMINI INTERFACE...
        [SYSTEM] LOADING MODULES...
        [SUCCESS] EVOLUTION CORE: ACTIVE
        [SUCCESS] EXCEL EXPORTER: READY (Tab-Delimited Mode)
        
        > WAITING FOR INPUT...
        """
        self.textbox.insert("0.0", welcome_msg)

        # 底部复制
        self.btn_copy = CyberpunkButton(self.main_area, text="COPY TO CLIPBOARD [CTRL+C]", command=self.copy_to_clipboard, 
                                        fg_color="transparent", border_color=self.colors["accent"], text_color=self.colors["accent"], hover_color="#003333")
        self.btn_copy.pack(pady=15)

    # --- 逻辑功能 ---
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.api_key_var.set(config.get("api_key", ""))
            except: pass

    def _save_config(self):
        current_key = self.api_key_var.get().strip()
        if current_key:
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump({"api_key": current_key}, f)
            except: pass

    def _load_history_db(self):
        if os.path.exists(HISTORY_DB_FILE):
            try:
                with open(HISTORY_DB_FILE, "r", encoding="utf-8") as f:
                    self.history_data = json.load(f)
                    self._refresh_history_list()
            except: pass

    def _save_history_db(self):
        try:
            with open(HISTORY_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except: pass

    def _load_evolution_db(self):
        if os.path.exists(EVOLUTION_DB_FILE):
            try:
                with open(EVOLUTION_DB_FILE, "r", encoding="utf-8") as f:
                    self.evolution_memory = json.load(f)
            except: self.evolution_memory = []
        self.update_evo_ui()

    def _save_evolution_db(self):
        try:
            with open(EVOLUTION_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.evolution_memory, f, ensure_ascii=False, indent=2)
        except: pass
        self.update_evo_ui()

    def update_evo_ui(self):
        count = len(self.evolution_memory)
        self.lbl_evo_count.configure(text=f"ACTIVE NODES: {count}")

    def _refresh_history_list(self):
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
        for index, item in enumerate(reversed(self.history_data)):
            real_index = len(self.history_data) - 1 - index
            btn = ctk.CTkButton(
                self.history_list_frame, 
                text=f"> {item['title']}\n  {item['date']}", 
                fg_color=self.colors["card"], 
                hover_color="#232E4D",
                text_color="#AAA",
                anchor="w",
                font=("Consolas", 11),
                height=45,
                command=lambda idx=real_index: self.load_history_content(idx)
            )
            btn.pack(pady=2, padx=0, fill="x")
            btn.bind("<Double-Button-1>", lambda event, idx=real_index: self.rename_history(idx))

    def add_new_history(self, content, video_name):
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        self.history_data.append({"title": video_name, "date": timestamp, "content": content})
        self._save_history_db()
        self._refresh_history_list()
        self.load_history_content(len(self.history_data) - 1)

    def load_history_content(self, index):
        if 0 <= index < len(self.history_data):
            entry = self.history_data[index]
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", entry["content"])
            self.current_display_label.configure(text=f"> TARGET: {entry['title']}")
            self.current_active_index = index

    def rename_history(self, index):
        new_title = simpledialog.askstring("RENAME PROTOCOL", "New Target Name:", initialvalue=self.history_data[index]["title"])
        if new_title:
            self.history_data[index]["title"] = new_title
            self._save_history_db()
            self._refresh_history_list()
            if hasattr(self, 'current_active_index') and self.current_active_index == index:
                self.current_display_label.configure(text=f"> TARGET: {new_title}")

    def delete_current_history(self):
        if hasattr(self, 'current_active_index'):
            if messagebox.askyesno("WARNING", "CONFIRM DELETION?\n此操作不可逆。"):
                del self.history_data[self.current_active_index]
                self._save_history_db()
                self._refresh_history_list()
                self.textbox.delete("0.0", "end")
                self.current_display_label.configure(text="> NO TARGET")
                del self.current_active_index

    def add_evolution_rule(self):
        rule = simpledialog.askstring("NEURAL LINK", "Input New Rule / 输入新规则:")
        if rule:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            self.evolution_memory.append({"date": timestamp, "rule": rule})
            self._save_evolution_db()
            messagebox.showinfo("UPLOAD COMPLETE", "Rule integrated into Neural Net.")

    def construct_dynamic_prompt(self):
        if not self.evolution_memory:
            memory_text = ""
        else:
            rules_str = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
            memory_text = f"\n[🔥🔥 CRITICAL MEMORY BANK / 重点关注]\n{rules_str}\n"
        return BASE_PROMPT + memory_text + FORMAT_PROMPT

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mov *.avi *.webm *.mkv")])
        if file_path:
            self.file_path = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path)[:25] + "...", text_color=self.colors["accent"])
            self.btn_run.configure(state="normal")
            self.update_status(f"SOURCE LOCKED: {os.path.basename(file_path)}")

    def update_status(self, text, is_error=False):
        color = self.colors["danger"] if is_error else self.colors["accent"]
        self.lbl_status.configure(text=text, text_color=color)

    def start_analysis_thread(self):
        api_key = self.api_key_var.get().strip()
        if not api_key or not self.file_path: return
        self._save_config()
        self.processing = True
        self.btn_run.configure(state="disabled", text="SCANNING...")
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", "> ESTABLISHING LINK...\n> UPLOADING DATA STREAM...\n")
        self.progressbar.start()
        threading.Thread(target=self.run_logic, args=(api_key, self.file_path, self.model_combo.get()), daemon=True).start()

    def run_logic(self, api_key, file_path, model_name):
        try:
            genai.configure(api_key=api_key)
            self.update_status(">> UPLOADING SOURCE FILE...")
            video_file = genai.upload_file(path=file_path)
            
            self.update_status(">> PROCESSING VIDEO DATA...")
            start_time = time.time()
            while video_file.state.name == "PROCESSING":
                if time.time() - start_time > 600: raise TimeoutError("TIMEOUT")
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED": raise ValueError("UPLOAD FAILED")

            self.update_status(f">> GEMINI 3 AGENT ACTIVE [{model_name}]...")
            final_prompt = self.construct_dynamic_prompt()
            
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([final_prompt, video_file])
            
            self.after(0, lambda: self.add_new_history(response.text, os.path.basename(file_path)))
            self.update_status(">> MISSION COMPLETE")
        except Exception as e:
            self.update_status(f"!! SYSTEM ERROR: {str(e)}", is_error=True)
            self.textbox.insert("end", f"\n[ERROR] {str(e)}")
        finally:
            if 'video_file' in locals(): 
                try: genai.delete_file(video_file.name)
                except: pass
            self.processing = False
            self.progressbar.stop()
            self.btn_run.configure(state="normal", text="INITIATE SCAN")

    def copy_to_clipboard(self):
        pyperclip.copy(self.textbox.get("0.0", "end"))
        self.update_status(">> DATA COPIED TO CLIPBOARD")

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()