#!/bin/python3
__version__ = "1.3.1"
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QFontComboBox, QSpinBox, QCheckBox, QDialogButtonBox, QWidget, QPushButton, QLabel, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView
    from PyQt6.QtGui import QIcon, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QFontMetrics, QAction, QKeySequence, QPainter, QImage, QTextCursor
    from PyQt6.QtCore import QRegularExpression, Qt, QSettings, QRect, QSize, QTimer
    from asmcc import AssemblyCraftCompiler
    import argparse
    import struct
    import ctypes
    import asmcc
    import tempfile
    import time
    import sys
    import os
except ImportError:
    print(f"\033[91;1mError> A python library is missing, make sure all the libraries are installed!\033[00m")
    sys.exit(127)

reg = {
    'rax': 0, 'rbx': 1, 'rcx': 2, 'rdx': 3,
    'rsi': 4, 'rdi': 5, 'rbp': 6, 'rsp': 7,
    'r8': 8,  'r9': 9,  'r10': 10, 'r11': 11,
    'r12': 12, 'r13': 13, 'r14': 14, 'r15': 15,

    'arg1': 5, 'arg2': 4, 'arg3': 3, 'arg4': 10, 'arg5': 8, 'arg6': 9,
    'ret': 0
}

VRAM_GRAPHICS = 0xA0000
VRAM_TEXT = 0xB8000
MMIO_KEYBOARD = 0xFF000
MMIO_KEY_STATUS = 0xFF001
MMIO_TIMER = 0xFF004
MMIO_DISPLAY_MODE = 0xFF008
MMIO_DISK_SECTOR = 0xFF010
MMIO_DISK_ADDR = 0xFF014
MMIO_DISK_CMD = 0xFF018

VGA_COLORS = [
    QColor(0x00, 0x00, 0x00), QColor(0x00, 0x00, 0xAA), QColor(0x00, 0xAA, 0x00), QColor(0x00, 0xAA, 0xAA),
    QColor(0xAA, 0x00, 0x00), QColor(0xAA, 0x00, 0xAA), QColor(0xAA, 0x55, 0x00), QColor(0xAA, 0xAA, 0xAA),
    QColor(0x55, 0x55, 0x55), QColor(0x55, 0x55, 0xFF), QColor(0x55, 0xFF, 0x55), QColor(0x55, 0xFF, 0xFF),
    QColor(0xFF, 0x55, 0x55), QColor(0xFF, 0x55, 0xFF), QColor(0xFF, 0xFF, 0x55), QColor(0xFF, 0xFF, 0xFF)
]

def _info(message: str):
    for i in message.splitlines():
        print(f"\033[96;1mInfo>\033[00m\033[96m {i}\033[00m")

def _warning(message: str):
    for i in message.splitlines():
        print(f"\033[93;1mWarning>\033[00m\033[93m {i}\033[00m")

def _error(message: str):
    for i in message.splitlines():
        print(f"\033[91;1mError> {i}\033[00m")
    sys.exit(1)

