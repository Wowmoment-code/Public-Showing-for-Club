# 星澜 PDF（StellarPDF）

一款面向 Windows 的本地离线 PDF 编辑器。界面按照主流办公软件的操作习惯设计，提供与 WPS PDF 相近的功能分区：**首页、编辑、页面、注释、工具、填写与签署、保护、转换、AI**。品牌名、图标与视觉素材均为原创设计，不包含第三方商标或图标资源。

> 最终程序：工作区根目录 `星澜PDF.exe`（启动器，无需安装）。
> 主程序与全部源码、构建脚本、示例文档位于 `StellarPDF/`。
>
> 根目录启动器会把 `TEMP` / `TMP` 指向 `StellarPDF/runtime/temp`，再启动
> `StellarPDF/bin/星澜PDF_主程序.exe`。这样即使系统临时目录被权限策略或安全软件拦截，
> 单文件主程序也能正常解压运行。

---

## 功能一览

| 模块 | 已实现能力 |
|---|---|
| 阅读 | 连续阅读、单页、双页、全屏、缩放、适合宽度/页面、实际大小、页面跳转、缩略图 |
| 文字 | 双击直接编辑文字，保留字号/颜色/位置；插入文字、文本框、粘贴文字、全文查找替换 |
| 图片 | 插入图片、替换页面中已有图片、删除图片、保持比例 |
| 注释 | 高亮、下划线、删除线、波浪线、区域高亮、便签、文本注释、自由文本框、手绘、矩形、椭圆、箭头、直线、图章 |
| 页面 | 插入空白页/PDF 页面、删除、复制、移动、拖拽排序、旋转、裁剪、调整页面大小、横竖切换、提取、拆分、合并、替换页面、导出 |
| 转换 | PDF → Word / Excel / PPT / 图片（PNG/JPG/WEBP）/ 文本 / HTML；图片、Word、Excel、PPT → PDF；批量转换；全部格式导出 |
| OCR | 基于 RapidOCR + ONNX Runtime 的本地中英文 OCR；可输出可搜索 PDF、纯文本或添加隐藏文字层 |
| 表单 | 填写已有表单、导出表单数据、重置表单；添加文本域、复选框、单选、下拉、签名域 |
| 签名 | 手写签名、输入签名、上传图片签名、姓名缩写、日期、签署图章 |
| 保护 | AES-256/AES-128 打开密码与权限密码；打印/复制/修改/批注/表单/提取/拼合权限；解除密码；密文涂黑；搜索密文；元数据清理 |
| 装饰 | 文字水印、图片水印、平铺水印、页面背景、页眉页脚、页码、文档属性 |
| 工具 | 全文搜索、书签、附件、压缩、比较文档、距离/面积测量、截图、导出图片/文本、批量处理、修复文档、优化体积 |
| AI | 本地智能摘要、结构大纲、关键词、全文问答、选中提问、文字整理建议、字数统计 |
| 其他 | 撤销/重做、最近文档、拖放打开、打印、快捷键、全屏 |

### 像 WPS 一样改文字

选中一段文字后，页面旁会出现浮动工具条：**编辑文字 / 高亮 / 复制**。
点击“编辑文字”后，再点击正文中的任意文字，**光标会直接出现在原文字上**，
没有弹窗、没有输入框边框：

- 编辑器的字号、字族、颜色、行距、对齐方式尽量与原文一致；
- 按 `Ctrl+Enter` 应用，按 `Esc` 取消，点击页面其他位置也会应用；
- 应用前自动保存页面/文档快照，`Ctrl+Z` 可撤销；
- 只替换当前段落，不再把整段文字拆成前后两截；
- 替换文字时优先使用原 PDF 的字体族（微软雅黑、宋体、黑体、楷体、仿宋、Arial、Times 等），
  保留字号、颜色、粗细与行距，避免“改一句话，整段字体都变了”。

阅读区的滚轮按每格约 110 px 滚动，触控板支持像素级滚动；`Ctrl+滚轮` 缩放。
左侧缩略图改为按需渲染，只绘制当前页和屏幕可见页，打开几百页的大文档时不会再
把所有页面同时渲染而造成卡顿。

