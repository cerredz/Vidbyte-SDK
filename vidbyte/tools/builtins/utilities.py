"""Context Header Protocol

Description:
    Simple utility tools using Python stdlib only — no API keys, no external dependencies.
Purpose:
    Provides atomic utility functions (string, encoding, hash, json, network, time,
    random, validation, file, system, diff, math) as composable agent tools.
Architecture:
    - Every tool is a @tool-decorated async function.
    - All implementations use stdlib only (no pip install needed beyond vidbyte-sdk).
    - Tools are SAFE or READ permission.
Relations:
    Related to vidbyte.tools.decorators and vidbyte.tools.types.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import difflib
import hashlib
import html as html_mod
import io
import ipaddress
import json
import mimetypes
import os
import platform
import random
import re
import secrets
import shutil
import socket
import string
import time
import urllib.parse
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

# ---------------------------------------------------------------------------
# String / Text
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def count_words(text: str) -> str:
    """Count the number of words in a text string."""
    return str(len(text.split()))


@tool(permission=ToolPermission.SAFE)
async def count_chars(text: str) -> str:
    """Count the number of characters in a text string."""
    return str(len(text))


@tool(permission=ToolPermission.SAFE)
async def regex_match(pattern: str, text: str, flags: str = "") -> str:
    """Test if a regex pattern matches a string. Returns match groups as JSON or 'no match'."""
    flag_map: dict[str, int] = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}
    flag_val = 0
    for c in flags:
        flag_val |= flag_map.get(c, 0)
    m = re.search(pattern, text, flag_val)
    if not m:
        return "no match"
    groups = m.groupdict() or {str(i): g for i, g in enumerate(m.groups(), 1)} if m.groups() else {}
    return json.dumps({"match": m.group(0), "groups": groups, "span": list(m.span())}, default=str)


@tool(permission=ToolPermission.SAFE)
async def regex_replace(pattern: str, replacement: str, text: str, count: int = 0) -> str:
    """Replace occurrences of a regex pattern in text."""
    return re.sub(pattern, replacement, text, count=count)


@tool(permission=ToolPermission.SAFE)
async def truncate_text(text: str, max_chars: int = 2000) -> str:
    """Truncate text to a maximum character count."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated at {max_chars} chars]"


@tool(permission=ToolPermission.SAFE)
async def case_convert(text: str, to_case: str = "lower") -> str:
    """Convert text case. to_case: 'lower', 'upper', 'title', 'capitalize', 'snake', 'kebab'."""
    if to_case == "lower":
        return text.lower()
    if to_case == "upper":
        return text.upper()
    if to_case == "title":
        return text.title()
    if to_case == "capitalize":
        return text.capitalize()
    if to_case == "snake":
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        return re.sub(r"[-\s]+", "_", s).lower()
    if to_case == "kebab":
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", text)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", s)
        return re.sub(r"[_\s]+", "-", s).lower()
    return text


@tool(permission=ToolPermission.SAFE)
async def slugify(text: str, separator: str = "-") -> str:
    """Convert text into a URL-friendly slug."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", separator, s)
    return s.strip(separator)


@tool(permission=ToolPermission.SAFE)
async def extract_emails(text: str) -> str:
    """Extract all email addresses from text."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    found = re.findall(pattern, text)
    return json.dumps(list(set(found))) if found else "[]"


@tool(permission=ToolPermission.SAFE)
async def extract_urls(text: str) -> str:
    """Extract all URLs from text."""
    pattern = r"https?://[^\s<>\"']+"
    found = re.findall(pattern, text)
    return json.dumps(list(set(found))) if found else "[]"


@tool(permission=ToolPermission.SAFE)
async def reading_time(text: str, wpm: int = 200) -> str:
    """Estimate reading time for text. Returns minutes."""
    words = len(text.split())
    minutes = max(1, round(words / wpm))
    return f"{minutes} min ({words} words at {wpm} wpm)"


@tool(permission=ToolPermission.SAFE)
async def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def base64_encode(text: str) -> str:
    """Encode a string to base64."""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