class VirtualMachine:
    def __init__(self, binary_path: str, output_callback=None, input_callback=None, cls_callback=None, video_write_callback=None):
        with open(binary_path, "rb") as f:
            self.binary_data = f.read()

        if self.binary_data[:4] != AssemblyCraftCompiler.MAGIC_HEADER:
            _error(f"Invalid binary format. Expected '{AssemblyCraftCompiler.MAGIC_HEADER.decode()}' header.")

        var_count, text_offset = struct.unpack("<HI", self.binary_data[4:10])
        
        self.var_table = {}
        offset = 10
        for _ in range(var_count):
            var_id, raw_name, val_offset, alloc_len = struct.unpack("<B16sIH", self.binary_data[offset:offset+23])
            self.var_table[var_id] = self.binary_data[val_offset : val_offset + alloc_len]
            offset += 23

        self.bytecode = self.binary_data[text_offset:]
        
        self.output_callback = output_callback
        self.input_callback = input_callback
        self.cls_callback = cls_callback
        self.video_write_callback = video_write_callback

        self.reset()

    def reset(self):
        self.ram = bytearray(1024 * 1024)
        self.regs = [0] * 16
        self.regs[7] = 0x07FFE
        self.ip = 0
        self.zf = False
        self.sf = False
        self.halted = False

        self.var_ram_addrs = {}
        for var_id, val in self.var_table.items():
            ram_addr = 0x01000 + (var_id * 0x00100)
            self.ram[ram_addr : ram_addr + len(val)] = val
            self.var_ram_addrs[var_id] = ram_addr

        code_start = 0x08000
        bc_len = len(self.bytecode)
        self.ram[code_start : code_start + bc_len] = self.bytecode

        self.cursor_x = 0
        self.cursor_y = 0
        self._init_vga_text_mode()

    def _init_vga_text_mode(self):
        for i in range(80 * 25):
            idx = VRAM_TEXT + i * 2
            self.ram[idx] = 0x20
            self.ram[idx + 1] = 0x0A

    def read_mem(self, addr: int, size: int = 4) -> int:
        if MMIO_TIMER <= addr < MMIO_TIMER + 4:
            ticks = int(time.time() * 1000) & 0xFFFFFFFF
            struct.pack_into("<I", self.ram, MMIO_TIMER, ticks)

        addr = addr % len(self.ram)
        if size == 1:
            return self.ram[addr]
        elif size == 2:
            return struct.unpack_from("<H", self.ram, addr)[0]
        elif size == 4:
            return struct.unpack_from("<i", self.ram, addr)[0]
        elif size == 8:
            return struct.unpack_from("<q", self.ram, addr)[0]
        return 0

    def write_mem(self, addr: int, val: int, size: int = 4):
        addr = addr % len(self.ram)
        if size == 1:
            self.ram[addr] = val & 0xFF
        elif size == 2:
            struct.pack_into("<H", self.ram, addr, val & 0xFFFF)
        elif size == 4:
            struct.pack_into("<i", self.ram, addr, val & 0xFFFFFFFF)
        elif size == 8:
            struct.pack_into("<q", self.ram, addr, val)

        if addr == MMIO_DISK_CMD:
            self._process_disk_cmd()

    def _process_disk_cmd(self):
        cmd = self.ram[MMIO_DISK_CMD]
        if cmd == 1:
            sector = self.read_mem(MMIO_DISK_SECTOR, 4)
            target_addr = self.read_mem(MMIO_DISK_ADDR, 4)
            data_offset = (sector * 512) % len(self.binary_data)
            sector_data = self.binary_data[data_offset : data_offset + 512]
            target_addr = target_addr % len(self.ram)
            self.ram[target_addr : target_addr + len(sector_data)] = sector_data
            self.ram[MMIO_DISK_CMD] = 0

    def _resolve(self, op_type: int, op_val: int) -> int:
        if op_type == 1:
            return self.regs[op_val]
        elif op_type == 2:
            if op_val in self.var_ram_addrs:
                return self.var_ram_addrs[op_val]
            return op_val
        elif op_type == 3:
            return op_val
        return 0

    def _deref(self, val) -> str:
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='ignore').rstrip('\x00\n')
        if isinstance(val, str):
            return val
        if isinstance(val, int):
            if 0 <= val < len(self.ram):
                buf = bytearray()
                curr = val
                while curr < len(self.ram) and self.ram[curr] != 0:
                    buf.append(self.ram[curr])
                    curr += 1
                if buf:
                    return buf.decode('utf-8', errors='ignore')
            if 1 <= val <= 255:
                return chr(val)
        return str(val)

    def _vga_write_str(self, x: int, y: int, text: str, attr: int = 0x0A):
        x = x % 80
        y = y % 25
        for i, ch in enumerate(text):
            cx = (x + i) % 80
            cy = y + (x + i) // 80
            if cy >= 25:
                break
            idx = VRAM_TEXT + (cy * 80 + cx) * 2
            self.ram[idx] = ord(ch) & 0xFF
            self.ram[idx + 1] = attr & 0xFF

    def _vga_append_str(self, text: str):
        for ch in text:
            if ch == '\n':
                self.cursor_x = 0
                self.cursor_y += 1
            elif ch == '\r':
                self.cursor_x = 0
            else:
                idx = VRAM_TEXT + (self.cursor_y * 80 + self.cursor_x) * 2
                self.ram[idx] = ord(ch) & 0xFF
                self.ram[idx + 1] = 0x0A
                self.cursor_x += 1
                if self.cursor_x >= 80:
                    self.cursor_x = 0
                    self.cursor_y += 1

            if self.cursor_y >= 25:
                self.ram[VRAM_TEXT : VRAM_TEXT + 80 * 24 * 2] = self.ram[VRAM_TEXT + 80 * 2 : VRAM_TEXT + 80 * 25 * 2]
                for c in range(80):
                    idx = VRAM_TEXT + (24 * 80 + c) * 2
                    self.ram[idx] = 0x20
                    self.ram[idx + 1] = 0x0A
                self.cursor_y = 24

    def step(self) -> bool:
        bc_start = 0x08000
        bc_len = len(self.bytecode)

        if self.halted or self.ip >= bc_len:
            return False

        curr_ram_ip = bc_start + self.ip
        op = self.ram[curr_ram_ip]
        self.ip += 1

        if op == 0x01:
            d_type, d_val = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            s_type, s_val = self.ram[curr_ram_ip + 6], struct.unpack_from("<i", self.ram, curr_ram_ip + 7)[0]
            self.ip += 10
            val = self._resolve(s_type, s_val)
            if d_type == 1:
                self.regs[d_val] = val

        elif op == 0x02:
            s_type, s_val = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            self.ip += 5
            val = self._resolve(s_type, s_val)
            self.regs[7] -= 4
            self.write_mem(self.regs[7], val, 4)

        elif op == 0x03:
            d_type, d_val = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            self.ip += 5
            rsp = self.regs[7]
            val = self.read_mem(rsp, 4)
            self.regs[7] += 4
            if d_type == 1:
                self.regs[d_val] = val

        elif op == 0x04:
            t_type, t_val = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            self.ip += 5
            target = self._resolve(t_type, t_val)
            self.regs[7] -= 4
            self.write_mem(self.regs[7], self.ip, 4)
            self.ip = target

        elif op == 0x05:
            rsp = self.regs[7]
            self.ip = self.read_mem(rsp, 4)
            self.regs[7] += 4

        elif op == 0x06:
            a1_t, a1_v = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            a2_t, a2_v = self.ram[curr_ram_ip + 6], struct.unpack_from("<i", self.ram, curr_ram_ip + 7)[0]
            self.ip += 10
            v1, v2 = self._resolve(a1_t, a1_v), self._resolve(a2_t, a2_v)
            self.zf = (v1 == v2)
            self.sf = (v1 < v2)

        elif op == 0x07:
            t_t, t_v = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            self.ip = self._resolve(t_t, t_v)

        elif 0x08 <= op <= 0x0D:
            t_t, t_v = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            self.ip += 5
            target = self._resolve(t_t, t_v)
            
            cond = (
                (op == 0x08 and self.zf) or
                (op == 0x09 and not self.zf) or
                (op == 0x0A and not self.zf and not self.sf) or
                (op == 0x0B and self.sf and not self.zf) or
                (op == 0x0C and not self.sf) or
                (op == 0x0D and (self.sf or self.zf))
            )
            if cond:
                self.ip = target

        elif 0x0E <= op <= 0x12:
            d_t, d_v = self.ram[curr_ram_ip + 1], struct.unpack_from("<i", self.ram, curr_ram_ip + 2)[0]
            s_t, s_v = self.ram[curr_ram_ip + 6], struct.unpack_from("<i", self.ram, curr_ram_ip + 7)[0]
            self.ip += 10

            if d_t == 1:
                v1, v2 = self.regs[d_v], self._resolve(s_t, s_v)
                if op == 0x0E: self.regs[d_v] = v1 ^ v2
                elif op == 0x0F: self.regs[d_v] = v1 + v2
                elif op == 0x10: self.regs[d_v] = v1 - v2
                elif op == 0x11: self.regs[d_v] = v1 * v2
                elif op == 0x12:
                    if v2 == 0:
                        _error(f"Division by zero at IP: {self.ip - 11}")
                    self.regs[d_v] = v1 // v2

        elif op == 0x13:
            sys_num = self.regs[0]
            if sys_num == 0:
                self.halted = True
            elif sys_num == 1:
                msg = self._deref(self.regs[5])
                self._vga_append_str(msg)
                if self.output_callback:
                    self.output_callback(msg)
            elif sys_num == 2:
                if self.ram[MMIO_KEY_STATUS] == 1:
                    ch = self.ram[MMIO_KEYBOARD]
                    self.ram[MMIO_KEY_STATUS] = 0
                    self.regs[0] = ch
                elif self.input_callback:
                    ch = self.input_callback()
                    self.regs[0] = ord(ch) if isinstance(ch, str) and ch else (ch if isinstance(ch, int) else 0)
                else:
                    self.regs[0] = 0
            elif sys_num == 3:
                self.regs[0] = self.read_mem(MMIO_TIMER, 4)
            elif sys_num == 4:
                self._init_vga_text_mode()
                self.cursor_x, self.cursor_y = 0, 0
                if self.cls_callback:
                    self.cls_callback()
            elif sys_num == 5:
                x = self.regs[4]
                y = self.regs[3]
                text = self._deref(self.regs[5])
                self._vga_write_str(x, y, text)
                if self.video_write_callback:
                    self.video_write_callback(x, y, text)
            else:
                _error(f"Unhandled Machine Interrupt #{sys_num} at IP: {self.ip - 1}")

        return not self.halted and self.ip < bc_len

    def run(self):
        while self.step():
            pass

