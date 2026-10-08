#!/bin/python3
__version__ = "1.0.0"
import sys
try:
    import argparse
    import struct
    import os
    import re
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

ACC_VERSION = "1.0"
MAGIC_HEADER = (b"ACX"+ACC_VERSION.split(".")[0].encode())

# Tools
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

# API
class AssemblyCraftCompiler:
    ALLOC_SIZES = {
        'ds': 16,
        'dm': 32,
        'db': 64
    }

    REGISTERS = {
        'rax': 0x00, 'rbx': 0x01, 'rcx': 0x02, 'rdx': 0x03,
        'rsi': 0x04, 'rdi': 0x05, 'rbp': 0x06, 'rsp': 0x07,
        'r8': 0x08,  'r9': 0x09,  'r10': 0x0A, 'r11': 0x0B,
        'r12': 0x0C, 'r13': 0x0D, 'r14': 0x0E, 'r15': 0x0F
    }

    OPCODES = {
        'mov':     0x01, # 1
        'push':    0x02, # 2
        'pop':     0x03, # 3
        'call':    0x04, # 4
        'ret':     0x05, # 5
        'cmp':     0x06, # 6
        'jmp':     0x07, # 7
        'je':      0x08, # 8
        'jne':     0x09, # 9
        'jg':      0x0A, # 10
        'jl':      0x0B, # 11
        'jge':     0x0C, # 12
        'jle':     0x0D, # 13
        'xor':     0x0E, # 14
        'add':     0x0F, # 15
        'sub':     0x10, # 16
        'mul':     0x11, # 17
        'div':     0x12, # 18
        'syscall': 0x13  # 19
    }

    ARG_TYPE_REG = 0x01
    ARG_TYPE_VAR = 0x02
    ARG_TYPE_IMM = 0x03

    def __init__(self):
        self.variables = {}
        self.labels = {}
        self.bytecode = bytearray()

    def compile(self, source_code: str, output_filepath: str):
        data_lines, text_lines = self._split_sections(source_code)
        self._parse_data_section(data_lines)
        self._parse_text_section(text_lines)
        
        binary_data = self._generate_binary()
        
        with open(output_filepath, "wb") as f:
            f.write(binary_data)
        
        _info(f"Successfully compiled to '{output_filepath}' ({len(binary_data)} bytes)")

    def _split_sections(self, code: str):
        current_section = None
        data_lines, text_lines = [], []
        
        for line in code.splitlines():
            line = re.sub(r';.*$', '', line).strip()
            if not line:
                continue
            if line.startswith("section .data"):
                current_section = "data"
                continue
            elif line.startswith("section .text"):
                current_section = "text"
                continue

            if current_section == "data":
                data_lines.append(line)
            elif current_section == "text":
                text_lines.append(line)

        return data_lines, text_lines

    def _parse_data_section(self, lines: list):
        var_id = 0
        for line in lines:
            match = re.match(r'^([a-zA-Z_]\w*)\s+(ds|dm|db)\s+(.+)$', line)
            if not match:
                continue

            var_name, size_type, values_str = match.groups()
            alloc_len = self.ALLOC_SIZES[size_type]

            raw_bytes = bytearray()
            tokens = re.findall(r'"([^"]*)"|(\d+|0x[0-9a-fA-F]+)', values_str)

            for str_val, num_val in tokens:
                if str_val:
                    decoded_str = str_val.encode('utf-8').decode('unicode_escape')
                    raw_bytes.extend(decoded_str.encode('utf-8'))
                elif num_val:
                    raw_bytes.append(int(num_val, 0) & 0xFF)

            padded_data = bytes(raw_bytes)[:alloc_len].ljust(alloc_len, b'\x00')

            self.variables[var_name] = {
                'id': var_id,
                'size_type': size_type,
                'alloc_len': alloc_len,
                'data': padded_data
            }
            var_id += 1

    def _parse_text_section(self, lines: list):
        bytecode_offset = 0
        cleaned_instructions = []

        for line in lines:
            if line.endswith(':'):
                label_name = line[:-1].strip()
                self.labels[label_name] = bytecode_offset
            else:
                cleaned_instructions.append(line)
                parts = line.split(maxsplit=1)
                mnemonic = parts[0].lower()
                args_str = parts[1] if len(parts) > 1 else ""
                num_args = len([a.strip() for a in args_str.split(',')]) if args_str else 0
                bytecode_offset += 1 + (num_args * 5)

        for line in cleaned_instructions:
            parts = line.split(maxsplit=1)
            mnemonic = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

            if mnemonic not in self.OPCODES:
                _error(f"Unknown instruction: '{mnemonic}'")

            self.bytecode.append(self.OPCODES[mnemonic])

            if args_str:
                args = [a.strip() for a in args_str.split(',')]
                for arg in args:
                    arg_type, arg_val = self._resolve_operand(arg)
                    self.bytecode.append(arg_type)
                    self.bytecode += struct.pack("<i", arg_val)

    def _resolve_operand(self, token: str):
        if token in self.REGISTERS:
            return self.ARG_TYPE_REG, self.REGISTERS[token]
        if token in self.variables:
            return self.ARG_TYPE_VAR, self.variables[token]['id']
        if token in self.labels:
            return self.ARG_TYPE_IMM, self.labels[token]
        try:
            return self.ARG_TYPE_IMM, int(token, 0)
        except ValueError:
            _error(f"Unresolved operand token: '{token}'")

    def _generate_binary(self) -> bytearray:
        key_table = bytearray()
        data_payload = bytearray()

        base_offset = 10 + (len(self.variables) * 22)
        current_data_offset = base_offset

        for var_name, info in self.variables.items():
            encoded_name = var_name.encode('utf-8')[:16].ljust(16, b'\x00')
            key_table += struct.pack("<B16sIB", info['id'], encoded_name, current_data_offset, info['alloc_len'])
            data_payload += info['data']
            current_data_offset += info['alloc_len']

        text_offset = current_data_offset
        header = bytearray(MAGIC_HEADER) + struct.pack("<HI", len(self.variables), text_offset)

        return header + key_table + data_payload + self.bytecode

