__version__ = "1.0.2"

import os
import sys
import time

OPCODE_MOVE   = 0
OPCODE_LEFT   = 1
OPCODE_RIGHT  = 2
OPCODE_ADD    = 3
OPCODE_SUB    = 4
OPCODE_OPEN   = 5
OPCODE_CLOSE  = 6
OPCODE_INPUT  = 7
OPCODE_OUTPUT = 8
OPCODE_CLEAR  = 9
OPCODE_COPY   = 10
OPCODE_SCANL  = 11
OPCODE_SCANR  = 12

opcode_map = {
    "<": OPCODE_LEFT,
    ">": OPCODE_RIGHT,
    "+": OPCODE_ADD,
    "-": OPCODE_SUB,
    "[": OPCODE_OPEN,
    "]": OPCODE_CLOSE,
    ",": OPCODE_INPUT,
    ".": OPCODE_OUTPUT,
}

# Check for string type in Python 2x and 3x
try:
    isinstance("", basestring)
    def isstr(s):
        return isinstance(s, basestring)
except NameError:
    def isstr(s):
        return isinstance(s, str)

class BrainfuckSyntaxError(Exception):
    """
    Raised when brainfuck source contains invalid syntax
    """
    pass

class Opcode(object):
    """
    Brainfuck intermediate representation opcode
    """

    _name_map = {
        OPCODE_MOVE: "move",
        OPCODE_ADD: "add",
        OPCODE_SUB: "sub",
        OPCODE_OPEN: "open",
        OPCODE_CLOSE: "close",
        OPCODE_INPUT: "input",
        OPCODE_OUTPUT: "output",
        OPCODE_CLEAR: "clear",
        OPCODE_COPY: "copy",
        OPCODE_SCANL: "scanl",
        OPCODE_SCANR: "scanr"
    }

    def __init__(self, code, move=0, value=None):
        self.code = code
        self.value = value
        self.move = move

    def __str__(self):
        ret = '%s %d' % (self._name_map[self.code], self.move)
        if self.value is not None:
            ret += ' %s' % self.value

        return ret

def _raise_unmatched(brace):
    raise BrainfuckSyntaxError("Error: unmatched '" + brace + "' symbol")

def _count_dupes_ahead(string, index):
    """
    Counts the number of repeated characters in 'string', starting at 'index'
    """

    ret = 0
    i = index
    end = len(string) - 1

    while (i < end) and (string[i + 1] == string[i]):
        i += 1
        ret += 1

    return ret

def _is_copyloop(program, size, index, ii):
    """
    Detects a copy loop, or a multiply loop and returns equivalent opcodes
    """

    # Copy/multiply loop must start with a decrement
    if (index > (size - 6)) or (program[index + 1] != "-"):
        return [], 0

    mult = 0
    depth = 0
    mults = {}
    i = index + 2

    # Consume the loop contents until the cell pointer movement changes
    # direction. Keep track of pointer movement, and the number of increments
    # at each cell, so we can create Opcodes to recreate the copy / multiply
    # operations performed by the loop
    while i < size:
        if program[i] in "><":
            if mult > 0:
                mults[depth] = mult
                mult = 0

            if program[i] == "<":
                break

            depth += 1

        elif program[i] == "+":
            mult += 1

        else:
            return [], 0

        i += 1

    # If no cell or pointer increments by now, this isn't a copy/multiply loop
    if (len(mults) == 0) or (depth == 0) or (i == (size - 1)):
        return [], 0

    ret = [Opcode(OPCODE_COPY, ii, mults)]

    # Consume all the pointer decrements until the end of the loop.
    # If we encounter any non-"<" characters in the loop at this stage,
    # this isn't a copy/multiply loop (at least, not one I want to mess with!)
    while (i < size) and (program[i] != "]"):
        if program[i] != "<":
            return [], 0

        depth -= 1
        i += 1

    if (depth != 0) or (i == (size - 1)):
        return [], 0

    return ret, (i - index) + 1

def _is_scanloop(program, size, index, ii):
    """
    Detects a scan loop and returns equivalent opcodes
    """

    if index < (size - 3):
        clr = program[index : index + 3]

        if clr == "[>]":
            return [Opcode(OPCODE_SCANR, ii)], 3

        elif clr == "[<]":
            return [Opcode(OPCODE_SCANL, ii)], 3

    return [], 0

def _is_clearloop(program, size, index, ii):
    """
    Detects a clear loop and returns equivalent opcodes
    """

    if index < (size - 3):
        clr = program[index : index + 3]
        if clr == "[+]" or clr == "[-]":
            return [Opcode(OPCODE_CLEAR, ii)], 3

    return [], 0

def _run_optimizers(program, size, index, ii):
    """
    Runs all the loop optimizers on the current token, and returns
    the resulting opcodes of the first one that succeeds
    """

    loop_opts = [
        _is_clearloop, _is_copyloop, _is_scanloop
    ]

    for opt in loop_opts:
        codes, chars = opt(program, size, index, ii)
        if chars > 0:
            return codes, chars

    return [], 0