@tool(permission=ToolPermission.SAFE)
async def base64_decode(encoded: str) -> str:
    """Decode a base64 string."""
    return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")


@tool(permission=ToolPermission.SAFE)
async def url_encode(text: str) -> str:
    """URL-encode a string."""
    return urllib.parse.quote(text)


@tool(permission=ToolPermission.SAFE)
async def url_decode(text: str) -> str:
    """URL-decode a string."""
    return urllib.parse.unquote(text)


@tool(permission=ToolPermission.SAFE)
async def html_encode(text: str) -> str:
    """HTML-encode (escape) a string."""
    return html_mod.escape(text)


@tool(permission=ToolPermission.SAFE)
async def html_decode(text: str) -> str:
    """HTML-decode (unescape) a string."""
    return html_mod.unescape(text)


@tool(permission=ToolPermission.SAFE)
async def hex_encode(text: str) -> str:
    """Encode a string to hex."""
    return text.encode("utf-8").hex()


@tool(permission=ToolPermission.SAFE)
async def hex_decode(hex_str: str) -> str:
    """Decode a hex string."""
    return bytes.fromhex(hex_str).decode("utf-8")


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

def _compute_hash(data: bytes, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


@tool(permission=ToolPermission.SAFE)
async def hash_md5(text: str) -> str:
    """Compute the MD5 hash of a string."""
    return _compute_hash(text.encode("utf-8"), "md5")


@tool(permission=ToolPermission.SAFE)
async def hash_sha256(text: str) -> str:
    """Compute the SHA-256 hash of a string."""
    return _compute_hash(text.encode("utf-8"), "sha256")


@tool(permission=ToolPermission.SAFE)
async def hash_sha512(text: str) -> str:
    """Compute the SHA-512 hash of a string."""
    return _compute_hash(text.encode("utf-8"), "sha512")


@tool(permission=ToolPermission.READ)
async def hash_file(file_path: str, algorithm: str = "sha256") -> str:
    """Compute the hash of a file. algorithm: md5, sha256, sha512."""
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        return f"File not found: {file_path}"
    data = p.read_bytes()
    return _compute_hash(data, algorithm)


# ---------------------------------------------------------------------------
# JSON / Data
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def json_validate(text: str) -> str:
    """Validate a JSON string. Returns 'valid' or error message."""
    try:
        json.loads(text)
        return "valid"
    except json.JSONDecodeError as e:
        return f"invalid: {e}"


@tool(permission=ToolPermission.SAFE)
async def json_pretty(text: str, indent: int = 2) -> str:
    """Pretty-print a JSON string."""
    data = json.loads(text)
    return json.dumps(data, indent=indent, default=str, sort_keys=True)


@tool(permission=ToolPermission.SAFE)
async def json_to_csv(text: str) -> str:
    """Convert a JSON array of objects to CSV format."""
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        return "Input must be a non-empty JSON array of objects."
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


@tool(permission=ToolPermission.SAFE)
async def csv_to_json(text: str, delimiter: str = ",") -> str:
    """Convert CSV text to a JSON array of objects."""
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    return json.dumps(rows, default=str)


@tool(permission=ToolPermission.SAFE)
async def json_path(text: str, path: str) -> str:
    """Extract values from JSON using dot-notation path (e.g. 'data.items.0.name')."""
    data = json.loads(text)
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, f"<key '{part}' not found>")
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return f"<index '{part}' out of range>"
        else:
            return f"<cannot traverse into {type(current).__name__}>"
    return json.dumps(current, default=str) if not isinstance(current, str) else current


# ---------------------------------------------------------------------------
# Network (stdlib only, no API keys)
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.READ)
async def dns_lookup(hostname: str) -> str:
    """Resolve a hostname to IP address(es)."""
    try:
        info = socket.getaddrinfo(hostname, None)
        ips = sorted({addr[4][0] for addr in info})
        return json.dumps(ips)
    except socket.gaierror as e:
        return f"DNS lookup failed: {e}"


