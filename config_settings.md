# 串口调试助手配置管理说明

## 概述

本项目使用 QSettings 进行配置管理，所有用户设置都会自动保存到系统配置文件中，并在下次启动时自动加载。

## 配置文件位置

配置文件使用 QSettings 的标准路径：
- Windows: `HKEY_CURRENT_USER\Software\Gavin\Gavin_com` (注册表)
- 或者: `%APPDATA%\Gavin\Gavin_com.ini`

## 配置项说明

### 串口设置
- `baud`: 波特率索引 (默认: 9)
- `data_bits`: 数据位索引 (默认: 0 = 8位)
- `stop_bits`: 停止位索引 (默认: 0 = 1位)
- `parity`: 校验位索引 (默认: 0 = 无校验)

### 发送设置
- `send_hex`: 是否以十六进制发送 (默认: false)
- `send_newline`: 是否发送换行符 (默认: true)
- `timer_send_enabled`: 是否启用定时发送 (默认: false)
- `timer_send_interval`: 定时发送间隔(毫秒) (默认: "1000")
- `send_data_text`: 发送数据文本内容 (默认: "")

### 接收设置
- `show_hex`: 是否以十六进制显示接收数据 (默认: false)
- `show_add_ctrl`: 是否显示控制字符 (默认: true)

### 流控设置
- `rts_enabled`: RTS流控是否启用 (默认: false)
- `dtr_enabled`: DTR流控是否启用 (默认: false)

### 协议设置
- `proto_send_edit`: 协议发送编辑框内容 (默认: "")
- `proto_recv_edit`: 协议接收编辑框内容 (默认: "")
- `proto_seq_edit`: 协议序列号编辑框内容 (默认: "0")
- `proto_pack_edit`: 协议打包编辑框内容 (默认: "")
- `proto_ack_index`: 协议ACK下拉框索引 (默认: 0)

### 过滤设置
- `filter_regexp`: 过滤正则表达式 (默认: "")

### 自定义按钮设置
- `groupBox_customs_data_1` 到 `groupBox_customs_data_99`: 自定义按钮1-99的文本内容
- `bt_customs_send_1` 到 `bt_customs_send_99`: 自定义按钮1-99的按钮文本

### 窗口状态
- `windows_customs_status`: 自定义按钮面板是否隐藏 (默认: true)
- `windows_kero_status`: 协议面板是否隐藏 (默认: true)

## 自动保存机制

### 实时保存
以下设置会在改变时立即保存：
- 串口参数 (波特率、数据位、停止位、校验位)
- 发送/接收选项 (十六进制、换行符、显示模式等)
- 定时发送间隔
- 过滤正则表达式
- 自定义按钮文本内容

### 程序退出时保存
程序退出时会调用 `save_all_settings()` 函数，保存所有当前设置状态。

## 配置加载

程序启动时会调用 `load_from_local()` 函数，从配置文件中加载所有设置并应用到界面控件。

## 配置重置

如需重置所有配置，可以：
1. 删除注册表项 `HKEY_CURRENT_USER\Software\Gavin\Gavin_com`
2. 或删除配置文件 `%APPDATA%\Gavin\Gavin_com.ini`
3. 重新启动程序即可恢复默认设置

## 开发说明

### 添加新配置项
1. 在 `load_from_local()` 函数中添加加载逻辑
2. 在 `save_all_settings()` 函数中添加保存逻辑
3. 如需实时保存，在 `InitUI()` 中连接相应信号

### 配置文件格式
使用 QSettings 的 INI 格式，自动处理数据类型转换和编码问题。