"""Generate the bundled demo PDF used for tours and screenshots."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample" / "欢迎使用星澜PDF.pdf"
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

BLUE = (0.184, 0.420, 1.0)
DARK = (0.118, 0.149, 0.220)
SUB = (0.361, 0.400, 0.478)
LIGHT = (0.945, 0.961, 0.992)
WHITE = (1, 1, 1)
GREEN = (0.094, 0.651, 0.435)
ORANGE = (0.933, 0.541, 0.180)
PURPLE = (0.478, 0.353, 0.973)


def text(page, rect, value, size=11, color=DARK, bold=False, align=0, font=None):
    page.insert_textbox(
        pymupdf.Rect(rect),
        value,
        fontsize=size,
        fontname="F0" if not bold else "F1",
        fontfile=FONT if not bold else FONT_BOLD,
        color=color,
        align=align,
    )


def line(page, p1, p2, color=(0.85, 0.88, 0.93), width=1):
    page.draw_line(p1, p2, color=color, width=width)


def card(page, rect, title, body, color):
    page.draw_rect(rect, color=(0.90, 0.92, 0.96), fill=WHITE, width=0.8, radius=0.08)
    page.draw_rect(pymupdf.Rect(rect.x0, rect.y0, rect.x0 + 5, rect.y1), color=None, fill=color)
    text(page, (rect.x0 + 18, rect.y0 + 14, rect.x1 - 14, rect.y0 + 38), title, 11.5, DARK, True)
    text(page, (rect.x0 + 18, rect.y0 + 44, rect.x1 - 14, rect.y1 - 10), body, 9.2, SUB)


def header(page, title, subtitle, number):
    page.draw_rect(pymupdf.Rect(0, 0, 595, 6), color=None, fill=BLUE)
    text(page, (48, 46, 500, 78), title, 22, DARK, True)
    text(page, (48, 82, 500, 104), subtitle, 10, SUB)
    text(page, (500, 48, 547, 64), f"{number:02d}", 10, (0.62, 0.66, 0.74), True, 2)
    line(page, (48, 114), (547, 114), (0.90, 0.92, 0.96), 0.8)
    line(page, (48, 802), (547, 802), (0.92, 0.94, 0.97), 0.6)
    text(page, (48, 808, 330, 824), "星澜 PDF  ·  本地离线 PDF 编辑器", 7.5, (0.62, 0.66, 0.74))
    text(page, (380, 808, 547, 824), f"第 {number} 页", 7.5, (0.62, 0.66, 0.74), align=2)


def make() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    # Cover -----------------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, color=None, fill=(0.953, 0.969, 1.0))
    page.draw_rect(pymupdf.Rect(0, 0, 595, 370), color=None, fill=BLUE)
    page.draw_circle((500, 54), 110, color=None, fill=(0.30, 0.49, 0.98))
    page.draw_circle((470, 330), 70, color=None, fill=(0.48, 0.36, 0.98))
    page.draw_rect(pymupdf.Rect(48, 58, 104, 114), color=None, fill=(1, 1, 1), radius=0.18)
    page.draw_rect(pymupdf.Rect(62, 72, 88, 100), color=None, fill=BLUE, radius=0.08)
    page.draw_rect(pymupdf.Rect(66, 78, 84, 82), color=None, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(66, 87, 84, 91), color=None, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(66, 96, 78, 100), color=None, fill=(1, 1, 1))
    text(page, (48, 140, 460, 196), "星澜 PDF", 36, WHITE, True)
    text(page, (48, 202, 470, 230), "像编辑文档一样编辑 PDF", 15, (0.88, 0.93, 1.0))
    text(page, (48, 250, 440, 330),
         "文字、图片、注释、页面管理、格式转换、OCR 与文档保护，\n"
         "所有处理都在本机完成。无需登录，无需会员，文件不上传。",
         10.5, (0.88, 0.93, 1.0))
    text(page, (48, 420, 500, 452), "产品体验文档", 17, DARK, True)
    text(page, (48, 458, 500, 480), "这是一份用于展示编辑、批注与页面操作效果的示例文件。", 9.5, SUB)
    line(page, (48, 496), (547, 496), (0.86, 0.89, 0.95), 0.8)
    items = [
        ("01", "直接编辑", "修改 PDF 中的文字与图片，保持原有排版。"),
        ("02", "审阅批注", "高亮、下划线、便签、手绘与图章。"),
        ("03", "页面管理", "插入、删除、旋转、拆分、合并与提取。"),
        ("04", "转换与 OCR", "PDF 与 Word、Excel、PPT、图片互转。"),
    ]
    y = 520
    for no, title, body in items:
        text(page, (48, y, 82, y + 22), no, 10, BLUE, True)
        text(page, (88, y, 300, y + 22), title, 10, DARK, True)
        text(page, (300, y, 547, y + 34), body, 8.6, SUB)
        y += 54
    text(page, (48, 770, 500, 790), "双击正文中的文字即可直接修改；选中文字可添加高亮或批注。", 8.5, (0.54, 0.58, 0.66))
    text(page, (48, 800, 500, 820), "星澜 PDF 1.0  ·  Stellar Studio  ·  本地离线处理", 8, (0.62, 0.66, 0.74))

    # Features --------------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    header(page, "一个界面，覆盖 PDF 全流程", "从阅读、编辑到转换与保护，所有入口都按使用场景组织。", 2)
    text(page, (48, 132, 547, 156), "核心能力", 12, DARK, True)
    cards = [
        ("文字与图片编辑", "双击文字即可改写；插入、替换或删除图片；\n支持中文、英文与多行文本。", BLUE),
        ("注释与审阅", "高亮、下划线、删除线、波浪线、区域高亮；\n便签、文本框、手绘、矩形、箭头与图章。", ORANGE),
        ("页面管理", "插入空白页或 PDF 页面；删除、复制、移动、\n旋转、裁剪、调整尺寸、提取与拆分合并。", PURPLE),
        ("格式转换", "PDF 与 Word、Excel、PPT、图片、文本、HTML\n互转；支持批量转换与压缩。", GREEN),
        ("表单与签名", "填写已有表单；添加文本域、复选框、下拉列表；\n手写、输入或上传签名。", (0.05, 0.56, 0.72)),
        ("安全与保护", "打开密码、权限密码、打印/复制限制；\n密文涂黑、元数据清理、水印与扁平化。", (0.90, 0.24, 0.30)),
    ]
    for i, (title, body, color) in enumerate(cards):
        col = i % 2
        row = i // 2
        rect = pymupdf.Rect(48 + col * 252, 168 + row * 168, 296 + col * 252, 320 + row * 168)
        card(page, rect, title, body, color)
    text(page, (48, 700, 547, 724), "扫描件也能编辑", 12, DARK, True)
    text(page, (48, 730, 547, 780),
         "内置本地 OCR 可识别中文与英文，将扫描页转换为可搜索 PDF，或添加隐藏文字层。\n"
         "识别过程不联网，适合处理合同、发票与内部资料。", 9.5, SUB)

    # Editing sample ---------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    header(page, "直接编辑与审阅", "下面的文字是真实可编辑的 PDF 文本，试试双击第一段。", 3)
    text(page, (48, 140, 547, 164), "项目背景", 13, DARK, True)
    body = (
        "在日常办公中，PDF 往往承担最终交付的角色。收到一份需要修改的 PDF 时，"
        "重新排版既耗时，又容易破坏原始格式。星澜 PDF 让文字修改像编辑普通文档一样直接："
        "双击段落，输入新的内容，原有字号、颜色与位置会尽量保留。"
    )
    text(page, (48, 174, 547, 250), body, 10.5, (0.22, 0.25, 0.31))
    text(page, (48, 268, 547, 292), "关键特性", 13, DARK, True)
    bullets = [
        "选择文本后，可一键添加高亮、下划线或删除线。",
        "使用便签记录审阅意见，批注会显示在左侧列表中。",
        "手绘工具适合圈选重点，图章可用于“已批准”“草稿”等状态。",
        "所有修改都可以通过 Ctrl+Z 撤销。",
    ]
    y = 304
    for bullet in bullets:
        page.draw_circle((56, y + 6), 2.2, color=None, fill=BLUE)
        text(page, (68, y, 547, y + 28), bullet, 10, (0.25, 0.28, 0.35))
        y += 34
    page.draw_rect(pymupdf.Rect(48, 468, 547, 608), color=(0.84, 0.89, 0.98), fill=(0.965, 0.975, 1.0), width=0.8, radius=0.04)
    page.draw_rect(pymupdf.Rect(48, 468, 53, 608), color=None, fill=BLUE)
    text(page, (70, 484, 530, 510), "试一试", 11.5, BLUE, True)
    text(page, (70, 516, 530, 590),
         "1. 双击“在日常办公中”这段文字，修改任意内容。\n"
         "2. 切换到“注释”选项卡，选择“高亮”，拖动选中一句话。\n"
         "3. 点击“便签”，在页面空白处写下你的审阅意见。",
         10, (0.25, 0.30, 0.40))
    text(page, (48, 640, 547, 664), "数据与表格", 13, DARK, True)
    rows = [
        ("处理能力", "本地引擎", "说明"),
        ("文字编辑", "支持", "保留字号、颜色与位置"),
        ("页面操作", "支持", "插入、删除、旋转、拆分与合并"),
        ("格式转换", "支持", "Word / Excel / PPT / 图片 / HTML"),
        ("OCR", "支持", "中文与英文，离线运行"),
    ]
    x0, y0 = 48, 676
    widths = [130, 110, 259]
    for r, row in enumerate(rows):
        y = y0 + r * 28
        if r == 0:
            page.draw_rect(pymupdf.Rect(x0, y, x0 + sum(widths), y + 28), color=None, fill=(0.93, 0.95, 0.99))
        elif r % 2 == 0:
            page.draw_rect(pymupdf.Rect(x0, y, x0 + sum(widths), y + 28), color=None, fill=(0.985, 0.99, 1.0))
        line(page, (x0, y + 28), (x0 + sum(widths), y + 28), (0.90, 0.92, 0.96), 0.5)
        x = x0
        for c, value in enumerate(row):
            text(page, (x + 8, y + 7, x + widths[c] - 8, y + 24), value, 8.8, DARK if r == 0 else (0.28, 0.31, 0.38), r == 0)
            x += widths[c]
    for x in (x0 + 130, x0 + 240):
        line(page, (x, y0), (x, y0 + 28 * len(rows)), (0.90, 0.92, 0.96), 0.5)

    # Page management -------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    header(page, "页面管理，像整理纸张一样简单", "在左侧缩略图中多选页面，即可批量删除、旋转、提取或导出。", 4)
    text(page, (48, 136, 547, 160), "常用页面操作", 13, DARK, True)
    ops_cards = [
        ("插入", "空白页、PDF 页面\n可指定插入位置", BLUE),
        ("删除", "删除选中页面\n自动保留至少一页", (0.90, 0.24, 0.30)),
        ("旋转", "左转 / 右转 90°\n适合横向扫描件", ORANGE),
        ("裁剪", "按边距裁剪\n隐藏不需要的区域", PURPLE),
        ("拆分", "每 N 页或按范围\n生成多个 PDF", GREEN),
        ("合并", "多个 PDF 排序后\n合并为一个文件", (0.05, 0.56, 0.72)),
    ]
    for i, (title, body, color) in enumerate(ops_cards):
        col = i % 3
        row = i // 3
        rect = pymupdf.Rect(48 + col * 168, 174 + row * 140, 202 + col * 168, 294 + row * 140)
        card(page, rect, title, body, color)
    text(page, (48, 470, 547, 494), "页面尺寸与方向", 13, DARK, True)
    page.draw_rect(pymupdf.Rect(48, 506, 300, 724), color=(0.86, 0.89, 0.95), fill=(0.975, 0.98, 1.0), width=0.8)
    text(page, (66, 522, 282, 548), "A4  ·  纵向", 12, DARK, True)
    text(page, (66, 554, 282, 620), "595 × 842 pt\n210 × 297 mm", 10, SUB)
    page.draw_rect(pymupdf.Rect(318, 506, 547, 724), color=(0.86, 0.89, 0.95), fill=(0.975, 0.98, 1.0), width=0.8)
    text(page, (336, 522, 530, 548), "A4  ·  横向", 12, DARK, True)
    text(page, (336, 554, 530, 620), "842 × 595 pt\n297 × 210 mm", 10, SUB)
    text(page, (48, 748, 547, 778), "提示：在缩略图面板按住 Ctrl 或 Shift 可多选页面。", 8.8, (0.54, 0.58, 0.66))

    # Conversion ------------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    header(page, "转换与 OCR", "在“转换”选项卡中选择目标格式，输出文件会保存到你指定的位置。", 5)
    text(page, (48, 136, 547, 160), "支持的格式", 13, DARK, True)
    formats = [
        ("PDF → Word", "保留段落与文字样式", BLUE),
        ("PDF → Excel", "自动识别页面表格", GREEN),
        ("PDF → PPT", "每页生成一张幻灯片", ORANGE),
        ("PDF → 图片", "PNG / JPG / WEBP，最高 600 DPI", PURPLE),
        ("PDF → HTML", "适合网页发布与检索", (0.05, 0.56, 0.72)),
        ("Office → PDF", "Word / Excel / PPT 本地排版", (0.90, 0.24, 0.30)),
    ]
    for i, (title, body, color) in enumerate(formats):
        col = i % 2
        row = i // 2
        rect = pymupdf.Rect(48 + col * 252, 174 + row * 96, 296 + col * 252, 254 + row * 96)
        card(page, rect, title, body, color)
    page.draw_rect(pymupdf.Rect(48, 480, 547, 690), color=(0.86, 0.89, 0.95), fill=(0.965, 0.975, 1.0), width=0.8, radius=0.04)
    text(page, (68, 498, 520, 524), "本地 OCR 工作方式", 11.5, DARK, True)
    text(page, (68, 532, 520, 650),
         "1. 选择页面范围与渲染精度（默认 200 DPI）。\n"
         "2. 本地模型识别中文、英文、数字与常见符号。\n"
         "3. 可输出可搜索 PDF、纯文本，或直接在当前文档中添加隐藏文字层。\n\n"
         "识别过程不需要联网，适合扫描合同、发票、书籍与内部资料。",
         9.6, (0.25, 0.30, 0.40))
    text(page, (48, 714, 547, 738), "输出建议", 11.5, DARK, True)
    text(page, (48, 744, 547, 790),
         "• 需要继续编辑文字：优先转换为 Word。\n"
         "• 需要保留版式：转换为图片或 PDF。\n"
         "• 扫描件：先 OCR，再转换或全文搜索。",
         9.2, SUB)

    # Closing ---------------------------------------------------------------
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, color=None, fill=(0.953, 0.969, 1.0))
    page.draw_rect(pymupdf.Rect(0, 0, 595, 300), color=None, fill=BLUE)
    page.draw_circle((510, 260), 120, color=None, fill=(0.30, 0.49, 0.98))
    text(page, (48, 86, 500, 126), "开始使用", 28, WHITE, True)
    text(page, (48, 136, 500, 174), "打开你的第一份 PDF，或从示例文档开始。", 12, (0.88, 0.93, 1.0))
    steps = [
        ("1", "打开 PDF", "点击“打开”，或将文件拖入窗口。"),
        ("2", "编辑与批注", "双击文字修改；用注释工具标记重点。"),
        ("3", "保存与导出", "Ctrl+S 保存；在“转换”中输出其他格式。"),
    ]
    y = 360
    for no, title, body in steps:
        page.draw_circle((78, y + 24), 22, color=None, fill=BLUE)
        text(page, (58, y + 14, 98, y + 36), no, 14, WHITE, True, 1)
        text(page, (120, y + 4, 500, y + 30), title, 13, DARK, True)
        text(page, (120, y + 34, 500, y + 62), body, 10, SUB)
        y += 100
    page.draw_rect(pymupdf.Rect(48, 690, 547, 764), color=(0.84, 0.89, 0.98), fill=WHITE, width=0.8, radius=0.04)
    text(page, (68, 706, 520, 732), "本地处理，文件不上传", 11.5, BLUE, True)
    text(page, (68, 736, 520, 754), "星澜 PDF 不要求登录，也不会把文档内容发送到网络。", 9.2, SUB)

    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.set_metadata({
        "title": "欢迎使用星澜 PDF",
        "author": "Stellar Studio",
        "subject": "星澜 PDF 产品体验文档",
        "keywords": "PDF,编辑器,OCR,转换,批注,星澜",
        "creator": "Stellar PDF Demo Builder",
        "producer": "PyMuPDF",
    })
    doc.save(OUT, garbage=3, deflate=True)
    doc.close()
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    make()