class Memory:
    def __init__(self, binary_path: str):
        with open(binary_path, "rb") as f:
            self.raw_data = f.read()

        self.var_table = {}
        self.text_bytecode = bytearray()
        self._parse_binary()

    def _parse_binary(self):
        magic = self.raw_data[:4]
        if magic != MAGIC_HEADER:
            _error(f"Invalid binary format. Expected '{MAGIC_HEADER.decode()}' magic header.")

        var_count, text_offset = struct.unpack("<HI", self.raw_data[4:10])
        offset = 10

        for _ in range(var_count):
            var_id, raw_name, val_offset, alloc_len = struct.unpack("<B16sIB", self.raw_data[offset:offset+22])
            var_name = raw_name.decode('utf-8').rstrip('\x00')
            self.var_table[var_id] = {
                'name': var_name,
                'offset': val_offset,
                'alloc_len': alloc_len
            }
            offset += 22

        self.text_bytecode = self.raw_data[text_offset:]

    def read_var_bytes(self, var_id: int) -> bytes:
        if var_id not in self.var_table:
            _error(f"Variable ID {var_id} not found in Memory table.")
        var_info = self.var_table[var_id]
        val_offset = var_info['offset']
        alloc_len = var_info['alloc_len']

        return self.raw_data[val_offset:val_offset + alloc_len]

class RAM:
    def __init__(self):
        self.registers = [0] * 16
        self.registers[7] = 0x8000
        self.heap = {}

    def get_register(self, reg_id: int) -> int:
        return self.registers[reg_id]

    def set_register(self, reg_id: int, value: int):
        self.registers[reg_id] = value

    def store_in_ram(self, address: int, data: bytes):
        self.heap[address] = data

    def read_from_ram(self, address: int, length: int = 64) -> bytes:
        return self.heap.get(address, b"")[:length]

    def deref_register(self, reg_value) -> str:
        if isinstance(reg_value, bytes):
            return reg_value.decode('utf-8', errors='ignore').rstrip('\x00\n')
        
        if isinstance(reg_value, str):
            return reg_value
        
        ram_data = self.read_from_ram(reg_value)

        if ram_data:
            return ram_data.decode('utf-8', errors='ignore').rstrip('\x00\n')
        elif isinstance(reg_value, int) and 1 <= reg_value <= 255:
            return chr(reg_value)
        else:
            return str(reg_value)