@tool(permission=ToolPermission.READ)
async def port_check(host: str, port: int, timeout_seconds: int = 5) -> str:
    """Check if a TCP port is open on a host."""
    try:
        s = socket.create_connection((host, port), timeout=timeout_seconds)
        s.close()
        return f"Port {port} on {host} is OPEN"
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return f"Port {port} on {host} is CLOSED ({e})"


@tool(permission=ToolPermission.READ)
async def is_reachable(url: str, timeout_seconds: int = 10) -> str:
    """Check if a URL is reachable via HTTP HEAD request. Returns status code."""
    from urllib.request import Request, urlopen

    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=timeout_seconds) as resp:
            return f"Reachable — HTTP {resp.status}"
    except Exception as e:
        return f"Not reachable: {e}"


@tool(permission=ToolPermission.READ)
async def ping_host(host: str, count: int = 3, timeout_seconds: int = 5) -> str:
    """Ping a host using system ping command. Returns summary."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
    cmd = ["ping", param, str(count), timeout_param, str(timeout_seconds * 1000), host]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds * count + 5)
    output = stdout.decode("utf-8", errors="replace")
    if not output and stderr:
        output = stderr.decode("utf-8", errors="replace")
    return output[:3000] or "No output"


# ---------------------------------------------------------------------------
# Time / Date
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def current_time(timezone: str = "UTC") -> str:
    """Get the current date and time. timezone: 'UTC' or 'local'."""
    if timezone.lower() == "utc":
        now = datetime.now(UTC)
        return now.isoformat()
    now = datetime.now()
    return now.isoformat()


@tool(permission=ToolPermission.SAFE)
async def timestamp() -> str:
    """Get the current Unix timestamp (seconds since epoch)."""
    return str(int(time.time()))


@tool(permission=ToolPermission.SAFE)
async def sleep_tool(seconds: float = 1.0) -> str:
    """Pause execution for the specified number of seconds."""
    await asyncio.sleep(max(0, min(seconds, 300)))
    return f"Slept for {seconds} seconds"


# ---------------------------------------------------------------------------
# Random / ID Generation
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def random_number(min_val: int = 0, max_val: int = 100) -> str:
    """Generate a random integer between min_val and max_val (inclusive)."""
    return str(random.randint(min_val, max_val))


@tool(permission=ToolPermission.SAFE)
async def random_string(length: int = 16, charset: str = "alphanumeric") -> str:
    """Generate a random string. charset: 'alphanumeric', 'alpha', 'numeric', 'hex', 'printable'."""
    chars: dict[str, str] = {
        "alphanumeric": string.ascii_letters + string.digits,
        "alpha": string.ascii_letters,
        "numeric": string.digits,
        "hex": string.hexdigits,
        "printable": string.ascii_letters + string.digits + "!@#$%^&*()-_=+",
    }
    pool = chars.get(charset, chars["alphanumeric"])
    return "".join(secrets.choice(pool) for _ in range(length))


@tool(permission=ToolPermission.SAFE)
async def uuid4() -> str:
    """Generate a random UUID v4."""
    return str(uuid.uuid4())


@tool(permission=ToolPermission.SAFE)
async def nanoid(length: int = 21) -> str:
    """Generate a URL-friendly unique ID (nanoid-style)."""
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def validate_email(email: str) -> str:
    """Basic email format validation. Returns 'valid' or error."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(pattern, email):
        return "valid"
    return "invalid email format"


@tool(permission=ToolPermission.SAFE)
async def validate_url(url: str) -> str:
    """Check if a string is a valid URL. Returns 'valid' or error."""
    try:
        result = urllib.parse.urlparse(url)
        if result.scheme and result.netloc:
            return "valid"
        return "invalid: missing scheme or host"
    except Exception as e:
        return f"invalid: {e}"


@tool(permission=ToolPermission.SAFE)
async def validate_ip(ip_str: str) -> str:
    """Validate an IPv4 or IPv6 address. Returns 'valid' or error."""
    try:
        ipaddress.ip_address(ip_str)
        return "valid"
    except ValueError as e:
        return f"invalid: {e}"