def compile_asmc(asmc_file_path: str, asmcx_file_path: str):
    if not os.path.isfile(asmc_file_path):
        _error(f"Unable to open file {asmc_file_path}!")
    if os.path.exists(asmcx_file_path):
        _warning(f"{asmcx_file_path} already exists!")
        inp = ""
        while inp.lower() not in ("y", "n", "yes", "no"):
            inp = input("Do you want to overwrite the file (Y/n)> ")

        if inp.lower() not in ("y", "yes"):
            sys.exit(0)

    with open(asmc_file_path, "r") as f:
        asmc_file = f.read()

    compiler = AssemblyCraftCompiler()
    compiler.compile(asmc_file, asmcx_file_path)

def execute_asmc(asmcx_file_path: str):
    if not os.path.isfile(asmcx_file_path):
        _error(f"Unable to open file '{asmcx_file_path}'!")
    vm = VirtualMachine(asmcx_file_path)
    vm.run()

def resource_path(*relative_paths: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, *relative_paths)

open_windows = []

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class AsmcCodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab_size = 4
        self.base_font_size = 11
        self.show_line_numbers = True

        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width()

    def wheelEvent(self, event):
        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
            return

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.angleDelta().x()

            if delta != 0:
                h_bar = self.horizontalScrollBar()
                h_bar.setValue(h_bar.value() - delta)
                event.accept()
                return

        super().wheelEvent(event)

    def zoom_in(self, range_val: int = 1):
        self.zoomIn(range_val)
        self.set_tab_size(self.tab_size)
        self.update_line_number_area_width()

    def zoom_out(self, range_val: int = 1):
        if self.font().pointSize() > 4:
            self.zoomOut(range_val)
            self.set_tab_size(self.tab_size)
            self.update_line_number_area_width()

    def reset_zoom(self):
        font = self.font()
        font.setPointSize(self.base_font_size)
        self.setFont(font)
        self.set_tab_size(self.tab_size)
        self.update_line_number_area_width()

    def line_number_area_width(self) -> int:
        if not self.show_line_numbers:
            return 0
        digits = max(1, len(str(self.blockCount())))
        space = 12 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, newBlockCount: int = 0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        if not self.show_line_numbers:
            return

        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1e1e1e"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                
                if block_number == self.textCursor().blockNumber():
                    painter.setPen(QColor("#CCCCCC"))
                else:
                    painter.setPen(QColor("#6E7681"))

                painter.setFont(self.font())
                painter.drawText(
                    0, top, 
                    self.line_number_area.width() - 6, 
                    self.fontMetrics().height(), 
                    Qt.AlignmentFlag.AlignRight, 
                    number
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        self.line_number_area.update()

    def set_line_numbers_visible(self, visible: bool):
        self.show_line_numbers = visible
        self.line_number_area.setVisible(visible)
        self.update_line_number_area_width()
        self.viewport().update()

    def set_editor_font(self, family: str, size: int):
        self.base_font_size = size
        font = QFont(family, size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.set_tab_size(self.tab_size)
        self.update_line_number_area_width()

    def set_tab_size(self, spaces: int):
        self.tab_size = spaces
        font_metrics = QFontMetrics(self.font())
        self.setTabStopDistance(self.tab_size * font_metrics.horizontalAdvance(' '))

    def set_word_wrap(self, wrap: bool):
        if wrap:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.insertPlainText(" " * self.tab_size)
        else:
            super().keyPressEvent(event)


class AsmcSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        c_keyword  = QColor("#C586C0")
        c_section  = QColor("#C586C0")
        c_function = QColor("#DCDCAA")
        c_register = QColor("#4FC1FF")
        c_storage  = QColor("#569CD6")
        c_variable = QColor("#9CDCFE")
        c_number   = QColor("#B5CEA8")
        c_string   = QColor("#CE9178")
        c_comment  = QColor("#6A9955")

        fmt_keyword = QTextCharFormat(); fmt_keyword.setForeground(c_keyword); fmt_keyword.setFontWeight(QFont.Weight.Bold)
        fmt_section = QTextCharFormat(); fmt_section.setForeground(c_section); fmt_section.setFontWeight(QFont.Weight.Bold)
        fmt_function = QTextCharFormat(); fmt_function.setForeground(c_function)
        fmt_register = QTextCharFormat(); fmt_register.setForeground(c_register)
        fmt_storage = QTextCharFormat(); fmt_storage.setForeground(c_storage)
        fmt_variable = QTextCharFormat(); fmt_variable.setForeground(c_variable)
        fmt_number = QTextCharFormat(); fmt_number.setForeground(c_number)
        fmt_string = QTextCharFormat(); fmt_string.setForeground(c_string)
        fmt_comment = QTextCharFormat(); fmt_comment.setForeground(c_comment)

        self.rules.append({
            "pattern": QRegularExpression(r"^\s*(section\s+\.(?:data|text))\b"),
            "formats": [(1, fmt_section)]
        })

        self.rules.append({
            "pattern": QRegularExpression(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+\b(ds|dm|db)\b"),
            "formats": [(1, fmt_variable), (2, fmt_storage)]
        })

        self.rules.append({
            "pattern": QRegularExpression(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:"),
            "formats": [(1, fmt_function)]
        })

        keywords_regex = r"\b(mov|push|pop|call|ret|cmp|jmp|je|jne|jg|jl|jge|jle|xor|add|sub|mul|div|syscall)\b"
        self.rules.append({
            "pattern": QRegularExpression(keywords_regex),
            "formats": [(0, fmt_keyword)]
        })

        registers_regex = r"\b(rax|rbx|rcx|rdx|rsi|rdi|rbp|rsp|r[8-9]|r1[0-5])\b"
        self.rules.append({
            "pattern": QRegularExpression(registers_regex),
            "formats": [(0, fmt_register)]
        })

        self.rules.append({
            "pattern": QRegularExpression(r"\b(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)\b"),
            "formats": [(0, fmt_number)]
        })

        self.rules.append({
            "pattern": QRegularExpression(r'".*?"'),
            "formats": [(0, fmt_string)]
        })

        self.rules.append({
            "pattern": QRegularExpression(r";.*$"),
            "formats": [(0, fmt_comment)]
        })

    def highlightBlock(self, text: str):
        for rule in self.rules:
            match_iterator = rule["pattern"].globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                for group_idx, fmt in rule["formats"]:
                    start = match.capturedStart(group_idx)
                    length = match.capturedLength(group_idx)
                    if start >= 0 and length > 0:
                        self.setFormat(start, length, fmt)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(380, 250)

        self.settings = QSettings("ASMCEditor", "Preferences")

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.font_combo = QFontComboBox()
        self.font_combo.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        saved_font = self.settings.value("font_family", "Consolas", type=str)
        self.font_combo.setCurrentFont(QFont(saved_font))
        form_layout.addRow("Font Family:", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 72)
        self.font_size_spin.setValue(self.settings.value("font_size", 11, type=int))
        form_layout.addRow("Font Size:", self.font_size_spin)

        self.tab_size_spin = QSpinBox()
        self.tab_size_spin.setRange(1, 16)
        self.tab_size_spin.setValue(self.settings.value("tab_size", 4, type=int))
        form_layout.addRow("Tab Indent (Spaces):", self.tab_size_spin)

        self.word_wrap_cb = QCheckBox("Enable Word Wrap")
        self.word_wrap_cb.setChecked(self.settings.value("word_wrap", False, type=bool))
        form_layout.addRow("", self.word_wrap_cb)

        self.line_numbers_cb = QCheckBox("Show Line Numbers")
        self.line_numbers_cb.setChecked(self.settings.value("line_numbers", True, type=bool))
        form_layout.addRow("", self.line_numbers_cb)

        layout.addLayout(form_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.save_settings)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def save_settings(self):
        self.settings.setValue("font_family", self.font_combo.currentFont().family())
        self.settings.setValue("font_size", self.font_size_spin.value())
        self.settings.setValue("tab_size", self.tab_size_spin.value())
        self.settings.setValue("word_wrap", self.word_wrap_cb.isChecked())
        self.settings.setValue("line_numbers", self.line_numbers_cb.isChecked())

        for win in open_windows:
            if hasattr(win, "load_settings"):
                win.load_settings()

    def accept(self):
        self.save_settings()
        super().accept()


class VMDisplayWidget(QWidget):
    def __init__(self, ram_ref, parent=None):
        super().__init__(parent)
        self.ram = ram_ref
        self.setMinimumSize(640, 400)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        text = event.text()
        key_code = ord(text[0]) if text else event.key()
        if 0 <= key_code <= 255:
            self.ram[MMIO_KEYBOARD] = key_code
            self.ram[MMIO_KEY_STATUS] = 1
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        mode = self.ram[MMIO_DISPLAY_MODE]

        if mode == 1:
            img = QImage(320, 200, QImage.Format.Format_Indexed8)
            for i in range(256):
                c = VGA_COLORS[i % 16]
                img.setColor(i, c.rgb())

            frame_data = bytes(self.ram[VRAM_GRAPHICS : VRAM_GRAPHICS + 64000])
            img_bytes = img.bits()
            if img_bytes is not None:
                img_bytes.setsize(64000)
                img_bytes[:len(frame_data)] = frame_data

            scaled = img.scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio)
            ox = (self.width() - scaled.width()) // 2
            oy = (self.height() - scaled.height()) // 2
            painter.fillRect(self.rect(), QColor(10, 10, 10))
            painter.drawImage(ox, oy, scaled)
        else:
            painter.fillRect(self.rect(), QColor(12, 12, 12))
            cw = self.width() / 80.0
            ch = self.height() / 25.0
            font = QFont("Consolas", max(8, int(ch * 0.7)))
            painter.setFont(font)

            for y in range(25):
                for x in range(80):
                    idx = VRAM_TEXT + (y * 80 + x) * 2
                    char_byte = self.ram[idx]
                    attr_byte = self.ram[idx + 1]

                    bg_idx = (attr_byte >> 4) & 0x0F
                    fg_idx = attr_byte & 0x0F

                    rx = int(x * cw)
                    ry = int(y * ch)
                    rw = int(cw) + 1
                    rh = int(ch) + 1

                    if bg_idx != 0:
                        painter.fillRect(QRect(rx, ry, rw, rh), VGA_COLORS[bg_idx])

                    if char_byte > 32:
                        painter.setPen(VGA_COLORS[fg_idx])
                        painter.drawText(QRect(rx, ry, rw, rh), Qt.AlignmentFlag.AlignCenter, chr(char_byte))


class VMWindow(QMainWindow):
    def __init__(self, icon_path: str = "", asmcx_file_path: str = None):
        super().__init__()
        open_windows.append(self)

        self.icon_path = icon_path
        self.asmcx_file_path = asmcx_file_path

        self.setWindowTitle(f"ASMC Machine Emulator - {os.path.basename(asmcx_file_path or 'No File')}")
        if self.icon_path and os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(str(self.icon_path)))
        self.resize(1000, 680)

        self.vm = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._emulate_cycles)

        self._init_ui()

        if self.asmcx_file_path and os.path.isfile(self.asmcx_file_path):
            self._load_vm(self.asmcx_file_path)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        
        self.btn_run = QPushButton("▶ Run")
        self.btn_run.clicked.connect(self.start_vm)
        top_bar.addWidget(self.btn_run)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self.pause_vm)
        top_bar.addWidget(self.btn_pause)

        self.btn_step = QPushButton("⏭ Step")
        self.btn_step.clicked.connect(self.step_vm)
        top_bar.addWidget(self.btn_step)

        self.btn_reset = QPushButton("🔄 Reset")
        self.btn_reset.clicked.connect(self.reset_vm)
        top_bar.addWidget(self.btn_reset)

        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("font-weight: bold; padding-left: 10px;")
        top_bar.addWidget(self.status_label)

        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        screen_widget = QWidget()
        screen_layout = QVBoxLayout(screen_widget)
        screen_layout.setContentsMargins(0, 0, 0, 0)

        screen_label = QLabel("Bare-Metal Hardware Display Monitor:")
        screen_label.setStyleSheet("font-weight: bold;")
        screen_layout.addWidget(screen_label)

        dummy_ram = bytearray(1024 * 1024)
        self.display_canvas = VMDisplayWidget(dummy_ram)
        screen_layout.addWidget(self.display_canvas)

        splitter.addWidget(screen_widget)

        reg_widget = QWidget()
        reg_layout = QVBoxLayout(reg_widget)
        reg_layout.setContentsMargins(0, 0, 0, 0)

        reg_label = QLabel("CPU Registers & Machine State:")
        reg_label.setStyleSheet("font-weight: bold;")
        reg_layout.addWidget(reg_label)

        self.reg_table = QTableWidget()
        self.reg_table.setColumnCount(2)
        self.reg_table.setHorizontalHeaderLabels(["Register", "Value (Hex / Dec)"])
        self.reg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.reg_table.verticalHeader().setVisible(False)
        self.reg_table.setFont(QFont("Consolas", 10))
        reg_layout.addWidget(self.reg_table)

        splitter.addWidget(reg_widget)
        splitter.setSizes([650, 350])

        main_layout.addWidget(splitter, 1)

    def _load_vm(self, path: str):
        try:
            self.vm = VirtualMachine(
                binary_path=path,
                output_callback=None,
                input_callback=None,
                cls_callback=None,
                video_write_callback=None
            )
            self.display_canvas.ram = self.vm.ram
            self._update_register_view()
            self.display_canvas.update()
            self.status_label.setText("Status: Ready")
        except Exception as e:
            QMessageBox.critical(self, "VM Load Error", f"Failed to load binary:\n{e}")

    def _emulate_cycles(self):
        if not self.vm:
            return

        for _ in range(50):
            running = self.vm.step()
            if not running:
                self.pause_vm()
                if self.vm.halted:
                    self.status_label.setText("Status: Halted (SYS_HALT)")
                else:
                    self.status_label.setText("Status: Execution Finished")
                break

        self.display_canvas.update()
        self._update_register_view()

    def start_vm(self):
        if self.vm and not self.vm.halted:
            self.timer.start(10)
            self.status_label.setText("Status: Running")

    def pause_vm(self):
        self.timer.stop()
        if self.vm and not self.vm.halted:
            self.status_label.setText("Status: Paused")

    def step_vm(self):
        if self.vm and not self.vm.halted:
            running = self.vm.step()
            if not running:
                if self.vm.halted:
                    self.status_label.setText("Status: Halted (SYS_HALT)")
                else:
                    self.status_label.setText("Status: Execution Finished")
            else:
                self.status_label.setText(f"Status: Stepped to IP={self.vm.ip}")
            self.display_canvas.update()
            self._update_register_view()

    def reset_vm(self):
        self.timer.stop()
        if self.asmcx_file_path:
            self._load_vm(self.asmcx_file_path)

    def _update_register_view(self):
        if not self.vm:
            return

        reg_names = [
            'rax (ret)', 'rbx', 'rcx (arg3)', 'rdx (arg4)',
            'rsi (arg2)', 'rdi (arg1)', 'rbp', 'rsp',
            'r8 (arg5)', 'r9 (arg6)', 'r10', 'r11',
            'r12', 'r13', 'r14', 'r15'
        ]

        rows = len(reg_names) + 3
        self.reg_table.setRowCount(rows)

        for i, name in enumerate(reg_names):
            val = self.vm.regs[i]
            self.reg_table.setItem(i, 0, QTableWidgetItem(name))
            self.reg_table.setItem(i, 1, QTableWidgetItem(f"0x{val & 0xFFFFFFFF:08X} ({val})"))

        self.reg_table.setItem(16, 0, QTableWidgetItem("IP (Instruction Ptr)"))
        self.reg_table.setItem(16, 1, QTableWidgetItem(f"0x{self.vm.ip:04X} ({self.vm.ip})"))

        self.reg_table.setItem(17, 0, QTableWidgetItem("ZF (Zero Flag)"))
        self.reg_table.setItem(17, 1, QTableWidgetItem(str(self.vm.zf)))

        self.reg_table.setItem(18, 0, QTableWidgetItem("SF (Sign Flag)"))
        self.reg_table.setItem(18, 1, QTableWidgetItem(str(self.vm.sf)))

    def closeEvent(self, event):
        self.timer.stop()
        if self in open_windows:
            open_windows.remove(self)
        super().closeEvent(event)


