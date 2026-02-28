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

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 文件路径 ---
CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"

# --- 基础 Prompt (骨架) ---
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

# --- 输出格式控制 (Excel 直贴版) ---
FORMAT_PROMPT = """
[输出格式要求 - 极为重要]
1. **严禁**使用 Markdown 表格符号。
2. 请输出**纯文本**。
3. 列与列之间，**必须**使用键盘上的【Tab键】( \\t ) 进行分隔。
4. 每一行数据占一行。

[表头 (Tab分隔)]
时间	界面/位置	❌ 原文	⚠️ 问题类型	🟢 优化方案 (English)	💡 深度解析 (中文)
"""

class VideoLocalizationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gemini 3 视频审计 (旗舰进化版)")
        self.geometry("1400x950")

        self.file_path = None
        self.processing = False
        self.history_data = []
        self.evolution_memory = [] 
        
        # --- 针对您的 API 列表定制的模型选择 ---
        self.model_list = [
            "gemini-3-flash-preview",  # 👑 首选：最新最快，适合视频
            "gemini-3-pro-preview",    # 备选：推理最强，但可能慢
            "gemini-2.5-flash",        # 稳健：2.5 正式版
            "gemini-2.0-flash",        # 经典：2.0 版本
        ]

        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _init_ui(self):
        # === 整体布局 ===
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # --- 左侧：历史记录 ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="🕒 历史记录", font=("微软雅黑", 20, "bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="记录列表")
        self.history_list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        self.btn_delete_history = ctk.CTkButton(self.sidebar_frame, text="🗑️ 删除记录", command=self.delete_current_history, fg_color="#D32F2F")
        self.btn_delete_history.grid(row=3, column=0, padx=20, pady=20)

        # --- 右侧：主操作区 ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        # 1. 顶部配置
        self.config_frame = ctk.CTkFrame(self.main_frame)
        self.config_frame.pack(pady=10, padx=20, fill="x")

        self.api_label = ctk.CTkLabel(self.config_frame, text="API Key:")
        self.api_label.pack(side="left", padx=(10, 5))
        self.api_key_var = tk.StringVar()
        self.api_entry = ctk.CTkEntry(self.config_frame, textvariable=self.api_key_var, show="*", width=300)
        self.api_entry.pack(side="left", padx=5)
        
        # 模型选择器
        self.model_combo = ctk.CTkComboBox(self.config_frame, values=self.model_list, width=220)
        self.model_combo.set("gemini-3-flash-preview") # 默认选中最强
        self.model_combo.pack(side="left", padx=20)

        # 2. 进化中心
        self.evo_frame = ctk.CTkFrame(self.main_frame, fg_color="#1E2736")
        self.evo_frame.pack(pady=5, padx=20, fill="x")
        
        self.lbl_evo = ctk.CTkLabel(self.evo_frame, text="🧬 进化记忆库 (已激活)", font=("微软雅黑", 12, "bold"), text_color="#64B5F6")
        self.lbl_evo.pack(side="left", padx=15, pady=8)
        
        self.lbl_evo_count = ctk.CTkLabel(self.evo_frame, text="当前规则数: 0", text_color="silver")
        self.lbl_evo_count.pack(side="left", padx=5)

        self.btn_add_evo = ctk.CTkButton(self.evo_frame, text="➕ 添加新规则/调教AI", command=self.add_evolution_rule, width=150, fg_color="#1565C0")
        self.btn_add_evo.pack(side="right", padx=15, pady=8)

        # 3. 文件操作
        self.file_frame = ctk.CTkFrame(self.main_frame)
        self.file_frame.pack(pady=10, padx=20, fill="x")
        self.btn_select = ctk.CTkButton(self.file_frame, text="📂 导入视频", command=self.select_file)
        self.btn_select.pack(side="left", padx=10, pady=10)
        self.lbl_filename = ctk.CTkLabel(self.file_frame, text="未选择文件", text_color="gray")
        self.lbl_filename.pack(side="left", padx=10)
        self.btn_run = ctk.CTkButton(self.file_frame, text="🔍 开始进化分析", command=self.start_analysis_thread, fg_color="#2E7D32", state="disabled", font=("微软雅黑", 14, "bold"), width=150)
        self.btn_run.pack(side="right", padx=10)

        # 4. 状态 & 内容
        self.progressbar = ctk.CTkProgressBar(self.main_frame, mode="indeterminate", width=800)
        self.progressbar.pack(pady=5, padx=20, fill="x")
        self.lbl_status = ctk.CTkLabel(self.main_frame, text="准备就绪", text_color="silver")
        self.lbl_status.pack()

        self.current_display_label = ctk.CTkLabel(self.main_frame, text="当前显示: [新任务]", font=("微软雅黑", 14, "bold"), text_color="#4FC3F7")
        self.current_display_label.pack(pady=(10, 0), anchor="w", padx=20)

        self.textbox = ctk.CTkTextbox(self.main_frame, font=("Consolas", 12), activate_scrollbars=True)
        self.textbox.pack(pady=10, padx=20, fill="both", expand=True)
        self.textbox.insert("0.0", "👋 已自动为您选择最强模型：Gemini 3 Flash Preview\n\n🧬【进化功能】：点击上方“➕ 添加新规则”，您可以告诉 AI 之前忽略的问题。\n📋【Excel直贴】：输出已自动调整为 Tab 分隔格式，复制后直接去 Excel 粘贴即可。")

        self.btn_copy = ctk.CTkButton(self.main_frame, text="📋 复制 (Tab格式)", command=self.copy_to_clipboard)
        self.btn_copy.pack(pady=10)

    # --- 🧠 进化核心逻辑 ---
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
        self.lbl_evo_count.configure(text=f"当前已积累规则: {count} 条")

    def add_evolution_rule(self):
        rule = simpledialog.askstring("调教 AI", "请输入您希望 AI 下次注意的规则：")
        if rule:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            self.evolution_memory.append({"date": timestamp, "rule": rule})
            self._save_evolution_db()
            messagebox.showinfo("成功", "✅ 规则已植入！下次生效。")

    def construct_dynamic_prompt(self):
        if not self.evolution_memory:
            memory_text = ""
        else:
            rules_str = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
            memory_text = f"\n[🔥🔥 特别关注/历史经验库]\n用户强调必须遵守：\n{rules_str}\n"
        return BASE_PROMPT + memory_text + FORMAT_PROMPT

    # --- 基础功能 ---
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

    def _refresh_history_list(self):
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
        for index, item in enumerate(reversed(self.history_data)):
            real_index = len(self.history_data) - 1 - index
            btn = ctk.CTkButton(
                self.history_list_frame, 
                text=f"{item['title']}\n{item['date']}", 
                fg_color="transparent", 
                border_width=1, 
                border_color="#444", 
                anchor="w",
                command=lambda idx=real_index: self.load_history_content(idx)
            )
            btn.pack(pady=2, padx=5, fill="x")
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
            self.current_display_label.configure(text=f"当前显示: {entry['title']}")
            self.current_active_index = index

    def rename_history(self, index):
        new_title = simpledialog.askstring("重命名", "新标题:", initialvalue=self.history_data[index]["title"])
        if new_title:
            self.history_data[index]["title"] = new_title
            self._save_history_db()
            self._refresh_history_list()
            if hasattr(self, 'current_active_index') and self.current_active_index == index:
                self.current_display_label.configure(text=f"当前显示: {new_title}")

    def delete_current_history(self):
        if hasattr(self, 'current_active_index'):
            if messagebox.askyesno("确认", "删除此记录？"):
                del self.history_data[self.current_active_index]
                self._save_history_db()
                self._refresh_history_list()
                self.textbox.delete("0.0", "end")
                self.current_display_label.configure(text="当前显示: [无]")
                del self.current_active_index

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mov *.avi *.webm *.mkv")])
        if file_path:
            self.file_path = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path), text_color="white")
            self.btn_run.configure(state="normal")
            self.update_status(f"已加载: {os.path.basename(file_path)}")

    def update_status(self, text, is_error=False):
        color = "#FF5252" if is_error else "#E0E0E0"
        self.lbl_status.configure(text=text, text_color=color)

    def start_analysis_thread(self):
        api_key = self.api_key_var.get().strip()
        if not api_key or not self.file_path: return
        self._save_config()
        self.processing = True
        self.btn_run.configure(state="disabled", text="进化分析中...")
        self.textbox.delete("0.0", "end")
        self.progressbar.start()
        threading.Thread(target=self.run_logic, args=(api_key, self.file_path, self.model_combo.get()), daemon=True).start()

    def run_logic(self, api_key, file_path, model_name):
        try:
            genai.configure(api_key=api_key)
            self.update_status("⬆️ 上传视频...")
            video_file = genai.upload_file(path=file_path)
            
            self.update_status("⏳ 等待处理...")
            start_time = time.time()
            while video_file.state.name == "PROCESSING":
                if time.time() - start_time > 600: raise TimeoutError("超时")
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED": raise ValueError("视频处理失败")

            self.update_status(f"🧬 [{model_name}] 正在分析...")
            final_prompt = self.construct_dynamic_prompt()
            
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([final_prompt, video_file])
            
            self.after(0, lambda: self.add_new_history(response.text, os.path.basename(file_path)))
            self.update_status("✅ 完成！")
        except Exception as e:
            self.update_status(f"❌ 错误: {str(e)}", is_error=True)
            self.textbox.insert("0.0", str(e))
        finally:
            if 'video_file' in locals(): 
                try: genai.delete_file(video_file.name)
                except: pass
            self.processing = False
            self.progressbar.stop()
            self.btn_run.configure(state="normal", text="🔍 开始进化分析")

    def copy_to_clipboard(self):
        pyperclip.copy(self.textbox.get("0.0", "end"))
        self.update_status("📋 已复制！")

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()