# ---------------------------------------------------------------------------
# File Inspection
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.READ)
async def file_size(file_path: str) -> str:
    """Get the size of a file in bytes, KB, MB."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return f"File not found: {file_path}"
    size = p.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@tool(permission=ToolPermission.READ)
async def line_count(file_path: str) -> str:
    """Count the number of lines in a file."""
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        return f"File not found: {file_path}"
    with open(p, encoding="utf-8", errors="replace") as f:
        return str(sum(1 for _ in f))


@tool(permission=ToolPermission.READ)
async def mime_type(file_path: str) -> str:
    """Get the MIME type of a file."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return f"File not found: {file_path}"
    mime, _ = mimetypes.guess_type(str(p))
    return mime or "application/octet-stream"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.READ)
async def get_env_var(name: str) -> str:
    """Get the value of an environment variable."""
    val = os.environ.get(name)
    if val is None:
        return f"Environment variable '{name}' is not set."
    return val


@tool(permission=ToolPermission.SAFE)
async def disk_usage(path: str = ".") -> str:
    """Get disk usage statistics for a path (total, used, free in GB)."""
    usage = shutil.disk_usage(path)
    gb = 1024 ** 3
    return f"Total: {usage.total / gb:.1f} GB, Used: {usage.used / gb:.1f} GB, Free: {usage.free / gb:.1f} GB"


@tool(permission=ToolPermission.SAFE)
async def cpu_count() -> str:
    """Get the number of CPU cores."""
    return f"Logical: {os.cpu_count()}, Physical: {os.cpu_count() // 2}" if os.cpu_count() else "unknown"


@tool(permission=ToolPermission.READ)
async def platform_info() -> str:
    """Get system platform information."""
    return json.dumps({
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    })


# ---------------------------------------------------------------------------
# Diff / Compare
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def text_diff(text_a: str, text_b: str, label_a: str = "original", label_b: str = "modified") -> str:
    """Generate a unified diff between two text strings."""
    diff = difflib.unified_diff(
        text_a.splitlines(keepends=True),
        text_b.splitlines(keepends=True),
        fromfile=label_a,
        tofile=label_b,
    )
    result = "".join(diff)
    return result[:10000] if result else "No differences found."


# ---------------------------------------------------------------------------
# Math (stdlib, extending existing calculator)
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def math_factorial(n: int) -> str:
    """Calculate the factorial of a non-negative integer."""
    if n < 0:
        return "Error: n must be >= 0"
    if n > 1000:
        return "Error: n too large (max 1000)"
    import math
    return str(math.factorial(n))


@tool(permission=ToolPermission.SAFE)
async def math_is_prime(n: int) -> str:
    """Check if a number is prime."""
    if n < 2:
        return "False (not prime)"
    if n in (2, 3):
        return "True (prime)"
    if n % 2 == 0 or n % 3 == 0:
        return "False (not prime)"
    import math
    limit = int(math.isqrt(n))
    for i in range(5, limit + 1, 6):
        if n % i == 0 or n % (i + 2) == 0:
            return "False (not prime)"
    return "True (prime)"


@tool(permission=ToolPermission.SAFE)
async def math_sqrt(n: float) -> str:
    """Calculate the square root of a number."""
    if n < 0:
        return f"{(-n) ** 0.5}i"
    import math
    return str(math.sqrt(n))


