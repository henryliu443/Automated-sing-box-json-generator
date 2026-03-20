import getpass
import json
import os
import sys

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None
    tty = None

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


def _consume_escape_sequence(fd):
    while True:
        chunk = os.read(fd, 1)
        if not chunk:
            return
        char = chunk.decode("utf-8", errors="ignore")
        if not char or char.isalpha() or char == "~":
            return


def _read_prompt_from_tty(text, secret=False):
    if termios is None or tty is None:
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
    chars = []

    try:
        write_stream.write(text)
        write_stream.flush()
        tty.setraw(fd)

        while True:
            chunk = os.read(fd, 1)
            if not chunk:
                raise EOFError

            char = chunk.decode("utf-8", errors="ignore")

            if char in ("\r", "\n"):
                write_stream.write("\n")
                write_stream.flush()
                return "".join(chars)

            if char == "\x03":
                write_stream.write("^C\n")
                write_stream.flush()
                raise KeyboardInterrupt

            if char == "\x04":
                if not chars:
                    write_stream.write("\n")
                    write_stream.flush()
                    raise EOFError
                continue

            if char == "\x1b":
                _consume_escape_sequence(fd)
                continue

            if char in ("\x7f", "\b"):
                if chars:
                    chars.pop()
                    if not secret:
                        write_stream.write("\b \b")
                        write_stream.flush()
                continue

            chars.append(char)
            if not secret:
                write_stream.write(char)
                write_stream.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        for stream in closers:
            stream.close()


def prompt(label, env_name=None, secret=False):
    hint = f" [{env_name}]" if env_name else ""
    text = f"{label}{hint}: "
    return _read_prompt_from_tty(text, secret=secret)


def json_block(title, payload):
    divider(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    divider()
