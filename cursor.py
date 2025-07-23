import json
import os
import sys
import uuid
import random
import platform
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText


class CursorResetterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Cursor ID 重置工具")
        self.root.geometry("600x400")
        self.root.resizable(False, False)

        # 设置窗口图标（如果有的话）
        # self.root.iconbitmap('icon.ico')

        self.setup_ui()
        self.resetter = CursorResetter(self.log)

    def setup_ui(self):
        """设置UI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="Cursor ID 重置工具",
            font=('Arial', 16, 'bold')
        )
        title_label.grid(row=0, column=0, pady=10)

        # 说明文本
        desc_text = """此工具用于重置 Cursor 编辑器的设备识别码。
使用前请确保：
1. Cursor 已完全关闭
2. 已备份重要数据
3. 具有足够的文件访问权限"""

        desc_label = ttk.Label(
            main_frame,
            text=desc_text,
            wraplength=550,
            justify=tk.LEFT
        )
        desc_label.grid(row=1, column=0, pady=10)

        # 重置按钮
        self.reset_button = ttk.Button(
            main_frame,
            text="开始重置",
            command=self.reset_ids
        )
        self.reset_button.grid(row=2, column=0, pady=10)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="5")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        self.log_text = ScrolledText(
            log_frame,
            width=60,
            height=10,
            wrap=tk.WORD
        )
        self.log_text.pack(expand=True, fill=tk.BOTH)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN
        )
        status_bar.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)

    def log(self, message):
        """添加日志信息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def reset_ids(self):
        """重置ID的操作"""
        self.reset_button.state(['disabled'])
        self.status_var.set("正在重置...")
        self.log("开始重置过程...")

        try:
            if self.resetter.update_config():
                messagebox.showinfo("成功", "重置完成！请重启 Cursor 以使更改生效。")
                self.status_var.set("重置完成")
            else:
                messagebox.showerror("错误", "重置过程中发生错误，请查看日志。")
                self.status_var.set("重置失败")
        except Exception as e:
            messagebox.showerror("错误", f"发生异常：{str(e)}")
            self.status_var.set("发生错误")
        finally:
            self.reset_button.state(['!disabled'])


class CursorResetter:
    def __init__(self, log_func):
        self.log_func = log_func
        self.config_path = self.get_config_path()

    def get_config_path(self):
        """获取配置文件路径"""
        system = platform.system().lower()

        if system == "windows":
            base_path = os.getenv("APPDATA")
            return Path(base_path) / "Cursor" / "User" / "globalStorage" / "storage.json"

        elif system == "darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "storage.json"

        elif system == "linux":
            return Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "storage.json"

        else:
            raise OSError(f"不支持的操作系统: {system}")

    def generate_hex_id(self, length=64):
        """生成指定长度的十六进制ID"""
        return ''.join(random.choices('0123456789abcdef', k=length))

    def generate_uuid(self):
        """生成UUID格式的ID"""
        return str(uuid.uuid4())

    def make_writable(self, path):
        """设置文件为可写"""
        try:
            os.chmod(path, 0o666)
            self.log_func("已设置文件为可写")
            return True
        except Exception as e:
            self.log_func(f"设置文件权限失败: {e}")
            return False

    def make_readonly(self, path):
        """设置文件为只读"""
        try:
            os.chmod(path, 0o444)
            self.log_func("已设置文件为只读")
            return True
        except Exception as e:
            self.log_func(f"设置文件只读失败: {e}")
            return False

    def update_config(self):
        """更新配置文件"""
        try:
            self.log_func(f"配置文件路径: {self.config_path}")

            if not self.config_path.exists():
                self.log_func("配置文件不存在！")
                return False

            if not self.make_writable(self.config_path):
                return False

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.log_func("已读取现有配置")

            new_mac_id = self.generate_hex_id()
            new_machine_id = self.generate_hex_id()
            new_device_id = self.generate_uuid()

            config.update({
                "telemetry.macMachineId": new_mac_id,
                "telemetry.machineId": new_machine_id,
                "telemetry.devDeviceId": new_device_id
            })

            self.log_func(f"新的 macMachineId: {new_mac_id}")
            self.log_func(f"新的 machineId: {new_machine_id}")
            self.log_func(f"新的 devDeviceId: {new_device_id}")

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
                self.log_func("已写入新配置")

            if not self.make_readonly(self.config_path):
                return False

            self.log_func("配置更新完成")
            return True

        except Exception as e:
            self.log_func(f"更新配置时出错: {e}")
            return False


def main():
    root = tk.Tk()
    app = CursorResetterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()