class CPU:
    ARG_TYPE_REG = 0x01
    ARG_TYPE_VAR = 0x02
    ARG_TYPE_IMM = 0x03

    def __init__(self, memory: Memory, ram: RAM):
        self.memory = memory
        self.ram = ram
        self.ip = 0
        self.zf = False
        self.sf = False
        self.running = False
        self.syscall_table = {}

    def register_syscall(self, sys_code: int, handler_func):
        self.syscall_table[sys_code] = handler_func

    def _fetch_operand(self):
        op_type = self.memory.text_bytecode[self.ip]
        op_val = struct.unpack("<i", self.memory.text_bytecode[self.ip+1:self.ip+5])[0]
        self.ip += 5
        return op_type, op_val

    def _resolve_val(self, op_type: int, op_val: int) -> int:
        if op_type == self.ARG_TYPE_REG:
            return self.ram.get_register(op_val)

        elif op_type == self.ARG_TYPE_VAR:
            var_info = self.memory.var_table[op_val]
            raw_bytes = self.memory.read_var_bytes(op_val)

            if 'ram_address' not in var_info:
                ram_address = 0x1000 + (op_val * 0x0100)
                self.ram.store_in_ram(ram_address, raw_bytes)
                var_info['ram_address'] = ram_address

            return var_info['ram_address']

        elif op_type == self.ARG_TYPE_IMM:
            return op_val
        return 0

    def run(self):
        self.running = True
        bytecode = self.memory.text_bytecode

        while self.running and self.ip < len(bytecode):
            opcode = bytecode[self.ip]
            self.ip += 1

            if opcode == 0x01:  # mov
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                src_res = self._resolve_val(s_type, s_val)
                if d_type == self.ARG_TYPE_REG:
                    self.ram.set_register(d_val, src_res)

            elif opcode == 0x02:  # push
                s_type, s_val = self._fetch_operand()
                val = self._resolve_val(s_type, s_val)
                rsp = self.ram.get_register(7) - 4
                self.ram.set_register(7, rsp)
                self.ram.store_in_ram(rsp, struct.pack("<i", val))

            elif opcode == 0x03:  # pop
                d_type, d_val = self._fetch_operand()
                rsp = self.ram.get_register(7)
                raw_val = self.ram.read_from_ram(rsp, 4)
                val = struct.unpack("<i", raw_val)[0] if raw_val else 0
                self.ram.set_register(7, rsp + 4)
                if d_type == self.ARG_TYPE_REG:
                    self.ram.set_register(d_val, val)

            elif opcode == 0x04:  # call
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                rsp = self.ram.get_register(7) - 4
                self.ram.set_register(7, rsp)
                self.ram.store_in_ram(rsp, struct.pack("<i", self.ip))
                self.ip = target

            elif opcode == 0x05:  # ret
                rsp = self.ram.get_register(7)
                raw_val = self.ram.read_from_ram(rsp, 4)
                return_ip = struct.unpack("<i", raw_val)[0] if raw_val else 0
                self.ram.set_register(7, rsp + 4)
                self.ip = return_ip

            elif opcode == 0x06:  # cmp
                a1_type, a1_val = self._fetch_operand()
                a2_type, a2_val = self._fetch_operand()
                v1 = self._resolve_val(a1_type, a1_val)
                v2 = self._resolve_val(a2_type, a2_val)
                self.zf = (v1 == v2)
                self.sf = (v1 < v2)

            elif opcode == 0x07:  # jmp
                t_type, t_val = self._fetch_operand()
                self.ip = self._resolve_val(t_type, t_val)

            elif opcode == 0x08:  # je
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if self.zf:
                    self.ip = target

            elif opcode == 0x09:  # jne
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if not self.zf:
                    self.ip = target

            elif opcode == 0x0A:  # jg
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if not self.zf and not self.sf:
                    self.ip = target

            elif opcode == 0x0B:  # jl
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if self.sf and not self.zf:
                    self.ip = target

            elif opcode == 0x0C:  # jge
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if not self.sf:
                    self.ip = target

            elif opcode == 0x0D:  # jle
                t_type, t_val = self._fetch_operand()
                target = self._resolve_val(t_type, t_val)
                if self.sf or self.zf:
                    self.ip = target

            elif opcode == 0x0E:  # xor
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                if d_type == self.ARG_TYPE_REG:
                    v1 = self.ram.get_register(d_val)
                    v2 = self._resolve_val(s_type, s_val)
                    self.ram.set_register(d_val, v1 ^ v2)

            elif opcode == 0x0F:  # add
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                if d_type == self.ARG_TYPE_REG:
                    v1 = self.ram.get_register(d_val)
                    v2 = self._resolve_val(s_type, s_val)
                    self.ram.set_register(d_val, v1 + v2)

            elif opcode == 0x10:  # sub
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                if d_type == self.ARG_TYPE_REG:
                    v1 = self.ram.get_register(d_val)
                    v2 = self._resolve_val(s_type, s_val)
                    self.ram.set_register(d_val, v1 - v2)

            elif opcode == 0x11:  # mul
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                if d_type == self.ARG_TYPE_REG:
                    v1 = self.ram.get_register(d_val)
                    v2 = self._resolve_val(s_type, s_val)
                    self.ram.set_register(d_val, v1 * v2)

            elif opcode == 0x12:  # div
                d_type, d_val = self._fetch_operand()
                s_type, s_val = self._fetch_operand()
                if d_type == self.ARG_TYPE_REG:
                    v1 = self.ram.get_register(d_val)
                    v2 = self._resolve_val(s_type, s_val)
                    if v2 == 0:
                        _error(f"Division by zero at IP: {self.ip}")
                    self.ram.set_register(d_val, v1 // v2)

            elif opcode == 0x13:  # syscall
                sys_num = self.ram.get_register(0)
                if sys_num in self.syscall_table:
                    self.syscall_table[sys_num]()
                else:
                    _error(f"Unhandled Syscall #{sys_num} at IP: {self.ip}")

class Firmware:
    def __init__(self, version: int):
        self.VERSIONS = [1]
        if version in self.VERSIONS:
            self.version = version
        else:
            _error(f"Unknown firmware version: {str(version)}!")

    def load_syscalls(self, cpu: CPU):
        if self.version == 1:
            def sys_exit():
                exit_code = cpu.ram.get_register(reg['arg1'])
                cpu.running = False
                sys.exit(exit_code)

            def sys_write():
                register_value = cpu.ram.get_register(reg['arg1'])
                text = cpu.ram.deref_register(register_value)
                print(text)

            def sys_read():
                read = input().encode('utf-8')
                cpu.ram.set_register(reg['ret'], read)

            cpu.register_syscall(0, sys_exit)
            cpu.register_syscall(1, sys_write)
            cpu.register_syscall(2, sys_read)

# UI
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
    system_memory = Memory(asmcx_file_path)
    system_ram = RAM()
    cpu = CPU(system_memory, system_ram)

    firmware = Firmware(1)
    firmware.load_syscalls(cpu)

    cpu.run()

def _main():
    parser = argparse.ArgumentParser(description="Compile & Run ASMC scripts", prog="ASMCM", add_help=False)
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help="Show this help message and exit")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}", help="Show the ASMCM version and exit")
    parser.add_argument("-V", "--accversion", action="version", version=f"ACC {ACC_VERSION}", help="Show the acc version and exit")
    parser.add_argument("asmc_file", type=str, nargs='?', default=None, help="Path to your ASMC file (optional)")
    parser.add_argument("asmcx_file", type=str, help="Path to the new ASMCX file")

    args = parser.parse_args()

    if args.asmc_file:
        compile_asmc(args.asmc_file, args.asmcx_file)
    else:
        execute_asmc(args.asmcx_file)


if __name__ == "__main__":
    _main()