class EditorWindow(QMainWindow):
    def __init__(self, icon_path: str = "", asmc_file_path: str = None):
        super().__init__()

        open_windows.append(self)

        self.icon_path = icon_path
        self.current_file_path = asmc_file_path

        if self.icon_path and os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(str(self.icon_path)))
        self.resize(800, 600)

        self.editor = AsmcCodeEditor()
        self.setCentralWidget(self.editor)

        self.load_settings()

        self.highlighter = AsmcSyntaxHighlighter(self.editor.document())

        self._create_menu_bar()

        self.editor.document().modificationChanged.connect(self._update_window_title)

        if self.current_file_path:
            self._load_file(self.current_file_path)
        else:
            self.editor.document().setModified(False)
            self._update_window_title()

    def _update_window_title(self, modified: bool = False):
        path_str = self.current_file_path if self.current_file_path else "Untitled"
        star = "*" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"ASMC Editor - {path_str}{star}")

    def load_settings(self):
        settings = QSettings("ASMCEditor", "Preferences")
        font_family = settings.value("font_family", "Consolas", type=str)
        font_size = settings.value("font_size", 11, type=int)
        tab_size = settings.value("tab_size", 4, type=int)
        word_wrap = settings.value("word_wrap", False, type=bool)
        line_numbers = settings.value("line_numbers", True, type=bool)

        self.editor.set_editor_font(font_family, font_size)
        self.editor.set_tab_size(tab_size)
        self.editor.set_word_wrap(word_wrap)
        self.editor.set_line_numbers_visible(line_numbers)

    def closeEvent(self, event):
        if self in open_windows:
            open_windows.remove(self)
        super().closeEvent(event)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        new_act = QAction("&New Window", self)
        new_act.setShortcut(QKeySequence("Ctrl+N"))
        new_act.triggered.connect(self.open_new_window)
        file_menu.addAction(new_act)

        open_act = QAction("&Open...", self)
        open_act.setShortcut(QKeySequence("Ctrl+O"))
        open_act.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_act)

        save_act = QAction("&Save", self)
        save_act.setShortcut(QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self.save_file)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save &As...", self)
        save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_act.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        edit_menu = menu_bar.addMenu("&Edit")

        undo_act = QAction("&Undo", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self.editor.undo)
        edit_menu.addAction(undo_act)

        redo_act = QAction("&Redo", self)
        redo_act.setShortcut(QKeySequence.StandardKey.Redo)
        redo_act.triggered.connect(self.editor.redo)
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        cut_act = QAction("Cu&t", self)
        cut_act.setShortcut(QKeySequence.StandardKey.Cut)
        cut_act.triggered.connect(self.editor.cut)
        edit_menu.addAction(cut_act)

        copy_act = QAction("&Copy", self)
        copy_act.setShortcut(QKeySequence.StandardKey.Copy)
        copy_act.triggered.connect(self.editor.copy)
        edit_menu.addAction(copy_act)

        paste_act = QAction("&Paste", self)
        paste_act.setShortcut(QKeySequence.StandardKey.Paste)
        paste_act.triggered.connect(self.editor.paste)
        edit_menu.addAction(paste_act)

        run_menu = menu_bar.addMenu("&Run")

        run_act = QAction("&Run Software", self)
        run_act.setShortcut(QKeySequence("F5"))
        run_act.triggered.connect(self.run_software)
        run_menu.addAction(run_act)

        compile_act = QAction("&Compile Software...", self)
        compile_act.setShortcut(QKeySequence("Ctrl+B"))
        compile_act.triggered.connect(self.compile_software)
        run_menu.addAction(compile_act)

        view_menu = menu_bar.addMenu("&View")

        zoom_in_act = QAction("Zoom &In", self)
        zoom_in_act.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        zoom_in_act.triggered.connect(self.editor.zoom_in)
        view_menu.addAction(zoom_in_act)

        zoom_out_act = QAction("Zoom &Out", self)
        zoom_out_act.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_act.triggered.connect(self.editor.zoom_out)
        view_menu.addAction(zoom_out_act)

        reset_zoom_act = QAction("&Reset Zoom", self)
        reset_zoom_act.setShortcut(QKeySequence("Ctrl+0"))
        reset_zoom_act.triggered.connect(self.editor.reset_zoom)
        view_menu.addAction(reset_zoom_act)

        settings_menu = menu_bar.addMenu("&Settings")
        pref_act = QAction("&Preferences...", self)
        pref_act.triggered.connect(self.open_settings)
        settings_menu.addAction(pref_act)

    def run_software(self):
        code = self.editor.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Warning", "Cannot run empty code.")
            return
        try:
            temp_dir = tempfile.gettempdir()
            temp_bin = os.path.join(temp_dir, f".temp_{os.getpid()}_{int(time.time())}.asmcx")
            compiler = AssemblyCraftCompiler()
            compiler.compile(code, temp_bin)
            vm_win = VMWindow(self.icon_path, temp_bin)
            vm_win.show()
            vm_win.start_vm()
        except Exception as e:
            QMessageBox.critical(self, "Execution Error", f"Failed to compile and run:\n{e}")

    def compile_software(self):
        code = self.editor.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Warning", "Cannot compile empty code.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Compile ASMC File", "", "ASMCX Files (*.asmcx);;All Files (*)"
        )
        if path:
            if not path.endswith(".asmcx"):
                path += ".asmcx"
            try:
                compiler = AssemblyCraftCompiler()
                compiler.compile(code, path)
                QMessageBox.information(self, "Success", f"Successfully compiled to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Compile Error", f"Failed to compile:\n{e}")

    def open_new_window(self):
        new_win = EditorWindow(icon_path=self.icon_path)
        new_win.show()

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "ASMC & ASMCX Files (*.asmc *.asmcx);;ASMC Files (*.asmc);;ASMCX Binaries (*.asmcx);;All Files (*)"
        )
        if path:
            if path.endswith(".asmcx"):
                vm_win = VMWindow(self.icon_path, path)
                vm_win.show()
            else:
                self._load_file(path)

    def _load_file(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
            self.current_file_path = path
            self.editor.document().setModified(False)
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def save_file(self):
        if self.current_file_path:
            self._write_to_disk(self.current_file_path)
        else:
            self.save_file_as()

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save File As", "", "ASMC Files (*.asmc);;All Files (*)"
        )
        if path:
            _, ext = os.path.splitext(path)
            if not ext:
                path += ".asmc"

            self._write_to_disk(path)

    def _write_to_disk(self, path: str):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.editor.toPlainText())
            self.current_file_path = path
            self.editor.document().setModified(False)
            self._update_window_title()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