def parse(program):
    """
    Convert brainfuck source into some more efficient intermediate opcodes.
    Specifically:

        * Strip out whitespace and any other non-BF characters
        * Replace copy loops, multiply loops, clear loops and scan loops with
          a single opcode that acheives the same effect
        * Collapse sequences of repeated "+", "-", ">" and "<" characters into
          a single opcode

    :param str program: Brainfuck source code
    :return: list of intermediate opcodes
    :rtype: [bfi.Opcode]
    """

    left_positions = []
    opcodes = []

    program = ''.join(program.split())
    size = len(program)

    pi = 0
    ii = 0

    while pi < size:
        if program[pi] not in opcode_map:
            pi += 1
            continue

        opcode = opcode_map[program[pi]]

        if opcode == OPCODE_OPEN:
            # Optimize common loop constructs
            codes, chars = _run_optimizers(program, size, pi, ii)
            if chars > 0:
                opcodes.extend(codes)
                pi += chars
                ii = 0
                continue

            if ii != 0:
                opcodes.append(Opcode(OPCODE_MOVE, 0, ii))
                ii = 0

            # No optimization possible, treat as normal BF loop
            left_positions.append(len(opcodes))
            opcodes.append(Opcode(OPCODE_OPEN))

        elif opcode == OPCODE_CLOSE:
            if len(left_positions) == 0:
                _raise_unmatched("]")

            left = left_positions.pop()
            right = len(opcodes)
            opcodes[left].value = right
            opcodes.append(Opcode(OPCODE_CLOSE, ii, left))
            ii = 0

        elif opcode in [OPCODE_INPUT, OPCODE_OUTPUT]:
            opcodes.append(Opcode(opcode_map[program[pi]], ii))
            ii = 0
        else:
            num = _count_dupes_ahead(program, pi)
            if opcode == OPCODE_LEFT:
                ii -= (num + 1)
            elif opcode == OPCODE_RIGHT:
                ii += (num + 1)
            else:
                opcodes.append(Opcode(opcode_map[program[pi]], ii, num + 1))
                ii = 0

            pi += num

        pi += 1

    if len(left_positions) != 0:
        _raise_unmatched('[')

    return opcodes

def execute(opcodes, input_data=None, time_limit=None, tape_size=30000,
              buffer_output=False):
    """
    Execute a list of intermediate opcodes

    :param [Opcode] opcodes: opcodes to execute
    :param str input_data: input data
    :param float time_limit: execution time limit
    :param int tape_size: Brainfuck program tape size
    :param bool buffer_output: if True, any output generated by the Brainfuck \
        program will be buffered and returned as a string
    """

    stdin = None
    if input_data != None:
        stdin = list(reversed(input_data))

    tape = bytearray(tape_size)
    size = len(opcodes)
    ret = []
    pi = 0
    ii = 0

    # Pre-bind printing function since we'll call it so frequently. This
    # *did* speed things up very slightly in my tests, could have been a
    # delusion, I'm leaving it in anyway...
    syswrite = sys.stdout.write
    sysflush = sys.stdout.flush

    def write_stdout(c):
        syswrite(c)
        sysflush()

    def write_buf(c):
        ret.append(c)

    def read_stdin():
        return os.read(0, 1)

    def read_buf():
        try:
            ret = stdin.pop()
        except:
            return ''

        return ret

    do_write = write_buf if buffer_output else write_stdout
    do_read = read_stdin if stdin == None else read_buf

    if time_limit:
        start = time.time()

    while ii < size:
        op = opcodes[ii]

        if op.code == OPCODE_MOVE:
            pi += op.value

        elif op.code == OPCODE_ADD:
            pi += op.move
            tape[pi] = (tape[pi] + op.value) % 256

        elif op.code == OPCODE_SUB:
            pi += op.move
            tape[pi] = (tape[pi] - op.value) % 256

        elif op.code == OPCODE_OPEN:
            pi += op.move
            if tape[pi] == 0:
               ii = op.value

        elif op.code == OPCODE_CLOSE:
            pi += op.move
            if tape[pi] != 0:
                ii = op.value - 1

        elif op.code == OPCODE_INPUT:
            pi += op.move
            ch = do_read()
            if len(ch) > 0 and ord(ch) > 0:
                tape[pi] = ord(ch)

        elif op.code == OPCODE_OUTPUT:
            pi += op.move
            do_write(chr(tape[pi]))

        elif op.code == OPCODE_CLEAR:
            pi += op.move
            tape[pi] = 0

        elif op.code == OPCODE_COPY:
            pi += op.move
            if tape[pi] > 0:
                for off in op.value:
                    index = pi + off
                    tape[index] = (tape[index]
                        + (tape[pi] * op.value[off])) % 256

                tape[pi] = 0

        elif op.code == OPCODE_SCANL:
            pi += op.move
            while pi > 0 and tape[pi] != 0:
                pi -= 1

        elif op.code == OPCODE_SCANR:
            pi += op.move
            while pi < (size - 1) and tape[pi] != 0:
                pi += 1

        ii += 1
        if time_limit and ((time.time() - start) >= time_limit):
            return None

    return "".join(ret) if buffer_output == True else None

def interpret(program, input_data=None, time_limit=None, tape_size=30000,
        buffer_output=False):
    """
    Interpret & execute a brainfuck program

    :param str program: Brainfuck source code
    :param str input_data: input data
    :param float time_limit: execution time limit
    :param int tape_size: Brainfuck program tape size
    :param bool buffer_output: if True, any output generated by the Brainfuck \
        program will be buffered and returned as a string
    """

    if not isstr(program):
        raise BrainfuckSyntaxError("expecting a string containing Brainfuck "
            "code. Got %s instead" % type(program))

    opcodes = parse(program)
    return execute(opcodes, input_data, time_limit, tape_size, buffer_output)
