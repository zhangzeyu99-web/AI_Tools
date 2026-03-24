"""Game Localization QA Workflow — GUI

Two-phase interface:
  Phase 1: Machine review (one click)
  Phase 2: AI review (clipboard-guided, batch by batch)
  → Final output

Run with:  python gui.py
"""
import io
import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from process_language import run_machine_review, write_outputs, prepare_ai_review, RowState
from utils.ai_checker import parse_ai_response, apply_corrections, BatchInfo

# ─── Style ────────────────────────────────────────────────

BG = "#f5f5f5"
CARD = "#ffffff"
ACCENT = "#4a90d9"
ACCENT2 = "#3a7bc8"
GREEN = "#27ae60"
ORANGE = "#e67e22"
TXT = "#2c3e50"
TXT2 = "#7f8c8d"
FT = ("Microsoft YaHei UI", 10)
FT_T = ("Microsoft YaHei UI", 14, "bold")
FT_H = ("Microsoft YaHei UI", 11, "bold")
FT_S = ("Microsoft YaHei UI", 9)
FT_L = ("Consolas", 9)
CHATGPT_URL = "https://chatgpt.com/"


class FileRow(tk.Frame):
    def __init__(self, parent, label, filetypes=None, optional=False, **kw):
        super().__init__(parent, bg=CARD, **kw)
        self._ft = filetypes or [("Excel 文件", "*.xlsx"), ("所有文件", "*.*")]
        lbl = f"{label}{'（可选）' if optional else ''}"
        tk.Label(self, text=lbl, font=FT, bg=CARD, fg=TXT,
                 width=16, anchor="e").pack(side="left", padx=(0, 6))
        self.var = tk.StringVar()
        tk.Entry(self, textvariable=self.var, font=FT, width=48,
                 relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(self, text="浏览…", font=FT_S, command=self._browse,
                  relief="solid", bd=1, cursor="hand2", padx=8).pack(side="left", padx=(6, 0))

    def _browse(self):
        p = filedialog.askopenfilename(filetypes=self._ft)
        if p:
            self.var.set(p)

    def get(self):
        return self.var.get().strip()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("游戏本地化质检工具")
        self.geometry("740x780")
        self.configure(bg=BG)
        self.resizable(True, True)

        # State
        self._df = None
        self._col_map = None
        self._states = None
        self._groups = None
        self._term_lookup = None
        self._input_path = ''
        self._batches: list[BatchInfo] = []
        self._current_batch = 0
        self._ai_corrections_total = 0

        self._build()

    def _build(self):
        # Title
        hdr = tk.Frame(self, bg=ACCENT)
        hdr.pack(fill="x")
        tk.Label(hdr, text="游戏本地化质检工具", font=FT_T, bg=ACCENT, fg="white").pack(pady=10)

        # Scrollable body
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._body = tk.Frame(canvas, bg=BG)
        self._body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._body, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        body = self._body
        body.columnconfigure(0, weight=1)
        pad = {"padx": 12, "pady": (6, 3), "sticky": "ew"}

        # ── Phase 1: Input + Machine Review ──
        p1 = tk.LabelFrame(body, text="  第一步 · 机审质检  ", font=FT_H,
                           bg=CARD, fg=ACCENT, relief="solid", bd=1, padx=14, pady=10)
        p1.grid(row=0, column=0, **pad)

        self.file_lang = FileRow(p1, "语言表 Excel:")
        self.file_lang.pack(fill="x", pady=(0, 5))
        self.file_term = FileRow(p1, "术语库:", optional=True,
                                 filetypes=[("Excel / JSON", "*.xlsx *.json"), ("Excel", "*.xlsx"), ("JSON", "*.json"), ("所有文件", "*.*")])
        self.file_term.pack(fill="x", pady=(0, 5))

        opts = tk.Frame(p1, bg=CARD)
        opts.pack(fill="x", pady=(4, 0))
        self.auto_fix_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="自动修复", variable=self.auto_fix_var,
                       font=FT, bg=CARD, activebackground=CARD).pack(side="left", padx=(130, 16))
        tk.Label(opts, text="语言:", font=FT, bg=CARD, fg=TXT).pack(side="left")
        self.lang_var = tk.StringVar(value="en")
        ttk.Combobox(opts, textvariable=self.lang_var, width=6, state="readonly",
                     values=["en", "idn", "fr", "de", "tr", "es", "pt", "ru"]).pack(side="left", padx=(4, 0))
        tk.Label(opts, text="AI批次:", font=FT, bg=CARD, fg=TXT).pack(side="left", padx=(16, 0))
        self.batch_var = tk.StringVar(value="500")
        ttk.Combobox(opts, textvariable=self.batch_var, width=6, state="readonly",
                     values=["200", "500", "1000"]).pack(side="left", padx=(4, 0))
        tk.Label(opts, text="行/批", font=FT_S, bg=CARD, fg=TXT2).pack(side="left", padx=(2, 0))

        self.btn_p1 = tk.Button(p1, text="▶  开始机审", font=("Microsoft YaHei UI", 11, "bold"),
                                bg=ACCENT, fg="white", activebackground=ACCENT2, activeforeground="white",
                                relief="flat", cursor="hand2", padx=24, pady=4, command=self._run_phase1)
        self.btn_p1.pack(pady=(8, 2))

        self.p1_result = tk.Label(p1, text="", font=FT, bg=CARD, fg=TXT, justify="left", anchor="w")

        # ── Phase 2: AI Review ──
        self.p2_frame = tk.LabelFrame(body, text="  第二步 · AI审查  ", font=FT_H,
                                      bg=CARD, fg=ORANGE, relief="solid", bd=1, padx=14, pady=10)

        self.p2_progress = tk.Label(self.p2_frame, text="", font=FT_H, bg=CARD, fg=TXT)
        self.p2_progress.pack(fill="x")

        self.p2_hint = tk.Label(self.p2_frame, text=(
            "操作：点「复制提示词」→ 粘贴到 ChatGPT → 复制AI回复 → 点「粘贴AI结果」"
        ), font=FT_S, bg=CARD, fg=TXT2, wraplength=650, justify="left")
        self.p2_hint.pack(fill="x", pady=(2, 6))

        btn_row = tk.Frame(self.p2_frame, bg=CARD)
        btn_row.pack(fill="x")

        self.btn_copy = tk.Button(btn_row, text="复制提示词", font=FT,
                                  bg=ACCENT, fg="white", activebackground=ACCENT2, activeforeground="white",
                                  relief="flat", cursor="hand2", padx=14, pady=2, command=self._copy_prompt)
        self.btn_copy.pack(side="left", padx=(0, 6))

        self.btn_open_ai = tk.Button(btn_row, text="打开 ChatGPT", font=FT_S,
                                     relief="solid", bd=1, cursor="hand2", padx=8,
                                     command=lambda: webbrowser.open(CHATGPT_URL))
        self.btn_open_ai.pack(side="left", padx=(0, 6))

        self.btn_paste = tk.Button(btn_row, text="粘贴AI结果", font=FT,
                                   bg=GREEN, fg="white", activebackground="#219a52", activeforeground="white",
                                   relief="flat", cursor="hand2", padx=14, pady=2, command=self._paste_response)
        self.btn_paste.pack(side="left", padx=(0, 6))

        self.btn_prev = tk.Button(btn_row, text="← 上一批", font=FT_S,
                                  relief="solid", bd=1, cursor="hand2", padx=8, command=self._prev_batch)
        self.btn_prev.pack(side="left", padx=(0, 6))

        self.btn_skip = tk.Button(btn_row, text="跳过此批", font=FT_S,
                                  relief="solid", bd=1, cursor="hand2", padx=8, command=self._skip_batch)
        self.btn_skip.pack(side="left", padx=(0, 6))

        self.btn_finish_ai = tk.Button(btn_row, text="完成AI审查 →", font=FT_S,
                                       relief="solid", bd=1, cursor="hand2", padx=8, command=self._finish_ai)
        self.btn_finish_ai.pack(side="right")

        self.p2_status = tk.Label(self.p2_frame, text="", font=FT_S, bg=CARD, fg=GREEN, anchor="w")
        self.p2_status.pack(fill="x", pady=(6, 0))

        # ── Final result card ──
        self.final_frame = tk.LabelFrame(body, text="  最终结果  ", font=FT_H,
                                         bg="#eaf4ea", fg=GREEN, relief="solid", bd=1, padx=14, pady=10)
        self.final_label = tk.Label(self.final_frame, text="", font=FT, bg="#eaf4ea", fg=TXT,
                                    justify="left", anchor="w")
        self.final_label.pack(fill="x")

        self.final_btns = tk.Frame(self.final_frame, bg="#eaf4ea")
        self.final_btns.pack(fill="x", pady=(8, 0))
        self.btn_open_result = tk.Button(self.final_btns, text="打开结果文件", font=FT_S,
                                         relief="solid", bd=1, cursor="hand2", padx=10)
        self.btn_open_result.pack(side="left", padx=(0, 8))
        self.btn_open_report = tk.Button(self.final_btns, text="打开质检报告", font=FT_S,
                                          relief="solid", bd=1, cursor="hand2", padx=10)
        self.btn_open_report.pack(side="left", padx=(0, 8))
        self.btn_open_dir = tk.Button(self.final_btns, text="打开输出文件夹", font=FT_S,
                                       relief="solid", bd=1, cursor="hand2", padx=10)
        self.btn_open_dir.pack(side="left")

        # ── Log ──
        log_f = tk.LabelFrame(body, text="  日志  ", font=FT_H, bg=CARD,
                               fg=TXT2, relief="solid", bd=1, padx=10, pady=6)
        log_f.grid(row=4, column=0, padx=12, pady=(6, 12), sticky="ew")
        self.log = tk.Text(log_f, height=6, font=FT_L, bg="#1e1e1e", fg="#d4d4d4",
                           insertbackground="white", relief="flat", wrap="word")
        ttk.Scrollbar(log_f, command=self.log.yview).pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        self._log("就绪。")

    # ── Logging ──

    def _log(self, t):
        self.log.configure(state="normal")
        self.log.insert("end", t + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log_clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Phase 1: Machine Review ──

    def _run_phase1(self):
        lp = self.file_lang.get()
        if not lp:
            messagebox.showwarning("提示", "请选择语言表 Excel 文件")
            return
        if not Path(lp).exists():
            messagebox.showerror("错误", f"文件不存在：{lp}")
            return

        tp = self.file_term.get() or None
        if tp and not Path(tp).exists():
            tp = None

        self._input_path = lp
        self.btn_p1.configure(state="disabled", text="处理中…")
        self.p2_frame.grid_forget()
        self.final_frame.grid_forget()
        self._log_clear()
        self._log("开始机审…")

        def task():
            try:
                old = sys.stdout
                sys.stdout = buf = io.StringIO()
                df, col_map, states, groups = run_machine_review(
                    lp, tp, self.auto_fix_var.get(),
                )
                from process_language import _load_term_base
                term_lookup = _load_term_base(tp)
                sys.stdout = old
                self.after(0, lambda: self._on_phase1_done(True, df, col_map, states, groups, buf.getvalue(), term_lookup=term_lookup))
            except Exception as e:
                sys.stdout = sys.__stdout__
                self.after(0, lambda: self._on_phase1_done(False, error=str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _on_phase1_done(self, ok, df=None, col_map=None, states=None, groups=None, captured="", error="", term_lookup=None):
        self.btn_p1.configure(state="normal", text="▶  开始机审")
        if not ok:
            self._log(f"错误: {error}")
            messagebox.showerror("错误", error)
            return

        try:
            self._df, self._col_map, self._states, self._groups = df, col_map, states, groups
            self._term_lookup = term_lookup
            for line in captured.strip().split("\n"):
                self._log("  " + line)

            total = len(states)
            fixed = sum(1 for s in states.values() if s.fixed_translation != s.translation)
            issues = sum(len(s.issues) for s in states.values())
            self.p1_result.configure(text=f"  机审完成: {total} 行，发现 {issues} 个问题，自动修复 {fixed} 处")
            self.p1_result.pack(fill="x", pady=(4, 0))

            # Prepare AI batches
            batch_size = int(self.batch_var.get())
            self._batches = prepare_ai_review(states, batch_size=batch_size, term_lookup=self._term_lookup, lang=self.lang_var.get())
            self._current_batch = 0
            self._ai_corrections_total = 0

            # Show phase 2
            self._update_p2_display()
            self.p2_frame.grid(row=1, column=0, padx=12, pady=(6, 3), sticky="ew")
            self._body.update_idletasks()
            self._log(f"\n机审完成。AI审查已准备: {len(self._batches)} 个批次，每批约200行")
            self._log("请按顺序操作：复制提示词 → 粘贴到ChatGPT → 复制回复 → 粘贴AI结果")
        except Exception as e:
            self._log(f"错误: {e}")
            import traceback
            self._log(traceback.format_exc())
            messagebox.showerror("错误", str(e))

    # ── Phase 2: AI Review ──

    def _update_p2_display(self):
        total = len(self._batches)
        cur = self._current_batch + 1
        self.btn_prev.configure(state="normal" if self._current_batch > 0 else "disabled")
        if self._current_batch >= total:
            self.p2_progress.configure(text=f"全部 {total} 批已完成")
            self.btn_copy.configure(state="disabled")
            self.btn_paste.configure(state="disabled")
            self.btn_skip.configure(state="disabled")
            self.p2_status.configure(text=f"AI共修正 {self._ai_corrections_total} 处。点击「完成AI审查 →」生成最终文件。")
        else:
            batch = self._batches[self._current_batch]
            self.p2_progress.configure(text=f"第 {cur} / {total} 批  （ID {batch.row_ids[0]} ~ {batch.row_ids[-1]}，共 {len(batch.row_ids)} 行）")
            self.btn_copy.configure(state="normal")
            self.btn_paste.configure(state="normal")
            self.btn_skip.configure(state="normal")

    def _copy_prompt(self):
        if self._current_batch >= len(self._batches):
            return
        batch = self._batches[self._current_batch]
        self.clipboard_clear()
        self.clipboard_append(batch.prompt_text)
        self.update()
        self._log(f"  第 {self._current_batch + 1} 批提示词已复制到剪贴板（{len(batch.row_ids)} 行）")
        self.p2_status.configure(text="已复制！粘贴到 ChatGPT，等AI回复后复制回来，点「粘贴AI结果」", fg=ACCENT)

    def _paste_response(self):
        if self._current_batch >= len(self._batches):
            return
        try:
            response = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板为空，请先复制AI的回复")
            return

        if not response.strip():
            messagebox.showwarning("提示", "剪贴板内容为空")
            return

        batch = self._batches[self._current_batch]
        batch.response_text = response
        batch.corrections = parse_ai_response(response)
        batch.is_done = True

        modified = apply_corrections(batch.corrections, self._states)
        self._ai_corrections_total += modified

        self._log(f"  第 {self._current_batch + 1} 批: 解析到 {len(batch.corrections)} 条修正，应用 {modified} 处")
        self.p2_status.configure(text=f"已导入 {len(batch.corrections)} 条修正！", fg=GREEN)

        self._current_batch += 1
        self._update_p2_display()

    def _prev_batch(self):
        if self._current_batch <= 0:
            messagebox.showinfo("提示", "已经是第一批了")
            return
        self._current_batch -= 1
        batch = self._batches[self._current_batch]

        # Undo corrections from this batch
        if batch.is_done and batch.corrections:
            for c in batch.corrections:
                state = self._states.get(c.row_id)
                if state and 'AI审校修正' in state.notes:
                    state.fixed_translation = state.translation
                    state.notes = [n for n in state.notes if n != 'AI审校修正']
                    self._ai_corrections_total = max(0, self._ai_corrections_total - 1)
            batch.corrections.clear()
            batch.response_text = ''
            batch.is_done = False

        self._update_p2_display()
        self._log(f"  已返回第 {self._current_batch + 1} 批，可重新操作")
        self.p2_status.configure(text="已撤回上一批，请重新操作", fg=ORANGE)

    def _skip_batch(self):
        if self._current_batch >= len(self._batches):
            return
        self._log(f"  跳过第 {self._current_batch + 1} 批")
        self._current_batch += 1
        self._update_p2_display()

    def _finish_ai(self):
        undone = sum(1 for b in self._batches if not b.is_done)
        if undone > 0:
            if not messagebox.askyesno("确认", f"还有 {undone} 批未审查，确定跳过直接生成最终文件？"):
                return

        self._log("\n生成最终输出文件…")
        self.p2_frame.grid_forget()

        output_dir = str(PROJECT_ROOT / "output")
        try:
            old = sys.stdout
            sys.stdout = buf = io.StringIO()
            summary = write_outputs(
                self._df, self._col_map, self._states, self._groups,
                self._input_path, self.lang_var.get(), output_dir,
            )
            sys.stdout = old
            for line in buf.getvalue().strip().split("\n"):
                self._log("  " + line)
        except Exception as e:
            sys.stdout = sys.__stdout__
            self._log(f"错误: {e}")
            messagebox.showerror("错误", str(e))
            return

        s = summary
        text = (
            f"处理完成!\n\n"
            f"  总行数:       {s['total_processed']}\n"
            f"  自动修复:     {s['auto_fixed']}（机审 + AI审）\n"
            f"  需人工确认:   {s['need_human_review']}\n"
            f"  无需改动:     {s['no_change']}\n"
            f"  UI文本:       {s['ui_texts']}\n"
            f"  AI修正:       {self._ai_corrections_total}"
        )
        self.final_label.configure(text=text)

        rp = s.get('result_path', '')
        rep = s.get('report_path', '')
        self.btn_open_result.configure(command=lambda: os.startfile(rp) if rp else None)
        self.btn_open_report.configure(command=lambda: os.startfile(rep) if rep else None)
        self.btn_open_dir.configure(command=lambda: os.startfile(output_dir))

        self.final_frame.grid(row=2, column=0, padx=12, pady=(6, 3), sticky="ew")

        messagebox.showinfo("完成", f"最终文件已生成！\nAI审查修正: {self._ai_corrections_total} 处")


if __name__ == "__main__":
    App().mainloop()