### 设计上的取舍

- **完全离线**：文档内容不会上传。AI 标签页是本地抽取式算法，不依赖云端大模型；因此不包含在线翻译。
- **格式转换**：PDF 转 Word/Excel/PPT 优先保证文字、表格、图片与页面顺序，复杂多栏排版、特殊字体、公式、图表可能被简化。扫描件建议先 OCR。
- **签名**：提供视觉签名与签名域，不包含 CA 证书链/可信时间戳。如需法律效力的数字签名，请使用专用证书签章系统。
- **界面**：布局、入口与配色参考 WPS PDF 的操作习惯，但所有图形、品牌与图标均为原创或使用 Lucide（ISC 许可）图标。

---

## 运行

直接双击根目录的 **`星澜PDF.exe`**（启动器）。

- 请保持根目录启动器与 `StellarPDF` 文件夹在同一目录，不要只移动启动器。
- 支持 Windows 10/11 64 位。
- 首次启动单文件主程序需要解压运行时，可能等待几秒。
- 启动器会自动使用项目内可写临时目录，不依赖系统 `%TEMP%` 的权限。
- 打开、拖入 PDF 或点击“打开 PDF”即可开始。
- 示例文档：`StellarPDF/sample/欢迎使用星澜PDF.pdf`，也可从“关于/帮助”中找到。

## 开发与构建

```powershell
cd StellarPDF
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launch.py
```

构建单文件 EXE：

```powershell
cd StellarPDF
.\build.ps1
```

构建脚本会把主程序复制到 `StellarPDF/bin/星澜PDF_主程序.exe`，再编译根目录的
`星澜PDF.exe` 启动器。启动器负责设置项目内临时目录并启动主程序。

### 主要依赖

- PySide6（Qt 6）
- PyMuPDF（PDF 渲染/编辑）
- Pillow
- python-docx / openpyxl / python-pptx / ReportLab
- RapidOCR + ONNX Runtime（离线 OCR）
- Lucide 图标（ISC License）

## 源码结构

```
StellarPDF/
  app/
    main.py              应用入口、截图模式
    config.py            路径、品牌、字体
    theme.py             Qt 样式表
    icons.py             SVG 图标与原创 Logo
    core/
      document.py        PDF 文档模型、渲染、撤销快照
      operations.py      文字/图片/注释/页面/表单/安全操作
      convert.py         格式转换
      ocr.py             本地 OCR
      ai.py              本地摘要/问答/关键词
      compare.py         文本级文档比较
    ui/
      main_window.py     主窗口与全部命令分发
      titlebar.py        标题栏、快速访问、文件菜单
      ribbon.py          九大功能区的声明式定义
      sidebar.py         缩略图/书签/批注/表单/附件/搜索
      viewer.py          连续画布、文本选择、工具交互
      statusbar.py       页码、视图、缩放
      welcome.py         欢迎页与最近文档
      dialogs.py         各类对话框
      worker.py          长任务线程
  assets/icons/lucide/   开源图标
  bin/星澜PDF_主程序.exe 实际主程序（单文件）
  launcher/Program.cs    根目录启动器源码
  sample/                示例 PDF
  tools/                 演示文档生成、测试、截图脚本
  build.ps1              PyInstaller + 启动器构建
  StellarPDF.spec        打包配置
```

## 快捷键

| 操作 | 快捷键 |
|---|---|
| 打开 | Ctrl+O |
| 新建 | Ctrl+N |
| 保存 / 另存为 | Ctrl+S / Ctrl+Shift+S |
| 打印 | Ctrl+P |
| 撤销 / 重做 | Ctrl+Z / Ctrl+Y |
| 查找 / 替换 | Ctrl+F / Ctrl+H |
| 适合页面 | Ctrl+0 |
| 放大 / 缩小 | Ctrl++ / Ctrl+- |
| 全屏 | F11 |
| 关闭文档 | Ctrl+W |

## 许可与声明

本项目为独立实现，不使用 WPS 的商标、图标或源代码。界面参考仅用于满足“相似操作路径”的产品需求。Lucide 图标遵循 ISC License，许可文件位于 `app/assets/icons/LICENSE-lucide.txt`。
