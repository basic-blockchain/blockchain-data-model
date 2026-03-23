"""Pure UI/display helpers for the multiuser terminal.

ANSI color shortcuts, box-drawing primitives, result/data display boxes,
prompt helpers, and formatting utilities.  None of these functions depend
on ledger state, session state, or any domain/persistence imports.
"""
from __future__ import annotations

import json
import sys


# ── ANSI helpers ─────────────────────────────────────────

def _supports_ansi() -> bool:
    return sys.stdout.isatty()


def _s(text: str, code: str) -> str:
    if not _supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


# Color shortcuts
def _dim(t: str) -> str: return _s(t, "2")
def _bold(t: str) -> str: return _s(t, "1")
def _cyan(t: str) -> str: return _s(t, "1;36")
def _green(t: str) -> str: return _s(t, "1;32")
def _red(t: str) -> str: return _s(t, "1;31")
def _yellow(t: str) -> str: return _s(t, "1;33")
def _blue(t: str) -> str: return _s(t, "1;34")
def _magenta(t: str) -> str: return _s(t, "1;35")
def _white(t: str) -> str: return _s(t, "1;37")


# ── Box drawing ──────────────────────────────────────────

W = 72  # Inner width for boxes


def _box_top() -> str:
    return _dim(f"╔{'═' * (W + 2)}╗")


def _box_mid() -> str:
    return _dim(f"╠{'═' * (W + 2)}╣")


def _box_bot() -> str:
    return _dim(f"╚{'═' * (W + 2)}╝")


def _box_line(text: str = "", align: str = "left") -> str:
    plain = text.replace("\033[0m", "").replace("\033[1m", "").replace("\033[2m", "")
    for code in ("1;36", "1;32", "1;31", "1;33", "1;34", "1;35", "1;37", "0;33", "0;37"):
        plain = plain.replace(f"\033[{code}m", "")
    pad = W - len(plain)
    if pad < 0:
        pad = 0
    if align == "center":
        left_pad = pad // 2
        right_pad = pad - left_pad
        content = " " * left_pad + text + " " * right_pad
    else:
        content = text + " " * pad
    return f"{_dim('║')} {content} {_dim('║')}"


def _wrap_box(text: str, width: int = W) -> list[str]:
    if len(text) <= width:
        return [text]
    lines: list[str] = []
    while text:
        if len(text) <= width:
            lines.append(text)
            break
        cut = text.rfind(" ", 0, width)
        if cut <= 0:
            cut = width
        lines.append(text[:cut])
        text = text[cut:].lstrip()
    return lines


# ── Result display ───────────────────────────────────────

def _print_result_box(kind: str, action: str, message: str) -> None:
    if kind == "ERROR":
        color_fn = _red
        icon = "✗"
    else:
        color_fn = _green
        icon = "✓"

    print()
    print(_box_top())
    print(_box_line(color_fn(f"  {icon} [{kind}] {action}")))
    print(_box_mid())
    for line in _wrap_box(f"  {message}", W):
        print(_box_line(line))
    print(_box_bot())


def _print_data_box(title: str, data: dict | list | str, revision_id: str | None = None) -> None:
    print()
    print(_box_top())
    print(_box_line(_cyan(f"  {title}")))
    print(_box_mid())

    if isinstance(data, dict):
        for key, val in data.items():
            val_str = str(val)
            max_val = W - 22
            if len(val_str) > max_val:
                val_str = val_str[:max_val - 3] + "..."
            print(_box_line(f"  {_dim(key + ':'):<22} {_bold(val_str)}"))
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            for i, item in enumerate(data[:20]):
                if i > 0:
                    print(_box_line(_dim("  " + "─" * (W - 4))))
                for key, val in item.items():
                    val_str = str(val)
                    max_val = W - 22
                    if len(val_str) > max_val:
                        val_str = val_str[:max_val - 3] + "..."
                    print(_box_line(f"  {_dim(key + ':'):<22} {val_str}"))
            if len(data) > 20:
                print(_box_line(_dim(f"  ... y {len(data) - 20} mas")))
        else:
            for item in data[:20]:
                print(_box_line(f"  {item}"))
    else:
        for line in _wrap_box(f"  {data}", W):
            print(_box_line(line))

    if revision_id:
        print(_box_mid())
        print(_box_line(_dim(f"  revision: {revision_id}")))

    print(_box_bot())


def _print_token_notice(token: str) -> None:
    print()
    print(_box_top())
    print(_box_line(_yellow("  ⚡ TOKEN DE AUTENTICACION")))
    print(_box_mid())
    print(_box_line(f"  Token: {_bold(token)}"))
    print(_box_line(_dim("  Usa este token en transfer como sender_token.")))
    print(_box_line(_dim("  Expira en 5 minutos.")))
    print(_box_bot())


# ── Prompt helpers ───────────────────────────────────────

def _ask(label: str) -> str:
    return input(label).strip()


def _prompt(label: str, hint: str = "", default: str = "") -> str:
    parts = [f"  {_cyan('›')} {_bold(label)}"]
    if hint:
        parts.append(f" {_dim(hint)}")
    if default:
        parts.append(f" {_dim(f'[{default}]')}")
    parts.append(": ")
    value = input("".join(parts)).strip()
    return value if value else default


def _prompt_confirm(message: str) -> bool:
    resp = input(f"  {_yellow('?')} {message} {_dim('[y/N]')}: ").strip().lower()
    return resp == "y"


def _section_header(title: str) -> None:
    print()
    print(f"  {_cyan('━' * 3)} {_bold(title)} {_cyan('━' * (60 - len(title)))}")
    print()


# ── Formatting utilities ────────────────────────────────

def _short_json(value, max_len: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _meter(percentage: float, width: int = 24) -> str:
    safe = max(0.0, min(100.0, percentage))
    filled = int(round((safe / 100.0) * width))
    return "█" * filled + "░" * (width - filled)
