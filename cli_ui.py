import getpass
import json
import os
import sys

try:
    import termios
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}

_USE_COLOR = sys.stdout.isatty() and os.environ.get("TERM", "").lower() != "dumb"


def _style(text, *styles):
    if not _USE_COLOR:
        return text
    prefix = "".join(_ANSI[name] for name in styles if name in _ANSI)
    return f"{prefix}{text}{_ANSI['reset']}"


def _tag(label, tone="blue"):
    return _style(f"[{label}]", tone, "bold")


def banner(title, subtitle=None):
    width = 72
    line = "=" * width
    print()
    print(_style(line, "cyan"))
    print(_style(title.center(width), "bold", "cyan"))
    if subtitle:
        print(_style(subtitle.center(width), "dim"))
    print(_style(line, "cyan"))


def section(title):
    print()
    print(_style(f"== {title} ==", "bold"))


def step(title):
    print(f"{_tag('STEP', 'blue')} {title}")


def info(message):
    print(f"{_tag('INFO', 'cyan')} {message}")


def success(message):
    print(f"{_tag(' OK ', 'green')} {message}")


def warning(message):
    print(f"{_tag('WARN', 'yellow')} {message}")


def error(message):
    print(f"{_tag('ERR ', 'red')} {message}")


def command(message):
    print(f"{_tag('CMD ', 'blue')} {message}")


def status_text(label, message, tone="cyan"):
    return f"{_tag(label, tone)} {message}"


def kv(label, value):
    print(f"  {label:<16} {value}")


def divider(label=None):
    if label:
        print(_style(f"--- {label} ---", "dim"))
    else:
        print(_style("-" * 72, "dim"))


def _resolve_tty_io():
    read_stream = None
    write_stream = None
    closers = []

    for stream in (sys.stdin, sys.__stdin__):
        if stream and hasattr(stream, "isatty") and stream.isatty():
            read_stream = stream
            break

    for stream in (sys.stdout, sys.__stdout__):
        if stream and hasattr(stream, "isatty") and stream.isatty():
            write_stream = stream
            break

    if read_stream and write_stream:
        return read_stream, write_stream, closers

    try:
        if read_stream is None:
            read_stream = open("/dev/tty", "r", encoding="utf-8", errors="ignore")
            closers.append(read_stream)
        if write_stream is None:
            write_stream = open("/dev/tty", "w", encoding="utf-8", errors="ignore")
            closers.append(write_stream)
    except OSError:
        for stream in closers:
            stream.close()
        return None, None, []

    return read_stream, write_stream, closers


def _read_prompt_from_tty(text, secret=False):
    if termios is None:
        if secret:
            return getpass.getpass(text)
        return input(text)

    read_stream, write_stream, closers = _resolve_tty_io()
    if read_stream is None or write_stream is None:
        if secret:
            return getpass.getpass(text)
        return input(text)

    fd = read_stream.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        # Force the prompt to start at column 0 even if the previous linefeed
        # did not return the cursor to the line start in this terminal.
        write_stream.write(f"\r{text}")
        write_stream.flush()
        if secret:
            new_settings = termios.tcgetattr(fd)
            new_settings[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

        line = read_stream.readline()
        if line == "":
            raise EOFError

        if secret:
            write_stream.write("\r\n")
            write_stream.flush()
        else:
            write_stream.write("\r")
            write_stream.flush()

        return line.rstrip("\r\n")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        for stream in closers:
            stream.close()


def prompt(label, env_name=None, secret=False):
    hint = f" [{env_name}]" if env_name else ""
    text = f"{label}{hint}: "
    if secret:
        try:
            return getpass.getpass(text)
        except EOFError:
            return _read_prompt_from_tty(text, secret=True)

    try:
        return input(text)
    except EOFError:
        return _read_prompt_from_tty(text, secret=False)


def json_block(title, payload):
    divider(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    divider()


def select_protocols(available):
    """Interactive protocol selection.

    *available* is a list of ``(name, label)`` tuples.
    Returns a list of selected protocol names (default: all).
    """
    print()
    info("可用协议:")
    for i, (name, label) in enumerate(available, 1):
        print(f"  {i}. [{name}] {label}")
    print()
    raw = prompt("输入要启用的协议编号 (逗号分隔, 回车=全选)")
    if not raw.strip():
        return [name for name, _ in available]

    selected = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(available) and available[idx][0] not in selected:
                selected.append(available[idx][0])
    if not selected:
        return [name for name, _ in available]
    return selected
