import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import os
import threading
import time
from datetime import datetime
import urllib.request 

# === 依赖库导入 ===
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from openai import OpenAI
except ImportError as e:
    messagebox.showerror("缺少依赖", f"请先运行: pip install --upgrade openai selenium\n错误详情: {e}")
    exit()

SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"
TARGET_URL = "http://i.4399om.com/todo/list" 

# 默认配置
DEFAULT_PROMPT_TEMPLATE = """你是一个专业的互联网大厂员工。请根据我提供的关键词：
{keywords}

请按以下严格格式生成今日工作日报：

1. [TOP5]部分：
   - 根据关键词扩展出 3-5 条重要的工作产出或进展。
   - 语气要专业、简洁。
   - 纯文本，不要带序号。

2. [总结]部分：
   - 对今日工作进行高度概括，50字以内。

3. [TODO]部分：
   - ⚠️ 重点：请从关键词中发散，随机生成 2-4 条具体的待办/跟进事项。
   - 事项内容要具体，比如“跟进xxx问题”、“完成xxx文档”、“复盘xxx数据”。
   - 纯文本，每行一条，不要带序号。

4. 格式分隔线（非常重要，不要改动）：
   请用 "@@@" 符号将这三部分隔开，顺序必须是：
   TOP5内容@@@总结内容@@@TODO内容
"""

KEYWORD_PLACEHOLDER = """请填写今日工作关键词，建议包含：
1. 您的职位 (如: 测试工程师)
2. 负责的项目 (如: 冒险岛V2.0)
3. 核心产出 (如: 修复登录Bug, 完成性能测试)
4. 特殊事项 (如: 下午组内周会)"""

# === 颜色定义 (Dark Mode) ===
COLOR_BG_MAIN = "#2b2b2b"      
COLOR_BG_PANEL = "#1e1e1e"     
COLOR_FG_TEXT = "#e0e0e0"      
COLOR_FG_SUB = "#aaaaaa"       
COLOR_INPUT_BG = "#3c3f41"     
COLOR_INPUT_FG = "#ffffff"     
COLOR_ACCENT = "#007acc"       
COLOR_ACCENT_HOVER = "#005f9e" 
COLOR_BORDER = "#444444"       

class TodoApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"自动日报助手 (v20.1 完美修正版)")
        self.root.geometry("1000x900")
        self.root.configure(bg=COLOR_BG_MAIN)
        
        # 存储不同模型的配置
        self.api_configs = {
            "DeepSeek (国内直连)": {"key": "", "url": "https://api.deepseek.com"},
            "Google Gemini (需代理)": {"key": "", "url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
            "自定义": {"key": "", "url": ""}
        }

        # === 样式配置 ===
        style = ttk.Style()
        style.theme_use('clam') 
        
        style.configure(".", background=COLOR_BG_MAIN, foreground=COLOR_FG_TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("TLabel", background=COLOR_BG_MAIN, foreground=COLOR_FG_TEXT)
        style.configure("Panel.TLabel", background=COLOR_BG_PANEL, foreground=COLOR_FG_TEXT)
        style.configure("TFrame", background=COLOR_BG_MAIN)
        style.configure("Panel.TFrame", background=COLOR_BG_PANEL)
        style.configure("TLabelframe", background=COLOR_BG_PANEL, bordercolor=COLOR_BORDER)
        style.configure("TLabelframe.Label", background=COLOR_BG_PANEL, foreground=COLOR_ACCENT, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TEntry", fieldbackground=COLOR_INPUT_BG, foreground=COLOR_INPUT_FG, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER)
        style.configure("TButton", background="#3c3c3c", foreground="#ffffff", borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#505050")])
        style.configure("Action.TButton", background=COLOR_ACCENT, foreground="#ffffff", font=("Microsoft YaHei UI", 12, "bold"))
        style.map("Action.TButton", background=[("active", COLOR_ACCENT_HOVER)])
        style.configure("TCheckbutton", background=COLOR_BG_PANEL, foreground=COLOR_FG_TEXT, indicatorbackground=COLOR_INPUT_BG, indicatorforeground=COLOR_FG_TEXT)
        style.map("TCheckbutton", background=[("active", COLOR_BG_PANEL)])
        style.configure("TCombobox", fieldbackground=COLOR_INPUT_BG, background="#3c3c3c", foreground=COLOR_INPUT_FG, arrowcolor="white")

        # 主容器
        main_container = ttk.Frame(root, padding=15)
        main_container.pack(fill="both", expand=True)

        # ================= 左侧：控制面板 =================
        left_panel = ttk.Frame(main_container, width=380, style="Panel.TFrame")
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)

        left_inner = ttk.Frame(left_panel, style="Panel.TFrame", padding=15)
        left_inner.pack(fill="both", expand=True)

        # 1. 账号配置
        frame_auth = ttk.LabelFrame(left_inner, text="🔐 账号设置", padding=10)
        frame_auth.pack(fill="x", pady=(0, 15))
        
        ttk.Label(frame_auth, text="OA账号:", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_user = ttk.Entry(frame_auth, width=25)
        self.entry_user.grid(row=0, column=1, sticky="e", padx=5)
        
        ttk.Label(frame_auth, text="OA密码:", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_pwd = ttk.Entry(frame_auth, show="*", width=25)
        self.entry_pwd.grid(row=1, column=1, sticky="e", padx=5)

        # 2. 模型设置 (联动)
        frame_ai = ttk.LabelFrame(left_inner, text="🧠 模型设置 (API Key自动记忆)", padding=10)
        frame_ai.pack(fill="x", pady=(0, 15))

        ttk.Label(frame_ai, text="选择模型:", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.combo_model = ttk.Combobox(frame_ai, width=23, state="readonly")
        self.combo_model['values'] = list(self.api_configs.keys())
        self.combo_model.grid(row=0, column=1, sticky="e", padx=5)
        self.combo_model.bind("<<ComboboxSelected>>", self._on_model_change)

        ttk.Label(frame_ai, text="API Key:", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_key = ttk.Entry(frame_ai, width=25)
        self.entry_key.grid(row=1, column=1, sticky="e", padx=5)
        self.entry_key.bind("<FocusOut>", self._save_temp_key_config) 
        
        ttk.Label(frame_ai, text="Base URL:", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.entry_base_url = ttk.Entry(frame_ai, width=25)
        self.entry_base_url.grid(row=2, column=1, sticky="e", padx=5)
        self.entry_base_url.bind("<FocusOut>", self._save_temp_key_config) 

        # 3. 核心关键词
        frame_kw = ttk.LabelFrame(left_inner, text="🔑 今日工作关键词", padding=10)
        frame_kw.pack(fill="x", pady=(0, 15))
        
        self.text_keywords = tk.Text(frame_kw, height=5, width=30, font=("Microsoft YaHei UI", 10), 
                                     bg=COLOR_INPUT_BG, fg=COLOR_FG_SUB, insertbackground="white", relief="flat", padx=5, pady=5)
        self.text_keywords.pack(fill="x")
        self.text_keywords.insert("1.0", KEYWORD_PLACEHOLDER)
        self.text_keywords.bind("<FocusIn>", self._on_kw_focus_in)
        self.text_keywords.bind("<FocusOut>", self._on_kw_focus_out)

        # 4. AI 指令
        frame_prompt = ttk.LabelFrame(left_inner, text="🤖 AI 指令模板", padding=10)
        frame_prompt.pack(fill="both", expand=True, pady=(0, 15))
        
        self.text_prompt = scrolledtext.ScrolledText(frame_prompt, height=4, width=30, font=("Consolas", 9), 
                                                     bg=COLOR_INPUT_BG, fg=COLOR_FG_TEXT, insertbackground="white", relief="flat")
        self.text_prompt.pack(fill="both", expand=True)
        self.text_prompt.insert("1.0", DEFAULT_PROMPT_TEMPLATE)

        # 5. 操作区
        frame_ctrl = ttk.Frame(left_inner, style="Panel.TFrame")
        frame_ctrl.pack(fill="x", pady=0)
        
        self.var_headless = tk.BooleanVar(value=False)
        self.chk_headless = ttk.Checkbutton(frame_ctrl, text="🔒 后台静默运行 (支持锁屏执行)", variable=self.var_headless, command=self.save_settings)
        self.chk_headless.pack(anchor="w", pady=(0, 5))
        
        self.var_auto_run = tk.BooleanVar(value=False)
        self.chk_auto = ttk.Checkbutton(frame_ctrl, text="🚀 启动后自动执行 (智能跳过节假日)", variable=self.var_auto_run, command=self.save_settings)
        self.chk_auto.pack(anchor="w", pady=(0, 10))

        self.btn_action = ttk.Button(frame_ctrl, text="⚡ 一键生成并填写", style="Action.TButton", cursor="hand2", command=self.one_click_execute)
        self.btn_action.pack(fill="x", pady=(0, 8), ipady=5)
        
        ttk.Button(frame_ctrl, text="💾 保存配置", command=self.save_settings).pack(fill="x")

        # ================= 右侧：预览与日志 =================
        right_panel = ttk.Frame(main_container)
        right_panel.pack(side="right", fill="both", expand=True)

        self.lbl_timer = ttk.Label(right_panel, text="", font=("Microsoft YaHei UI", 12, "bold"), foreground="#ff4d4d", background=COLOR_BG_MAIN)
        self.lbl_timer.pack(anchor="e", pady=(0, 5))

        self.notebook = ttk.Notebook(right_panel)
        self.notebook.pack(fill="both", expand=True)

        # --- Tab 1: 预览 ---
        self.tab_preview = ttk.Frame(self.notebook, style="Panel.TFrame", padding=15)
        self.notebook.add(self.tab_preview, text=" 📄 任务预览 ")

        def create_section(parent, title, height):
            lbl = ttk.Label(parent, text=title, font=("Microsoft YaHei UI", 11, "bold"), foreground=COLOR_ACCENT, background=COLOR_BG_PANEL)
            lbl.pack(anchor="w", pady=(10, 5))
            txt = tk.Text(parent, height=height, font=("Microsoft YaHei UI", 10), 
                          bg=COLOR_INPUT_BG, fg=COLOR_FG_TEXT, insertbackground="white", relief="flat", padx=10, pady=8)
            txt.pack(fill="x", pady=(0, 5))
            return txt

        self.text_top5 = create_section(self.tab_preview, "🏆 Top 5 重点工作", 4)
        self.text_summary = create_section(self.tab_preview, "📝 今日总结", 3)
        self.text_todo = create_section(self.tab_preview, "✅ 待办事项 (Todo)", 8)

        # --- Tab 2: 历史 ---
        self.tab_history = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.notebook.add(self.tab_history, text=" 🕰️ 历史记录 ")
        
        h_paned = ttk.PanedWindow(self.tab_history, orient="horizontal")
        h_paned.pack(fill="both", expand=True)
        
        frame_h_list = ttk.Frame(h_paned, width=160, style="Panel.TFrame")
        h_paned.add(frame_h_list, weight=1)
        
        ttk.Button(frame_h_list, text="🔄 刷新列表", command=self.load_history).pack(fill="x", pady=(0,5))
        self.listbox_history = tk.Listbox(frame_h_list, font=("Microsoft YaHei UI", 9), 
                                          bg=COLOR_INPUT_BG, fg=COLOR_FG_TEXT, selectbackground=COLOR_ACCENT, relief="flat")
        self.listbox_history.pack(fill="both", expand=True)
        self.listbox_history.bind('<<ListboxSelect>>', self.on_history_select)

        self.text_hist_detail = scrolledtext.ScrolledText(h_paned, font=("Microsoft YaHei UI", 10), state='disabled', 
                                                          bg=COLOR_BG_PANEL, fg=COLOR_FG_TEXT, relief="flat", padx=15, pady=15)
        h_paned.add(self.text_hist_detail, weight=3)

        # --- Tab 3: 日志 ---
        self.tab_log = ttk.Frame(self.notebook, style="Panel.TFrame", padding=5)
        self.notebook.add(self.tab_log, text=" 📟 运行日志 ")
        self.log_area = scrolledtext.ScrolledText(self.tab_log, state='disabled', font=("Consolas", 9), 
                                                  bg="#121212", fg="#00ff00", relief="flat")
        self.log_area.pack(fill="both", expand=True)

        # 初始化
        self.load_settings()
        self.load_history()
        self.check_auto_run_smart()

    # ================= 逻辑部分 =================
    def _on_model_change(self, event):
        model_name = self.combo_model.get()
        if model_name in self.api_configs:
            cfg = self.api_configs[model_name]
            self.entry_key.delete(0, tk.END)
            self.entry_key.insert(0, cfg["key"])
            self.entry_base_url.delete(0, tk.END)
            self.entry_base_url.insert(0, cfg["url"])

    def _save_temp_key_config(self, event):
        model_name = self.combo_model.get()
        if model_name in self.api_configs:
            self.api_configs[model_name]["key"] = self.entry_key.get().strip()
            self.api_configs[model_name]["url"] = self.entry_base_url.get().strip()

    def _on_kw_focus_in(self, event):
        current = self.text_keywords.get("1.0", tk.END).strip()
        if current == KEYWORD_PLACEHOLDER.strip():
            self.text_keywords.delete("1.0", tk.END)
            self.text_keywords.config(foreground=COLOR_FG_TEXT)

    def _on_kw_focus_out(self, event):
        current = self.text_keywords.get("1.0", tk.END).strip()
        if not current:
            self.text_keywords.insert("1.0", KEYWORD_PLACEHOLDER)
            self.text_keywords.config(foreground=COLOR_FG_SUB)

    def log(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"{time.strftime('%H:%M:%S')} > {msg}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        if "❌" in msg and not self.var_auto_run.get():
            self.notebook.select(self.tab_log)

    def save_settings(self):
        self._save_temp_key_config(None)

        kw_content = self.text_keywords.get("1.0", tk.END).strip()
        if kw_content == KEYWORD_PLACEHOLDER.strip(): kw_content = ""
        
        settings = {
            "username": self.entry_user.get(), 
            "password": self.entry_pwd.get(),
            "api_configs": self.api_configs, 
            "last_model": self.combo_model.get(),
            "keywords": kw_content,
            "prompt_template": self.text_prompt.get("1.0", tk.END).strip(),
            "auto_run": self.var_auto_run.get(),
            "headless": self.var_headless.get() 
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        self.log("✅ 配置已保存")

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entry_user.insert(0, data.get("username", ""))
                    self.entry_pwd.insert(0, data.get("password", ""))
                    
                    saved_configs = data.get("api_configs", {})
                    if saved_configs:
                        for k, v in saved_configs.items():
                            if k in self.api_configs:
                                self.api_configs[k] = v
                    
                    last_model = data.get("last_model", "DeepSeek (国内直连)")
                    if last_model in self.api_configs:
                        self.combo_model.set(last_model)
                        self._on_model_change(None) 
                    else:
                        self.combo_model.current(0)

                    saved_kw = data.get("keywords", "")
                    if saved_kw:
                        self.text_keywords.delete("1.0", tk.END)
                        self.text_keywords.insert("1.0", saved_kw)
                        self.text_keywords.config(foreground=COLOR_FG_TEXT)
                    else:
                        self.text_keywords.delete("1.0", tk.END)
                        self.text_keywords.insert("1.0", KEYWORD_PLACEHOLDER)
                        self.text_keywords.config(foreground=COLOR_FG_SUB)
                    
                    self.var_auto_run.set(data.get("auto_run", False))
                    self.var_headless.set(data.get("headless", False)) 
                    
                    saved_prompt = data.get("prompt_template", "")
                    if saved_prompt: 
                        self.text_prompt.delete("1.0", tk.END)
                        self.text_prompt.insert("1.0", saved_prompt)
            except: pass
        else:
             self.combo_model.current(0)
             self._on_model_change(None)

    def save_history_record(self, top5, summary, todo):
        record = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "top5": top5, "summary": summary, "todo": todo}
        history = []
        if os.path.exists(HISTORY_FILE):
            try: 
                with open(HISTORY_FILE, "r", encoding="utf-8") as f: 
                    history = json.load(f)
            except: pass
        history.insert(0, record)
        if len(history) > 50: history = history[:50]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: 
            json.dump(history, f, ensure_ascii=False, indent=4)
        self.root.after(0, self.load_history)

    def load_history(self):
        self.listbox_history.delete(0, tk.END)
        self.history_data = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history_data = json.load(f)
                    for item in self.history_data: 
                        self.listbox_history.insert(tk.END, item["time"])
            except: pass

    def on_history_select(self, event):
        selection = self.listbox_history.curselection()
        if selection:
            record = self.history_data[selection[0]]
            detail = f"⏰ {record['time']}\n\n🏆 Top 5\n{record['top5']}\n\n📝 总结\n{record['summary']}\n\n✅ Todo\n{record['todo']}"
            self.text_hist_detail.config(state='normal')
            self.text_hist_detail.delete("1.0", tk.END)
            self.text_hist_detail.insert("1.0", detail)
            self.text_hist_detail.config(state='disabled')

    def check_is_workday(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            req = urllib.request.Request(f"http://timor.tech/api/holiday/info/{today_str}", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('code') == 0:
                        type_code = data['type']['type']
                        if type_code in [0, 3]: return True, f"工作日 ({data['type']['name']})"
                        return False, f"休息日 ({data['type']['name']})"
        except: pass
        return (True, "周一至周五") if datetime.now().weekday() < 5 else (False, "周末")

    def check_auto_run_smart(self):
        if self.var_auto_run.get(): self.root.after(500, self._do_check_and_run)

    def _do_check_and_run(self):
        self.log("📅 检查工作日...")
        is_work, reason = self.check_is_workday()
        self.log(f"📅 结果: {reason}")
        if is_work: self.auto_countdown(10)
        else: self.lbl_timer.config(text=f"☕ {reason}，自动运行已暂停", foreground="#28a745")

    def auto_countdown(self, seconds):
        if not self.var_auto_run.get(): self.lbl_timer.config(text=""); return
        if seconds > 0:
            self.lbl_timer.config(text=f"⏳ 倒计时: {seconds}s")
            self.root.after(1000, lambda: self.auto_countdown(seconds - 1))
        else:
            if self.var_auto_run.get():
                self.lbl_timer.config(text="🚀 启动中...")
                self.one_click_execute(auto=True)

    def one_click_execute(self, auto=False):
        raw_keywords = self.text_keywords.get("1.0", tk.END).strip()
        if not raw_keywords or raw_keywords == KEYWORD_PLACEHOLDER.strip():
            if not auto: messagebox.showwarning("提示", "请先填写【工作关键词】！")
            else: self.log("❌ 关键词为空，跳过执行")
            return

        if not auto:
            self.lbl_timer.config(text="")
            self.btn_action.config(state="disabled", text="⚡ 执行中...")
            self.notebook.select(self.tab_preview)
        threading.Thread(target=self._process_pipeline, args=(auto,), daemon=True).start()

    def _process_pipeline(self, auto):
        self.save_settings()
        
        model_name = self.combo_model.get()
        if model_name in self.api_configs:
            api_key = self.api_configs[model_name]["key"]
            base_url = self.api_configs[model_name]["url"]
        else:
            api_key = self.entry_key.get().strip()
            base_url = self.entry_base_url.get().strip()
        
        raw_keywords = self.text_keywords.get("1.0", tk.END).strip()
        template = self.text_prompt.get("1.0", tk.END).strip()
        if raw_keywords == KEYWORD_PLACEHOLDER.strip(): raw_keywords = ""

        if not api_key:
            self.log("❌ 缺少 API Key")
            self.root.after(0, lambda: self.btn_action.config(state="normal", text="⚡ 一键生成并填写"))
            return
        
        self.log(f"⚡ [1/2] AI生成中 ({model_name})...")
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            if "DeepSeek" in model_name:
                api_model = "deepseek-chat"
            elif "Gemini" in model_name:
                api_model = "gemini-2.0-flash" 
            else:
                api_model = "deepseek-chat" 

            final_prompt = template.replace("{keywords}", raw_keywords) + "\n\n(系统补充：请务必使用 @@@ 分隔 TOP5、总结、TODO 三部分)"
            
            response = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": final_prompt}],
                stream=False
            )
            
            content = response.choices[0].message.content
            parts = content.split("@@@")
            
            c_top5 = parts[0].strip() if len(parts)>0 else ""
            c_summ = parts[1].strip() if len(parts)>1 else ""
            c_todo = parts[2].strip() if len(parts)>2 else ""

            self.root.after(0, lambda: self._update_ui_preview(parts))
            self.save_history_record(c_top5, c_summ, c_todo)
            self.log("✅ AI生成完成")
        except Exception as e:
            self.log(f"❌ 生成失败: {e}")
            self.root.after(0, lambda: self.btn_action.config(state="normal", text="⚡ 一键生成并填写"))
            return

        try:
            self._run_selenium_logic(c_top5, c_summ, c_todo)
        except Exception as e: 
            self.log(f"❌ 自动化失败: {e}")
        
        self.root.after(0, lambda: self.btn_action.config(state="normal", text="⚡ 一键生成并填写"))
        self.log("🎉 流程结束")
        if not auto: messagebox.showinfo("完成", "✅ 执行完毕")

    def _update_ui_preview(self, parts):
        self.text_top5.delete("1.0", tk.END)
        self.text_summary.delete("1.0", tk.END)
        self.text_todo.delete("1.0", tk.END)
        if len(parts) > 0: self.text_top5.insert("1.0", parts[0].strip())
        if len(parts) > 1: self.text_summary.insert("1.0", parts[1].strip())
        if len(parts) > 2: self.text_todo.insert("1.0", parts[2].strip())

    def _run_selenium_logic(self, content_top5, content_summary, content_todo_raw):
        username = self.entry_user.get().strip()
        password = self.entry_pwd.get().strip()
        todo_list = [line for line in content_todo_raw.split('\n') if line.strip()]

        self.log(f"⚡ [2/2] 打开浏览器...")
        options = webdriver.ChromeOptions()
        
        if self.var_headless.get():
            self.log("🔒 已启用静默模式 (Headless)")
            options.add_argument("--headless=new") 
        
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            wait = WebDriverWait(driver, 20)
            driver.get(TARGET_URL)
            time.sleep(3)

            # 登录
            try:
                try:
                    driver.find_element(By.CSS_SELECTOR, "div[data-type='paragraph']")
                    self.log("✅ 已登录")
                except:
                    self.log("🔒 登录中...")
                    wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '工号') or contains(@placeholder, '账号')]"))).send_keys(username)
                    wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '密码')]"))).send_keys(password)
                    time.sleep(0.5)
                    btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), '登录')] | //input[@type='submit']")))
                    btn.click()
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-type='paragraph']")))
                    self.log("✅ 登录成功")
            except Exception as e:
                self.log(f"⚠️ 登录异常: {e}")
                time.sleep(5)
            time.sleep(2)

            # Top5
            try:
                potential_boxes = driver.find_elements(By.CSS_SELECTOR, "div[data-placeholder='请输入内容']")
                target_box = None
                for box in potential_boxes:
                    if box.is_displayed() and "ql-editor" not in box.get_attribute("class"):
                        target_box = box; break
                if target_box:
                    driver.execute_script("arguments[0].scrollIntoView(true);", target_box)
                    time.sleep(0.5)
                    curr = target_box.text.strip()
                    if len(curr) < 5 or "请输入内容" in curr:
                        target_box.click()
                        time.sleep(0.2)
                        act = driver.switch_to.active_element
                        act.send_keys(Keys.CONTROL, "a")
                        act.send_keys(Keys.BACK_SPACE)
                        act.send_keys(Keys.DELETE)
                        time.sleep(0.2)
                        act.send_keys(content_top5)
                        self.log("   - Top5 完成")
            except Exception as e: self.log(f"⚠️ Top5错: {e}")

            # 总结
            try:
                sm_box = driver.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']")
                if len(sm_box.text.strip()) < 5 or "请输入内容" in sm_box.text:
                    sm_box.click()
                    time.sleep(0.2)
                    sm_box.send_keys(Keys.CONTROL, "a")
                    sm_box.send_keys(Keys.BACK_SPACE)
                    time.sleep(0.2)
                    sm_box.send_keys(content_summary)
                    self.log("   - 总结 完成")
            except: pass

            # Todo
            try:
                for idx, item in enumerate(todo_list):
                    all_inputs = driver.find_elements(By.CSS_SELECTOR, "div.tribute-input[contenteditable='true']")
                    target = None
                    for inp in all_inputs:
                        if inp.is_displayed() and len(inp.text.strip()) < 2: target = inp; break
                    if not target:
                        try:
                            driver.find_element(By.XPATH, "//*[contains(text(), '新增todo') or contains(text(), '新增待办')]").click()
                            time.sleep(0.5)
                            target = driver.find_elements(By.CSS_SELECTOR, "div.tribute-input[contenteditable='true']")[-1]
                        except: pass
                    if target:
                        target.click()
                        time.sleep(0.1)
                        target.send_keys(item)
                        time.sleep(0.2)
                        target.send_keys(Keys.ENTER)
                        time.sleep(0.5)
                self.log("   - Todo 完成")
            except Exception as e: self.log(f"⚠️ Todo错: {e}")

            # 保存
            self.log("💾 保存...")
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                xpath = "//*[text()='保存']" 
                buttons = driver.find_elements(By.XPATH, xpath)
                clicked = False
                for btn in buttons:
                    if btn.is_displayed():
                        try: 
                            driver.execute_script("arguments[0].click();", btn)
                            clicked = True
                            self.log(f"🎉 保存成功")
                            break
                        except: pass
                if not clicked:
                    try: 
                        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "button[class*='primary'], div[class*='primary']"))
                        self.log("🎉 (备用) 保存成功")
                    except: pass
            except: pass
            
            time.sleep(5)
        finally:
            if driver: driver.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = TodoApp(root)
    root.mainloop()