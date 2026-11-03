"""WPS-style ribbon with nine functional tabs."""
from __future__ import annotations

from typing import Any, Callable, Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..theme import C
from .widgets import RibbonButton, RibbonGroup, ToolButton, VerticalSeparator

BLUE = "#2F6BFF"
GREEN = "#18A66F"
ORANGE = "#EE8A2E"
RED = "#E5484D"
PURPLE = "#7A5AF8"
YELLOW = "#D7A100"
SLATE = "#5C6577"
CYAN = "#0E9CB4"


def _spec(action: str, icon_name: str, text: str, color: str = SLATE, tooltip: str = "", checkable: bool = False, menu: list[tuple] | None = None) -> dict:
    return {
        "action": action,
        "icon": icon_name,
        "text": text,
        "color": color,
        "tooltip": tooltip,
        "checkable": checkable,
        "menu": menu,
    }


# The ribbon is intentionally declarative so the visual entry points remain
# easy to audit against WPS PDF's tab layout.
TABS: list[dict[str, Any]] = [
    {
        "key": "home",
        "title": "首页",
        "groups": [
            {
                "title": "文件",
                "large": [
                    _spec("file.open", "folder-open", "打开", BLUE),
                    _spec("file.save", "save", "保存", BLUE),
                ],
                "columns": [
                    [
                        _spec("file.save_as", "save-all", "另存为", SLATE),
                        _spec("file.print", "printer", "打印", SLATE),
                    ],
                    [
                        _spec("file.new", "file-plus", "新建", SLATE),
                        _spec("file.properties", "info", "属性", SLATE),
                    ],
                ],
            },
            {
                "title": "快速操作",
                "large": [
                    _spec("edit.undo", "undo-2", "撤销", SLATE),
                    _spec("edit.redo", "redo-2", "重做", SLATE),
                ],
                "columns": [
                    [
                        _spec("edit.find", "search", "查找", BLUE),
                        _spec("edit.replace", "replace", "替换", SLATE),
                    ],
                    [
                        _spec("edit.select_all", "text-select", "全选文本", SLATE),
                        _spec("edit.copy", "copy", "复制", SLATE),
                    ],
                ],
            },
            {
                "title": "阅读视图",
                "buttons": [
                    _spec("view.continuous", "rows-3", "连续阅读", BLUE, "连续滚动阅读", True),
                    _spec("view.single", "square", "单页", SLATE, "单页阅读", True),
                    _spec("view.double", "columns-2", "双页", SLATE, "双页并排", True),
                    _spec("view.fullscreen", "expand", "全屏", SLATE, "全屏阅读 (F11)", True),
                ],
            },
            {
                "title": "缩放",
                "buttons": [
                    _spec("view.zoom_out", "zoom-out", "缩小", SLATE),
                    _spec("view.zoom_in", "zoom-in", "放大", BLUE),
                    _spec("view.fit_width", "move-horizontal", "适合宽度", SLATE),
                    _spec("view.fit_page", "maximize-2", "适合页面", SLATE),
                    _spec("view.actual_size", "scan", "实际大小", SLATE),
                ],
            },
            {
                "title": "选择",
                "buttons": [
                    _spec("tool.select", "mouse-pointer-2", "选择文本", BLUE, "选择、复制文字或对象", True),
                    _spec("tool.hand", "hand", "手型工具", SLATE, "拖动画布", True),
                ],
            },
        ],
    },
    {
        "key": "edit",
        "title": "编辑",
        "groups": [
            {
                "title": "内容编辑",
                "large": [
                    _spec("edit.text", "type", "编辑文字", BLUE),
                    _spec("edit.image", "image", "插入图片", GREEN),
                    _spec("edit.textbox", "text-cursor-input", "文本框", PURPLE),
                ],
                "columns": [
                    [
                        _spec("edit.shape_rect", "square", "矩形", ORANGE),
                        _spec("edit.shape_ellipse", "circle", "椭圆", ORANGE),
                    ],
                    [
                        _spec("edit.shape_arrow", "move-up-right", "箭头", ORANGE),
                        _spec("edit.shape_line", "minus", "直线", ORANGE),
                    ],
                    [
                        _spec("edit.link", "link", "链接", CYAN),
                        _spec("edit.object_properties", "settings-2", "对象属性", SLATE),
                    ],
                ],
            },
            {
                "title": "页面装饰",
                "buttons": [
                    _spec("edit.watermark", "droplets", "水印", BLUE),
                    _spec("edit.background", "paint-bucket", "背景", CYAN),
                    _spec("edit.header", "panel-top", "页眉", SLATE),
                    _spec("edit.footer", "panel-bottom", "页脚", SLATE),
                    _spec("edit.page_number", "hash", "页码", PURPLE),
                ],
            },
            {
                "title": "对象",
                "buttons": [
                    _spec("edit.delete_object", "trash-2", "删除对象", RED),
                    _spec("edit.flatten", "layers", "拼合内容", SLATE),
                    _spec("edit.undo", "undo-2", "撤销", SLATE),
                    _spec("edit.redo", "redo-2", "重做", SLATE),
                ],
            },
            {
                "title": "高级",
                "buttons": [
                    _spec("edit.replace_all", "replace-all", "全文替换", PURPLE),
                    _spec("edit.metadata", "info", "文档属性", SLATE),
                    _spec("edit.fonts", "case-sensitive", "字体信息", SLATE),
                ],
            },
        ],
    },
    {
        "key": "page",
        "title": "页面",
        "groups": [
            {
                "title": "插入",
                "large": [
                    _spec("page.insert_blank", "file-plus-2", "插入空白页", BLUE),
                    _spec("page.insert_file", "file-input", "插入 PDF", GREEN),
                ],
                "columns": [
                    [
                        _spec("page.replace", "replace", "替换页面", SLATE),
                        _spec("page.duplicate", "copy-plus", "复制页面", SLATE),
                    ],
                    [
                        _spec("page.extract", "file-output", "提取页面", PURPLE),
                        _spec("page.merge", "combine", "合并文档", PURPLE),
                    ],
                ],
            },
            {
                "title": "页面管理",
                "buttons": [
                    _spec("page.delete", "trash-2", "删除页面", RED),
                    _spec("page.move", "move", "移动页面", SLATE),
                    _spec("page.rotate_left", "rotate-ccw", "左转 90°", SLATE),
                    _spec("page.rotate_right", "rotate-cw", "右转 90°", BLUE),
                    _spec("page.crop", "crop", "裁剪页面", ORANGE),
                ],
            },
            {
                "title": "拆分与合并",
                "buttons": [
                    _spec("page.split", "scissors", "拆分文档", PURPLE),
                    _spec("page.merge", "combine", "合并文档", PURPLE),
                    _spec("page.extract", "file-output", "提取页面", BLUE),
                ],
            },
            {
                "title": "页面设置",
                "buttons": [
                    _spec("page.size", "file-stack", "页面大小", CYAN),
                    _spec("page.orientation", "smartphone", "横竖切换", SLATE),
                    _spec("page.background", "paint-bucket", "页面背景", SLATE),
                    _spec("page.properties", "settings-2", "页面信息", SLATE),
                ],
            },
            {
                "title": "选择",
                "buttons": [
                    _spec("page.select_all", "list-checks", "全选页面", SLATE),
                    _spec("page.invert_selection", "flip-horizontal-2", "反选", SLATE),
                    _spec("page.export", "download", "导出页面", GREEN),
                ],
            },
        ],
    },
    {
        "key": "annot",
        "title": "注释",
        "groups": [
            {
                "title": "文本标注",
                "large": [
                    _spec("annot.highlight", "highlighter", "高亮", YELLOW, "拖动选择文字后高亮", True),
                    _spec("annot.underline", "underline", "下划线", BLUE, "为文字添加下划线", True),
                    _spec("annot.strike", "strikethrough", "删除线", RED, "为文字添加删除线", True),
                ],
                "columns": [
                    [
                        _spec("annot.squiggly", "waves", "波浪线", ORANGE, "波浪下划线", True),
                        _spec("annot.area_highlight", "scan", "区域高亮", YELLOW, "框选区域高亮", True),
                    ],
                    [
                        _spec("annot.color", "palette", "标注颜色", PURPLE),
                        _spec("annot.width", "pencil-ruler", "线宽", SLATE),
                    ],
                ],
            },
            {
                "title": "批注",
                "buttons": [
                    _spec("annot.sticky", "sticky-note", "便签", YELLOW, "在页面放置便签", True),
                    _spec("annot.note", "message-square-text", "文本注释", ORANGE, "添加批注气泡", True),
                    _spec("annot.textbox", "text-cursor-input", "文本框", PURPLE, "添加自由文本框", True),
                    _spec("annot.ink", "pen-line", "手绘", RED, "自由手绘标注", True),
                ],
            },
            {
                "title": "形状标注",
                "buttons": [
                    _spec("annot.rect", "square", "矩形", ORANGE, "添加矩形标注", True),
                    _spec("annot.ellipse", "circle", "椭圆", ORANGE, "添加椭圆标注", True),
                    _spec("annot.arrow", "move-up-right", "箭头", RED, "添加箭头标注", True),
                    _spec("annot.line", "minus", "直线", BLUE, "添加直线标注", True),
                ],
            },
            {
                "title": "图章与签名",
                "large": [
                    _spec("annot.stamp", "stamp", "图章", RED),
                    _spec("annot.signature", "signature", "签名", BLUE),
                ],
                "columns": [
                    [
                        _spec("annot.date", "calendar-days", "日期", SLATE),
                        _spec("annot.manage", "list-checks", "管理批注", SLATE),
                    ],
                    [
                        _spec("annot.export", "download", "导出批注", GREEN),
                        _spec("annot.flatten", "layers", "拼合批注", SLATE),
                    ],
                ],
            },
        ],
    },
    {
        "key": "tools",
        "title": "工具",
        "groups": [
            {
                "title": "文档工具",
                "large": [
                    _spec("tools.search", "search", "全文搜索", BLUE),
                    _spec("tools.ocr", "scan-text", "OCR 识别", GREEN),
                    _spec("tools.compress", "archive", "压缩文档", PURPLE),
                ],
                "columns": [
                    [
                        _spec("tools.bookmark", "bookmark", "书签", SLATE),
                        _spec("tools.attachment", "paperclip", "附件", SLATE),
                    ],
                    [
                        _spec("tools.compare", "git-compare-arrows", "比较文档", ORANGE),
                        _spec("tools.properties", "info", "文档属性", SLATE),
                    ],
                ],
            },
            {
                "title": "测量与捕获",
                "buttons": [
                    _spec("tools.measure", "ruler", "测量距离", CYAN, "在页面上测量距离", True),
                    _spec("tools.area", "spline", "测量面积", CYAN, "框选区域测量面积", True),
                    _spec("tools.screenshot", "camera", "截图", SLATE),
                    _spec("tools.export_images", "images", "导出图片", GREEN),
                ],
            },
            {
                "title": "页面处理",
                "buttons": [
                    _spec("tools.extract_images", "image-down", "提取图片", GREEN),
                    _spec("tools.export_text", "file-type-2", "导出文本", BLUE),
                    _spec("tools.print", "printer", "打印", SLATE),
                    _spec("tools.batch", "layers-2", "批量处理", PURPLE),
                ],
            },
            {
                "title": "修复与优化",
                "buttons": [
                    _spec("tools.repair", "wrench", "修复文档", SLATE),
                    _spec("tools.metadata_clean", "eraser", "清除元数据", RED),
                    _spec("tools.optimize", "gauge", "优化体积", PURPLE),
                ],
            },
        ],
    },
    {
        "key": "fill",
        "title": "填写与签署",
        "groups": [
            {
                "title": "填写表单",
                "large": [
                    _spec("form.fill", "text-cursor-input", "填写表单", BLUE),
                    _spec("form.manage", "list-checks", "管理表单", PURPLE),
                ],
                "columns": [
                    [
                        _spec("form.export", "file-output", "导出数据", GREEN),
                        _spec("form.reset", "rotate-ccw", "重置表单", SLATE),
                    ],
                ],
            },
            {
                "title": "添加控件",
                "buttons": [
                    _spec("form.text", "text-cursor", "文本域", BLUE, "拖动添加文本输入框", True),
                    _spec("form.checkbox", "square-check-big", "复选框", GREEN, "拖动添加复选框", True),
                    _spec("form.radio", "circle-dot", "单选按钮", GREEN, "拖动添加单选按钮", True),
                    _spec("form.dropdown", "chevrons-up-down", "下拉列表", CYAN, "拖动添加下拉列表", True),
                    _spec("form.signature", "signature", "签名域", PURPLE, "拖动添加签名域", True),
                ],
            },
            {
                "title": "签署",
                "large": [
                    _spec("sign.draw", "pen-tool", "手写签名", BLUE),
                    _spec("sign.upload", "image-up", "上传签名", GREEN),
                    _spec("sign.date", "calendar-days", "插入日期", SLATE),
                ],
                "columns": [
                    [
                        _spec("sign.stamp", "stamp", "签署图章", RED),
                        _spec("sign.initials", "user-round", "姓名缩写", PURPLE),
                    ],
                ],
            },
        ],
    },
    {
        "key": "protect",
        "title": "保护",
        "groups": [
            {
                "title": "文档安全",
                "large": [
                    _spec("protect.encrypt", "lock-keyhole", "加密文档", BLUE),
                    _spec("protect.permissions", "shield-check", "权限设置", PURPLE),
                    _spec("protect.decrypt", "lock-open", "解除密码", GREEN),
                ],
                "columns": [
                    [
                        _spec("protect.info", "shield", "安全信息", SLATE),
                        _spec("protect.certificate", "badge-check", "签名信息", SLATE),
                    ],
                ],
            },
            {
                "title": "内容安全",
                "buttons": [
                    _spec("protect.redact", "square-dashed", "密文涂黑", RED, "框选并永久移除内容", True),
                    _spec("protect.find_redact", "scan-search", "搜索密文", RED),
                    _spec("protect.metadata", "info", "元数据清理", ORANGE),
                    _spec("protect.flatten", "layers", "扁平化文档", SLATE),
                ],
            },
            {
                "title": "水印",
                "buttons": [
                    _spec("protect.watermark", "droplets", "文字水印", BLUE),
                    _spec("protect.watermark_image", "image", "图片水印", GREEN),
                    _spec("protect.watermark_manage", "settings-2", "水印设置", SLATE),
                ],
            },
            {
                "title": "签名与认证",
                "buttons": [
                    _spec("protect.sign", "signature", "文档签名", BLUE),
                    _spec("protect.timestamp", "clock", "时间戳", SLATE),
                    _spec("protect.info", "ellipsis", "更多安全", SLATE),
                ],
            },
        ],
    },
    {
        "key": "convert",
        "title": "转换",
        "groups": [
            {
                "title": "PDF 转其他格式",
                "large": [
                    _spec("convert.word", "file-text", "PDF 转 Word", BLUE),
                    _spec("convert.excel", "file-spreadsheet", "PDF 转 Excel", GREEN),
                    _spec("convert.ppt", "presentation", "PDF 转 PPT", ORANGE),
                ],
                "columns": [
                    [
                        _spec("convert.image", "file-image", "PDF 转图片", PURPLE),
                        _spec("convert.text", "file-type-2", "PDF 转文本", SLATE),
                    ],
                    [
                        _spec("convert.html", "file-code-2", "PDF 转 HTML", CYAN),
                        _spec("convert.extract_all", "package-open", "全部导出", SLATE),
                    ],
                ],
            },
            {
                "title": "其他格式转 PDF",
                "large": [
                    _spec("convert.images_pdf", "images", "图片转 PDF", GREEN),
                    _spec("convert.word_pdf", "file-text", "Word 转 PDF", BLUE),
                ],
                "columns": [
                    [
                        _spec("convert.excel_pdf", "file-spreadsheet", "Excel 转 PDF", GREEN),
                        _spec("convert.ppt_pdf", "presentation", "PPT 转 PDF", ORANGE),
                    ],
                ],
            },
            {
                "title": "批量与导出",
                "buttons": [
                    _spec("convert.batch", "layers-2", "批量转换", PURPLE),
                    _spec("convert.compress", "archive", "压缩 PDF", PURPLE),
                    _spec("convert.merge", "combine", "合并 PDF", BLUE),
                    _spec("convert.split", "scissors", "拆分 PDF", ORANGE),
                ],
            },
            {
                "title": "输出设置",
                "buttons": [
                    _spec("convert.options", "settings-2", "转换设置", SLATE),
                    _spec("convert.preview", "eye", "转换预览", SLATE),
                ],
            },
        ],
    },
    {
        "key": "ai",
        "title": "AI",
        "groups": [
            {
                "title": "智能阅读",
                "large": [
                    _spec("ai.summary", "sparkles", "智能摘要", PURPLE),
                    _spec("ai.outline", "list-tree", "生成大纲", BLUE),
                    _spec("ai.keywords", "tags", "提取关键词", GREEN),
                ],
            },
            {
                "title": "文档问答",
                "large": [
                    _spec("ai.qa", "messages-square", "全文问答", BLUE),
                    _spec("ai.selection_qa", "text-cursor-input", "选中提问", PURPLE),
                ],
                "columns": [
                    [
                        _spec("ai.explain", "lightbulb", "解释选中", ORANGE),
                        _spec("ai.rewrite", "wand-sparkles", "润色文字", PURPLE),
                    ],
                ],
            },
            {
                "title": "语言工具",
                "buttons": [
                    _spec("ai.translate", "languages", "全文翻译", CYAN),
                    _spec("ai.proofread", "spell-check-2", "拼写检查", GREEN),
                    _spec("ai.wordcount", "sigma", "字数统计", SLATE),
                ],
            },
            {
                "title": "模型",
                "buttons": [
                    _spec("ai.local", "cpu", "本地智能", GREEN, "查看本地 AI 工作方式"),
                    _spec("ai.about", "circle-help", "AI 说明", SLATE),
                ],
            },
        ],
    },
]


