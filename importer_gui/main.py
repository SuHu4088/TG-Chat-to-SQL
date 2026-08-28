import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from db_manager import DatabaseManager
from importer import JSONImporter


DARK_BG = '#1e1e2e'
DARK_BG_SECONDARY = '#2a2a3e'
DARK_BG_TERTIARY = '#333348'
TEXT_COLOR = '#cdd6f4'
TEXT_DIM = '#a6adc8'
ACCENT = '#89b4fa'
ACCENT_HOVER = '#b4befe'
SUCCESS = '#a6e3a1'
WARNING = '#f9e2af'
ERROR = '#f38ba8'
BORDER = '#45475a'


class TkinterApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("TG群聊SQL导入工具")
        self.geometry("900x650")
        self.configure(bg=DARK_BG)
        self.minsize(800, 600)

        self.db_path = tk.StringVar(value=os.path.join(os.path.dirname(__file__), 'telegram_chat.db'))
        self.json_path = tk.StringVar()
        self.db_manager: DatabaseManager = None
        self.is_importing = False

        self._setup_styles()
        self._create_widgets()
        self._load_database()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure('Dark.TFrame', background=DARK_BG)
        style.configure('DarkSecondary.TFrame', background=DARK_BG_SECONDARY)

        style.configure('Dark.TLabel',
                        background=DARK_BG,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 10))

        style.configure('Title.TLabel',
                        background=DARK_BG,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 16, 'bold'))

        style.configure('Subtitle.TLabel',
                        background=DARK_BG,
                        foreground=TEXT_DIM,
                        font=('Microsoft YaHei', 9))

        style.configure('DarkSecondary.TLabel',
                        background=DARK_BG_SECONDARY,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 10))

        style.configure('Accent.TButton',
                        background=ACCENT,
                        foreground=DARK_BG,
                        font=('Microsoft YaHei', 10, 'bold'),
                        padding=(16, 8),
                        borderwidth=0)
        style.map('Accent.TButton',
                  background=[('active', ACCENT_HOVER)])

        style.configure('Dark.TButton',
                        background=DARK_BG_TERTIARY,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 10),
                        padding=(12, 6),
                        borderwidth=0)
        style.map('Dark.TButton',
                  background=[('active', BORDER)])

        style.configure('Success.TButton',
                        background='#313244',
                        foreground=SUCCESS,
                        font=('Microsoft YaHei', 10, 'bold'),
                        padding=(16, 8),
                        borderwidth=0)
        style.map('Success.TButton',
                  background=[('active', BORDER)])

        style.configure('Dark.TLabelframe',
                        background=DARK_BG_SECONDARY,
                        foreground=TEXT_COLOR,
                        borderwidth=1,
                        relief='solid')

        style.configure('Dark.TLabelframe.Label',
                        background=DARK_BG_SECONDARY,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 10, 'bold'))

        style.configure('Dark.Horizontal.TProgressbar',
                        background=ACCENT,
                        troughcolor=DARK_BG_TERTIARY,
                        bordercolor=DARK_BG_TERTIARY,
                        lightcolor=ACCENT,
                        darkcolor=ACCENT,
                        thickness=20)

        style.configure('Dark.Treeview',
                        background=DARK_BG_TERTIARY,
                        foreground=TEXT_COLOR,
                        fieldbackground=DARK_BG_TERTIARY,
                        font=('Microsoft YaHei', 9),
                        rowheight=25,
                        borderwidth=0)

        style.configure('Dark.Treeview.Heading',
                        background=DARK_BG_SECONDARY,
                        foreground=TEXT_COLOR,
                        font=('Microsoft YaHei', 9, 'bold'),
                        borderwidth=1,
                        relief='flat')

        style.map('Dark.Treeview',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', DARK_BG)])

        style.configure('Dark.Vertical.TScrollbar',
                        background=DARK_BG_TERTIARY,
                        troughcolor=DARK_BG_SECONDARY,
                        arrowcolor=TEXT_COLOR,
                        borderwidth=0)

        style.configure('Dark.Horizontal.TScrollbar',
                        background=DARK_BG_TERTIARY,
                        troughcolor=DARK_BG_SECONDARY,
                        arrowcolor=TEXT_COLOR,
                        borderwidth=0)

        style.configure('Dark.TNotebook',
                        background=DARK_BG,
                        borderwidth=0)

        style.configure('Dark.TNotebook.Tab',
                        background=DARK_BG_SECONDARY,
                        foreground=TEXT_DIM,
                        padding=[20, 10],
                        font=('Microsoft YaHei', 10))

        style.map('Dark.TNotebook.Tab',
                  background=[('selected', DARK_BG_TERTIARY)],
                  foreground=[('selected', ACCENT)])

        style.configure('Dark.TEntry',
                        fieldbackground=DARK_BG_TERTIARY,
                        foreground=TEXT_COLOR,
                        insertcolor=TEXT_COLOR,
                        borderwidth=1,
                        relief='solid')

    def _create_widgets(self):
        main_frame = ttk.Frame(self, style='Dark.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        title_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(title_frame, text="📨 TG群聊SQL导入工具", style='Title.TLabel').pack(side=tk.LEFT)
        ttk.Label(title_frame, text="  自动识别 · 增量导入 · 去重安全", style='Subtitle.TLabel').pack(side=tk.LEFT, pady=(8, 0))

        file_frame = ttk.LabelFrame(main_frame, text=" 文件选择 ", style='Dark.TLabelframe')
        file_frame.pack(fill=tk.X, pady=(0, 16))

        row1 = ttk.Frame(file_frame, style='DarkSecondary.TFrame')
        row1.pack(fill=tk.X, padx=12, pady=(12, 8))

        ttk.Label(row1, text="数据库路径:", style='DarkSecondary.TLabel').pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.db_path, style='Dark.TEntry', font=('Consolas', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Button(row1, text="浏览...", style='Dark.TButton', command=self._browse_db).pack(side=tk.LEFT)

        row2 = ttk.Frame(file_frame, style='DarkSecondary.TFrame')
        row2.pack(fill=tk.X, padx=12, pady=(4, 12))

        ttk.Label(row2, text="  JSON文件:", style='DarkSecondary.TLabel').pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.json_path, style='Dark.TEntry', font=('Consolas', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Button(row2, text="选择JSON", style='Accent.TButton', command=self._browse_json).pack(side=tk.LEFT)

        notebook = ttk.Notebook(main_frame, style='Dark.TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True)

        import_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(import_tab, text="  导入数据  ")

        self._setup_import_tab(import_tab)

        stats_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(stats_tab, text="  数据统计  ")

        self._setup_stats_tab(stats_tab)

        history_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(history_tab, text="  导入历史  ")

        self._setup_history_tab(history_tab)

        status_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        status_frame.pack(fill=tk.X, pady=(12, 0))

        self.status_label = ttk.Label(status_frame, text="就绪", style='Subtitle.TLabel')
        self.status_label.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(status_frame, style='Dark.Horizontal.TProgressbar', mode='determinate', length=200)
        self.progress.pack(side=tk.RIGHT)

    def _setup_import_tab(self, parent):
        info_frame = ttk.LabelFrame(parent, text=" 文件信息预览 ", style='Dark.TLabelframe')
        info_frame.pack(fill=tk.X, padx=8, pady=(8, 12))

        self.info_text = tk.Text(info_frame, height=5, bg=DARK_BG_TERTIARY, fg=TEXT_COLOR,
                                 insertbackground=TEXT_COLOR, selectbackground=ACCENT, selectforeground=DARK_BG,
                                 font=('Consolas', 10), relief='flat', borderwidth=0,
                                 wrap='word')
        self.info_text.pack(fill=tk.X, padx=12, pady=12)
        self.info_text.insert('1.0', '请选择一个Telegram导出的JSON文件...')
        self.info_text.config(state=tk.DISABLED)

        action_frame = ttk.Frame(parent, style='Dark.TFrame')
        action_frame.pack(fill=tk.X, padx=8, pady=12)

        self.import_btn = ttk.Button(action_frame, text="🚀 开始导入", style='Success.TButton', command=self._start_import)
        self.import_btn.pack(side=tk.LEFT, padx=(8, 8))

        ttk.Button(action_frame, text="清空预览", style='Dark.TButton', command=self._clear_preview).pack(side=tk.LEFT, padx=8)
        ttk.Button(action_frame, text="刷新数据库", style='Dark.TButton', command=self._load_database).pack(side=tk.LEFT, padx=8)

        self.result_frame = ttk.LabelFrame(parent, text=" 导入结果 ", style='Dark.TLabelframe')
        self.result_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 12))

        self.result_text = tk.Text(self.result_frame, bg=DARK_BG_TERTIARY, fg=TEXT_COLOR,
                                   insertbackground=TEXT_COLOR, selectbackground=ACCENT, selectforeground=DARK_BG,
                                   font=('Consolas', 10), relief='flat', borderwidth=0,
                                   wrap='word', padx=12, pady=12)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        scrollbar = ttk.Scrollbar(self.result_frame, orient='vertical', command=self.result_text.yview,
                                   style='Dark.Vertical.TScrollbar')
        self.result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.place(relx=1.0, rely=0, relheight=1, anchor='ne')

        self.result_text.insert('1.0', '等待导入...')
        self.result_text.config(state=tk.DISABLED)

    def _setup_stats_tab(self, parent):
        canvas_frame = ttk.Frame(parent, style='Dark.TFrame')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        stats_grid = ttk.Frame(canvas_frame, style='Dark.TFrame')
        stats_grid.pack(fill=tk.BOTH, expand=True)

        self.stat_labels = {}
        stat_items = [
            ('total_messages', '📝 消息总数', SUCCESS),
            ('regular_messages', '💬 普通消息', ACCENT),
            ('service_messages', '⚙️ 服务消息', WARNING),
            ('unique_senders', '👥 独立用户', '#cba6f7'),
            ('reply_count', '↩️ 回复消息', '#fab387'),
            ('forward_count', '📤 转发消息', '#89dceb'),
            ('entity_count', '🔤 文本实体', '#f5c2e7'),
        ]

        for i, (key, label, color) in enumerate(stat_items):
            frame = ttk.Frame(stats_grid, style='DarkSecondary.TFrame')
            frame.grid(row=i // 2, column=i % 2, sticky='nsew', padx=6, pady=6)

            ttk.Label(frame, text=label, style='DarkSecondary.TLabel',
                      font=('Microsoft YaHei', 11)).pack(pady=(12, 4))

            value_label = tk.Label(frame, text='-', bg=DARK_BG_SECONDARY, fg=color,
                                    font=('Segoe UI', 28, 'bold'))
            value_label.pack(pady=(0, 12))

            self.stat_labels[key] = value_label

        stats_grid.columnconfigure(0, weight=1)
        stats_grid.columnconfigure(1, weight=1)
        for r in range((len(stat_items) + 1) // 2):
            stats_grid.rowconfigure(r, weight=1)

        button_frame = ttk.Frame(canvas_frame, style='Dark.TFrame')
        button_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(button_frame, text="🔄 刷新统计", style='Dark.TButton', command=self._refresh_stats).pack(side=tk.RIGHT)

    def _setup_history_tab(self, parent):
        frame = ttk.Frame(parent, style='Dark.TFrame')
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        columns = ('time', 'file', 'total', 'imported', 'skipped', 'status')
        self.history_tree = ttk.Treeview(frame, columns=columns, show='headings', style='Dark.Treeview')

        self.history_tree.heading('time', text='导入时间')
        self.history_tree.heading('file', text='JSON文件')
        self.history_tree.heading('total', text='JSON总数')
        self.history_tree.heading('imported', text='已导入')
        self.history_tree.heading('skipped', text='跳过(重复)')
        self.history_tree.heading('status', text='状态')

        self.history_tree.column('time', width=150, anchor='center')
        self.history_tree.column('file', width=200, anchor='w')
        self.history_tree.column('total', width=80, anchor='center')
        self.history_tree.column('imported', width=80, anchor='center')
        self.history_tree.column('skipped', width=100, anchor='center')
        self.history_tree.column('status', width=80, anchor='center')

        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.history_tree.yview,
                                   style='Dark.Vertical.TScrollbar')
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(parent, style='Dark.TFrame')
        button_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(button_frame, text="🔄 刷新历史", style='Dark.TButton', command=self._refresh_history).pack(side=tk.RIGHT)

    def _browse_db(self):
        path = filedialog.asksaveasfilename(
            title="选择或创建数据库文件",
            defaultextension=".db",
            filetypes=[("SQLite数据库", "*.db"), ("所有文件", "*.*")]
        )
        if path:
            self.db_path.set(path)
            self._load_database()

    def _browse_json(self):
        path = filedialog.askopenfilename(
            title="选择Telegram导出的JSON文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if path:
            self.json_path.set(path)
            self._preview_json(path)

    def _preview_json(self, json_path: str):
        try:
            data = JSONImporter.load_json(json_path)
            analysis = JSONImporter.analyze_json(data)

            info = (
                f"📁 文件: {json_path}\n"
                f"🏷️  群组名称: {analysis['chat_name']}\n"
                f"🔖 群组类型: {analysis['chat_type']} (ID: {analysis['chat_id']})\n"
                f"📊 消息总数: {analysis['total_messages']:,} 条"
            )

            self._set_text(self.info_text, info)
            self.status_label.config(text=f"已加载 {analysis['total_messages']:,} 条消息待导入", foreground=ACCENT)

        except Exception as e:
            messagebox.showerror("预览失败", f"无法读取JSON文件:\n{e}")

    def _set_text(self, text_widget: tk.Text, content: str):
        text_widget.config(state=tk.NORMAL)
        text_widget.delete('1.0', tk.END)
        text_widget.insert('1.0', content)
        text_widget.config(state=tk.DISABLED)

    def _clear_preview(self):
        self._set_text(self.info_text, '请选择一个Telegram导出的JSON文件...')
        self._set_text(self.result_text, '等待导入...')
        self.progress['value'] = 0
        self.status_label.config(text="就绪", foreground=TEXT_DIM)

    def _load_database(self):
        try:
            if self.db_manager:
                self.db_manager.close()

            self.db_manager = DatabaseManager(self.db_path.get())
            self.db_manager.connect()
            self.db_manager.init_tables()

            count = self.db_manager.get_message_count()
            chat_info = self.db_manager.get_chat_info()

            if chat_info:
                self.status_label.config(
                    text=f"数据库已连接: {chat_info[1]} | 已有 {count:,} 条消息",
                    foreground=SUCCESS
                )
            else:
                self.status_label.config(
                    text=f"数据库已创建，暂无数据（{count:,} 条消息）",
                    foreground=WARNING
                )

            self._refresh_stats()
            self._refresh_history()

        except Exception as e:
            messagebox.showerror("数据库错误", f"无法打开数据库:\n{e}")
            self.status_label.config(text=f"错误: {e}", foreground=ERROR)

    def _start_import(self):
        if self.is_importing:
            return

        json_path = self.json_path.get()
        if not json_path:
            messagebox.showwarning("提示", "请先选择一个JSON文件")
            return

        if not os.path.exists(json_path):
            messagebox.showerror("错误", "JSON文件不存在")
            return

        self.is_importing = True
        self.import_btn.config(state=tk.DISABLED)
        self.progress['value'] = 0
        self.status_label.config(text="正在导入...", foreground=WARNING)
        self._set_text(self.result_text, "开始导入...\n")

        thread = threading.Thread(target=self._do_import, args=(json_path,), daemon=True)
        thread.start()

    def _do_import(self, json_path: str):
        try:
            def on_progress(current, total, msg):
                self.after(0, self._update_progress, current, total, msg)

            result = JSONImporter.import_to_database(self.db_manager, json_path, on_progress)

            self.after(0, self._import_done, result, None)

        except Exception as e:
            self.after(0, self._import_done, None, str(e))

    def _update_progress(self, current: int, total: int, msg: str):
        try:
            if total > 0:
                self.progress['value'] = (current / total) * 100
            self.status_label.config(text=msg, foreground=ACCENT)
        except tk.TclError:
            pass

    def _import_done(self, result, error):
        try:
            self.is_importing = False
            self.import_btn.config(state=tk.NORMAL)

            if error:
                self.status_label.config(text=f"导入失败: {error}", foreground=ERROR)
                messagebox.showerror("导入失败", error)
                self._append_result(f"\n❌ 导入失败: {error}")
                return

            if result:
                self.progress['value'] = 100

                output = (
                    f"✅ 导入完成!\n\n"
                    f"📁 JSON文件: {os.path.basename(self.json_path.get())}\n"
                    f"🏷️  群组名称: {result['chat_name']}\n"
                    f"📊 JSON消息总数: {result['total_in_json']:,} 条\n\n"
                    f"📥 新导入: {result['imported_count']:,} 条\n"
                    f"⏭️  跳过(重复): {result['skipped_count']:,} 条\n"
                    f"📈 数据库总计: {self.db_manager.get_message_count():,} 条\n\n"
                    f"{'🎉 全新数据库，首次导入!' if result['is_new_db'] else '🔄 增量导入模式'}"
                )

                self._set_text(self.result_text, output)

                if result['imported_count'] > 0:
                    self.status_label.config(
                        text=f"导入成功! 新增 {result['imported_count']:,} 条，跳过 {result['skipped_count']:,} 条重复",
                        foreground=SUCCESS
                    )
                else:
                    self.status_label.config(
                        text=f"所有 {result['skipped_count']:,} 条消息均已存在，无需导入",
                        foreground=WARNING
                    )

                self._refresh_stats()
                self._refresh_history()
        except tk.TclError:
            pass

    def _append_result(self, text: str):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.insert(tk.END, text + '\n')
        self.result_text.see(tk.END)
        self.result_text.config(state=tk.DISABLED)

    def _refresh_stats(self):
        if not self.db_manager:
            return

        try:
            stats = self.db_manager.get_statistics()
            for key, label in self.stat_labels.items():
                value = stats.get(key, 0)
                label.config(text=f"{value:,}")
        except Exception:
            pass

    def _refresh_history(self):
        if not self.db_manager:
            return

        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        try:
            history = self.db_manager.get_import_history()
            for record in history:
                self.history_tree.insert('', 'end', values=(
                    record[1],
                    record[2],
                    f"{record[3]:,}",
                    f"{record[4]:,}",
                    f"{record[5]:,}",
                    record[6]
                ))
        except Exception as e:
            pass

    def _on_close(self):
        self.is_importing = False
        if self.db_manager:
            self.db_manager.close()
        self.destroy()


def main():
    app = TkinterApp()
    app.mainloop()


if __name__ == '__main__':
    main()