def open_app(asmc: str = None, asmcx: str = None):
    app = QApplication([])
    app.setApplicationName("asmcm")
    app.setDesktopFileName("asmcm")

    if sys.platform == "win32":
        myappid = "orbinuity.asmcm.gui." + __version__
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    icon_path = resource_path("assets", "app.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    if asmcx:
        window = VMWindow(icon_path, asmcx)
    elif asmc:
        window = EditorWindow(icon_path, asmc)
    else:
        window = EditorWindow(icon_path)

    window.show()
    app.exec()

def main():
    parser = argparse.ArgumentParser(description="Compile & Run ASMC scripts", prog="asmcm", add_help=False)
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help="Show this help message and exit")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}", help="Show the ASMCM version and exit")
    parser.add_argument("-V", "--accversion", action="version", version=f"asmcc {asmcc.__version__}", help="Show the ASMCC version and exit")
    parser.add_argument("-t", "--terminal", action='store_true', help="Dont open the GUI")
    parser.add_argument("input_file", type=str, nargs='?', default=None, help="Path to ASMC (.asmc) or ASMCX (.asmcx) file")
    parser.add_argument("output_file", type=str, nargs='?', default=None, help="Output path when compiling")

    args = parser.parse_args()
    if args.terminal:
        if not args.input_file:
            parser.print_help()
            sys.exit(0)
        elif args.input_file.endswith(".asmcx") and not args.output_file:
            execute_asmc(args.input_file)
        elif args.input_file.endswith(".asmc"):
            out_path = args.output_file if args.output_file else args.input_file + "x"
            compile_asmc(args.input_file, out_path)
        else:
            _error("This input combo does not work! Use -h for help menu")
    else:
        if not args.input_file:
            open_app()
        elif args.input_file.endswith(".asmcx") and not args.output_file:
            open_app(asmcx=args.input_file)
        elif args.input_file.endswith(".asmc") and not args.output_file:
            open_app(asmc=args.input_file)
        else:
            _error("This input combo does not work! Use -h for help menu")

if __name__ == "__main__":
    main()