class RibbonBar(QWidget):
    command = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonHost")
        self._buttons: dict[str, list[RibbonButton]] = {}
        self._tab_buttons: dict[str, RibbonButton] = {}
        self._collapsed = False
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tab_row = QWidget(self)
        tab_row.setObjectName("RibbonTabs")
        tab_row.setFixedHeight(35)
        tab_layout = QHBoxLayout(tab_row)
        tab_layout.setContentsMargins(10, 0, 6, 0)
        tab_layout.setSpacing(0)
        self.tabbar = QTabBar(tab_row)
        self.tabbar.setObjectName("RibbonTabBar")
        self.tabbar.setDrawBase(False)
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(False)
        for tab in TABS:
            self.tabbar.addTab(tab["title"])
        self.tabbar.currentChanged.connect(self._on_tab_changed)
        tab_layout.addWidget(self.tabbar)
        tab_layout.addStretch(1)

        # A subtle original brand promise in the otherwise empty tab strip.
        self.tab_hint = QLabel("本地处理 · 文件不上传", tab_row)
        self.tab_hint.setStyleSheet(f"color:{C.TEXT_MUTED}; font-size:8pt; padding-right:8px;")
        tab_layout.addWidget(self.tab_hint)
        self.help_btn = ToolButton("circle-help", color=C.TEXT_MUTED, size=15, parent=tab_row)
        self.help_btn.setFixedSize(28, 28)
        self.help_btn.setToolTip("帮助与快捷键")
        self.help_btn.clicked.connect(lambda: self.command.emit("help.shortcuts"))
        tab_layout.addWidget(self.help_btn)
        self.collapse_btn = ToolButton("chevron-up", color=C.TEXT_MUTED, size=15, parent=tab_row)
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setToolTip("收起功能区")
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        tab_layout.addWidget(self.collapse_btn)
        outer.addWidget(tab_row)

        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFixedHeight(112)
        self.scroll.setStyleSheet(f"QScrollArea {{ background:{C.RIBBON}; }}")
        self.stack = QStackedWidget(self.scroll)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for tab in TABS:
            self.stack.addWidget(self._build_tab(tab))
        self.scroll.setWidget(self.stack)
        outer.addWidget(self.scroll)

    def _build_tab(self, tab: dict[str, Any]) -> QWidget:
        page = QWidget(self)
        page.setObjectName("Ribbon")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 1, 6, 1)
        layout.setSpacing(0)
        for group_index, group_spec in enumerate(tab["groups"]):
            group = RibbonGroup(group_spec["title"], parent=self)
            group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            for spec in group_spec.get("large", []):
                button = self._make_button(spec, large=True)
                group.add_button(button)
            large_buttons = len(group_spec.get("large", []))
            columns = list(group_spec.get("columns", []))
            buttons = list(group_spec.get("buttons", []))
            # Compact commands are arranged in short columns of at most three,
            # matching the dense WPS ribbon rather than one tall strip.
            if buttons:
                for start in range(0, len(buttons), 3):
                    columns.append(buttons[start : start + 3])
            for col_specs in columns:
                col = QWidget(group.body)
                col.setFixedHeight(78)
                col_layout = QVBoxLayout(col)
                col_layout.setContentsMargins(0, 0, 0, 0)
                col_layout.setSpacing(0)
                for spec in col_specs:
                    col_layout.addWidget(self._make_button(spec, large=False))
                col_layout.addStretch(1)
                group._body_layout.addWidget(col)
            layout.addWidget(group)
            if group_index < len(tab["groups"]) - 1:
                sep = VerticalSeparator(page)
                sep.setFixedHeight(70)
                layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return page

    def _make_button(self, spec: dict, large: bool) -> RibbonButton:
        menu = None
        if spec.get("menu"):
            menu = QMenu(self)
            for item in spec["menu"]:
                label, action = item[0], item[1]
                icon_name = item[2] if len(item) > 2 else ""
                if icon_name:
                    act = menu.addAction(icon(icon_name, C.TEXT_SUB, 15), label)
                else:
                    act = menu.addAction(label)
                act.triggered.connect(lambda checked=False, a=action: self.command.emit(a))
        button = RibbonButton(
            spec["action"],
            spec["icon"],
            spec["text"],
            large=large,
            color=spec.get("color", BLUE),
            tooltip=spec.get("tooltip", ""),
            checkable=bool(spec.get("checkable")),
            menu=menu,
            parent=self,
        )
        button.command.connect(self.command.emit)
        self._buttons.setdefault(spec["action"], []).append(button)
        return button

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def current_tab(self) -> str:
        index = self.tabbar.currentIndex()
        if 0 <= index < len(TABS):
            return str(TABS[index]["key"])
        return "home"

    def set_tab(self, key: str) -> None:
        for index, tab in enumerate(TABS):
            if tab["key"] == key:
                self.tabbar.setCurrentIndex(index)
                return

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self.scroll.setVisible(not self._collapsed)
        self.collapse_btn.set_icon("chevron-down" if self._collapsed else "chevron-up", C.TEXT_MUTED, 15)
        self.collapse_btn.setToolTip("展开功能区" if self._collapsed else "收起功能区")

    def set_checked(self, action: str, checked: bool) -> None:
        for button in self._buttons.get(action, []):
            button.setChecked(checked)

    def set_action_enabled(self, action: str, enabled: bool) -> None:
        for button in self._buttons.get(action, []):
            button.setEnabled(enabled)

    def set_actions_enabled(self, actions: Iterable[str], enabled: bool) -> None:
        for action in actions:
            self.set_action_enabled(action, enabled)

    def checked_actions(self) -> list[str]:
        out = []
        for action, buttons in self._buttons.items():
            if any(b.isChecked() for b in buttons):
                out.append(action)
        return out
