import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk  # 更好的 UI 库
import pandas as pd
import google.generativeai as genai
import threading
import os

# 设置 UI 风格
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class LQAToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Game Localization LQA Master - AI 自动化审计工具")
        self.geometry("800x600")

        # --- UI 布局 ---
        self.grid_columnconfigure(1, weight=1)

        # 1. API 配置
        self.api_label = ctk.CTkLabel(self, text="Gemini API Key:")
        self.api_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        self.api_entry = ctk.CTkEntry(self, placeholder_text="在此输入你的 API Key...", width=400)
        self.api_entry.grid(row=0, column=1, padx=20, pady=10, sticky="ew")

        # 2. 文件选择
        self.file_btn = ctk.CTkButton(self, text="选择待审 Excel", command=self.select_file)
        self.file_btn.grid(row=1, column=0, padx=20, pady=10)
        self.file_label = ctk.CTkLabel(self, text="未选择文件", text_color="gray")
        self.file_label.grid(row=1, column=1, padx=20, pady=10, sticky="w")

        self.glossary_btn = ctk.CTkButton(self, text="选择术语表 (可选)", command=self.select_glossary)
        self.glossary_btn.grid(row=2, column=0, padx=20, pady=10)
        self.glossary_label = ctk.CTkLabel(self, text="未选择术语表", text_color="gray")
        self.glossary_label.grid(row=2, column=1, padx=20, pady=10, sticky="w")

        # 3. 运行控制
        self.run_btn = ctk.CTkButton(self, text="🚀 开始自动化审计", command=self.start_audit_thread, fg_color="#2ECC71", hover_color="#27AE60")
        self.run_btn.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="ew")

        # 4. 日志输出
        self.log_output = ctk.CTkTextbox(self, height=300)
        self.log_output.grid(row=4, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")

        # 5. 进度条
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=5, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)

        # 内部变量
        self.input_path = ""
        self.glossary_path = ""

    def select_file(self):
        self.input_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if self.input_path:
            self.file_label.configure(text=os.path.basename(self.input_path), text_color="white")

    def select_glossary(self):
        self.glossary_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if self.glossary_path:
            self.glossary_label.configure(text=os.path.basename(self.glossary_path), text_color="white")

    def log(self, message):
        self.log_output.insert("end", f"{message}\n")
        self.log_output.see("end")

    def start_audit_thread(self):
        # 验证输入
        if not self.api_entry.get():
            messagebox.showerror("错误", "请输入 API Key")
            return
        if not self.input_path:
            messagebox.showerror("错误", "请选择待审计的 Excel 文件")
            return
        
        # 开启新线程防止界面卡死
        threading.Thread(target=self.run_audit, daemon=True).start()

    def run_audit(self):
        api_key = self.api_entry.get()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        self.log("📋 正在读取数据...")
        try:
            df = pd.read_excel(self.input_path)
            glossary = ""
            if self.glossary_path:
                glossary_df = pd.read_excel(self.glossary_path)
                glossary = glossary_df.to_string(index=False)
            
            total_rows = len(df)
            batch_size = 10
            all_reports = []

            for i in range(0, total_rows, batch_size):
                batch = df.iloc[i : i + batch_size]
                batch_text = "\n".join([f"{row.get('ID', 'N/A')} | {row.get('Source', '')} | {row.get('Target', '')}" for _, row in batch.iterrows()])
                
                self.log(f"🔍 正在审计第 {i+1} 至 {min(i+batch_size, total_rows)} 行...")
                
                prompt = f"你是一个游戏本地化专家。请根据术语表：\n{glossary}\n审核以下翻译：\n{batch_text}\n指出术语错误、爆框（>30字符）或语感生硬。直接输出 ID | 问题 | 建议。"
                
                response = model.generate_content(prompt)
                all_reports.append(response.text)
                
                # 更新进度条
                self.progress_bar.set((i + batch_size) / total_rows)
            
            # 保存结果
            with open("LQA_Audit_Report.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(all_reports))
            
            self.log("✅ 审计完成！报告已生成为：LQA_Audit_Report.txt")
            messagebox.showinfo("成功", "审计已完成，报告已保存！")

        except Exception as e:
            self.log(f"❌ 运行报错: {str(e)}")
            messagebox.showerror("运行错误", str(e))

if __name__ == "__main__":
    app = LQAToolApp()
    app.mainloop()