import getpass
import json
import os
import sys

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


def prompt(label, env_name=None, secret=False):
    hint = f" [{env_name}]" if env_name else ""
    text = f"{label}{hint}: "
    if secret:
        return getpass.getpass(text)
    return input(text)


def json_block(title, payload):
    divider(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    divider()
