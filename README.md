# Gavin_com 串口调试助手

<p align="center">
  <img src="res/sscom.ico" width="64" alt="icon"/>
</p>

<p align="center">
  基于 <strong>PySide6 (Qt for Python)</strong> 开发的跨平台串口调试工具，适用于 Windows / macOS / Linux。
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-blue"/>
  <img alt="PySide6" src="https://img.shields.io/badge/PySide6-6.4%2B-green"/>
  <img alt="License" src="https://img.shields.io/badge/license-MIT-orange"/>
  <img alt="Version" src="https://img.shields.io/badge/version-1.0.0.69-informational"/>
</p>

---

## 功能特性

### 串口通信
- 自定义波特率、数据位、校验位、停止位
- RTS / DTR 硬件流控
- 串口意外断开后**自动重连**（可配置超时，默认 5 秒）

### 数据收发
- HEX / 字符串 双模式发送与接收
- 自动换行（`\r\n` / `\n` 可选）
- 定时循环发送
- 顺序发送（多条指令按序依次执行）
- **多字符串快捷按钮**（最多 99 条，支持 HEX、延迟、顺序编号）
- **顶部快捷按钮栏**（可配置颜色、标签、发送内容）

### 显示与过滤
- 多标签页实时过滤（正则 / 关键词 / 大小写 / 反转模式）
- 收发统计（字节数 / 速率实时显示），支持右键清零
- 多主题配色切换（深色 / 浅色 / 护眼绿等）
- 按键盘 ↓ 可在接收区直接输入发送

### 自动应答
- 支持字符串 / HEX 匹配规则
- 多条规则，可单独启用 / 禁用

### 日志与导入导出
- 自动保存接收日志（可配置路径和格式）
- 兼容 SSCOM `.ini` 格式：一键导入 / 导出多字符串配置

### 高级设置
- 扩展面板（多字符串 / 快捷按钮栏）可折叠
- 底部串口配置区可折叠，最大化接收区显示
- 串口设置弹窗（独立对话框，支持端口刷新）

---

## 快速开始

### 环境依赖

```
Python >= 3.10
PySide6 >= 6.4.0
pyserial >= 3.5
psutil >= 5.9.0
pywin32 >= 227   # 仅 Windows
```

### 安装依赖

```bash
pip install -r requirements.txt
```

### 直接运行

```bash
python main.py
```

---

## 打包为可执行文件

项目已配置 `Gavin_com.spec`，使用 PyInstaller 打包：

```bash
# 方式一：一键脚本
python oneclick_build.py

# 方式二：手动
pyinstaller Gavin_com.spec
```

打包输出位于 `dist/Gavin_com/`。

---

## 项目结构

```
Gavin_SSCOM/
├── main.py                  # 主程序入口 & 业务逻辑
├── UI_Serial.py             # Qt UI 布局定义
├── Uart/
│   ├── UartSerial.py        # 底层串口操作（基于 pyserial）
│   └── uart_thread.py       # 串口收发线程 & 自动重连
├── widget/
│   ├── AdvancedFunctionDialog.py   # 高级功能弹窗（日志/系统设置）
│   ├── AutoReplyDialog.py          # 自动应答规则编辑器
│   ├── AutoReplyEngine.py          # 自动应答引擎
│   ├── MultistringWidget.py        # 多字符串面板控件
│   ├── MultistringAdapter.py       # 多字符串适配器（集成到主窗口）
│   ├── QuickButtonBar.py           # 顶部快捷按钮栏
│   ├── SerialSettingsDialog.py     # 串口参数设置弹窗
│   ├── MyTextBrowser.py            # 增强型接收显示控件
│   ├── MineWidget.py               # 主窗口中心控件
│   ├── MyHexQlineText.py           # HEX 输入框
│   ├── MyQComBox.py                # 自定义下拉框
│   └── UserPushButton.py           # 支持双击的按钮
├── logger.py                # 日志管理器
├── monitor.py               # 系统性能监控
├── config_manager.py        # 配置管理
├── data_sender.py           # 数据发送辅助
├── requirements.txt
├── Gavin_com.spec           # PyInstaller 打包配置
└── res/
    └── sscom.ico            # 应用图标
```

---

## License

MIT License