@tool(permission=ToolPermission.SAFE)
async def math_convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units.
    Supported: temperature (c, f, k), length (m, km, mi, ft, in, cm, mm, yd),
    weight (kg, g, lb, oz), data (b, kb, mb, gb, tb).
    """
    # Temperature
    temp_conversions: dict[tuple[str, str], Callable[[float], float]] = {
        ("c", "f"): lambda x: x * 9 / 5 + 32,
        ("f", "c"): lambda x: (x - 32) * 5 / 9,
        ("c", "k"): lambda x: x + 273.15,
        ("k", "c"): lambda x: x - 273.15,
        ("f", "k"): lambda x: (x - 32) * 5 / 9 + 273.15,
        ("k", "f"): lambda x: (x - 273.15) * 9 / 5 + 32,
    }

    # Length (base: meters)
    length_to_m: dict[str, float] = {"m": 1, "km": 1000, "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "cm": 0.01, "mm": 0.001, "yd": 0.9144}
    # Weight (base: kg)
    weight_to_kg: dict[str, float] = {"kg": 1, "g": 0.001, "lb": 0.453592, "oz": 0.0283495}
    # Data (base: bytes)
    data_to_bytes: dict[str, float] = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4}

    fu = from_unit.lower()
    tu = to_unit.lower()

    # Same unit
    if fu == tu:
        return str(value)

    # Temperature
    key = (fu, tu)
    if key in temp_conversions:
        return str(round(temp_conversions[key](value), 4))

    # Length
    if fu in length_to_m and tu in length_to_m:
        meters = value * length_to_m[fu]
        return str(round(meters / length_to_m[tu], 6))

    # Weight
    if fu in weight_to_kg and tu in weight_to_kg:
        kg = value * weight_to_kg[fu]
        return str(round(kg / weight_to_kg[tu], 6))

    # Data
    if fu in data_to_bytes and tu in data_to_bytes:
        b = value * data_to_bytes[fu]
        return str(round(b / data_to_bytes[tu], 6))

    return f"Unsupported unit conversion: {from_unit} -> {to_unit}"


# ---------------------------------------------------------------------------
# QR Code (optional dep — graceful fallback)
# ---------------------------------------------------------------------------

@tool(permission=ToolPermission.SAFE)
async def qr_generate(text: str, as_ascii: bool = True) -> str:
    """Generate a QR code as ASCII art or file path. Requires 'qrcode' package for image output."""
    try:
        import qrcode as qr_lib

        qr = qr_lib.QRCode()
        qr.add_data(text)
        qr.make(fit=True)
        if as_ascii:
            matrix = qr.modules
            if matrix is None:
                qr.make_image()
                matrix = qr.modules
            lines: list[str] = []
            for row in range(0, len(matrix), 2):
                line = ""
                for col in range(len(matrix[row])):
                    top = matrix[row][col]
                    bottom = matrix[row + 1][col] if row + 1 < len(matrix) else False
                    if top and bottom:
                        line += " "
                    elif top:
                        line += "\u2584"  # lower half block
                    elif bottom:
                        line += "\u2580"  # upper half block
                    else:
                        line += "\u2588"  # full block
                lines.append(line)
            return "\n".join(lines) if lines else "QR code generated (no ASCII output)"
        return "QR code generated. Use as_ascii=True for terminal output."
    except ImportError:
        return "QR code generation requires 'qrcode' package. Install with: pip install qrcode[pil]"


__all__ = [
    "base64_decode",
    "base64_encode",
    "case_convert",
    "count_chars",
    "count_words",
    "cpu_count",
    "csv_to_json",
    "current_time",
    "disk_usage",
    "dns_lookup",
    "extract_emails",
    "extract_urls",
    "file_size",
    "get_env_var",
    "hash_file",
    "hash_md5",
    "hash_sha256",
    "hash_sha512",
    "hex_decode",
    "hex_encode",
    "html_decode",
    "html_encode",
    "is_reachable",
    "json_path",
    "json_pretty",
    "json_to_csv",
    "json_validate",
    "line_count",
    "math_convert_units",
    "math_factorial",
    "math_is_prime",
    "math_sqrt",
    "mime_type",
    "nanoid",
    "ping_host",
    "platform_info",
    "port_check",
    "qr_generate",
    "random_number",
    "random_string",
    "reading_time",
    "regex_match",
    "regex_replace",
    "sleep_tool",
    "slugify",
    "strip_html",
    "text_diff",
    "timestamp",
    "truncate_text",
    "url_decode",
    "url_encode",
    "uuid4",
    "validate_email",
    "validate_ip",
    "validate_url",
]
