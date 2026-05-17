"""Lossless QR payload encoding for full client JSON exports."""

from dataclasses import dataclass
import hashlib
import json
import math
import zlib


BASE45_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
QR_JSON_PREFIX = "SBOX:ZLIB45"
RAW_JSON_MODE = "raw"
COMPRESSED_JSON_MODE = "compressed"
MULTIPART_JSON_MODE = "multipart"
DEFAULT_CHUNK_BODY_SIZE = 3500

_BASE45_INDEX = {char: index for index, char in enumerate(BASE45_ALPHABET)}


@dataclass(frozen=True)
class QRJsonPayloadPlan:
    mode: str
    tokens: tuple
    original_chars: int
    compressed_bytes: int
    encoded_chars: int
    sha256: str


def compact_json(data):
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def base45_encode(data):
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("base45_encode expects bytes")

    encoded = []
    index = 0
    while index < len(data):
        if index + 1 < len(data):
            value = data[index] * 256 + data[index + 1]
            encoded.append(BASE45_ALPHABET[value % 45])
            encoded.append(BASE45_ALPHABET[(value // 45) % 45])
            encoded.append(BASE45_ALPHABET[value // (45 * 45)])
            index += 2
        else:
            value = data[index]
            encoded.append(BASE45_ALPHABET[value % 45])
            encoded.append(BASE45_ALPHABET[value // 45])
            index += 1
    return "".join(encoded)


def base45_decode(text):
    if not isinstance(text, str):
        raise TypeError("base45_decode expects str")

    decoded = bytearray()
    index = 0
    while index < len(text):
        remaining = len(text) - index
        if remaining == 1:
            raise ValueError("invalid base45 length")

        try:
            c = _BASE45_INDEX[text[index]]
            d = _BASE45_INDEX[text[index + 1]]
        except KeyError as exc:
            raise ValueError(f"invalid base45 character: {exc.args[0]!r}") from exc

        if remaining >= 3:
            try:
                e = _BASE45_INDEX[text[index + 2]]
            except KeyError as exc:
                raise ValueError(f"invalid base45 character: {exc.args[0]!r}") from exc
            value = c + d * 45 + e * 45 * 45
            if value > 0xFFFF:
                raise ValueError("invalid base45 word")
            decoded.extend((value // 256, value % 256))
            index += 3
        else:
            value = c + d * 45
            if value > 0xFF:
                raise ValueError("invalid base45 byte")
            decoded.append(value)
            index += 2

    return bytes(decoded)


def _json_sha256(json_text):
    return hashlib.sha256(json_text.encode("utf-8")).hexdigest().upper()


def _single_token(sha256, encoded):
    return f"{QR_JSON_PREFIX}:1:{sha256}:{encoded}"


def _multipart_tokens(sha256, encoded, chunk_body_size):
    if chunk_body_size < 1:
        raise ValueError("chunk_body_size must be >= 1")

    total = max(1, math.ceil(len(encoded) / chunk_body_size))
    tokens = []
    for index in range(total):
        start = index * chunk_body_size
        chunk = encoded[start:start + chunk_body_size]
        tokens.append(f"{QR_JSON_PREFIX}:2:{sha256}:{index + 1}:{total}:{chunk}")
    return tuple(tokens)


def make_qr_json_payload_plan(config, token_fits, chunk_body_size=DEFAULT_CHUNK_BODY_SIZE):
    """Return raw, compressed, or multipart QR tokens for a full config.

    ``token_fits`` is a callback supplied by the QR renderer. It keeps this
    module independent of the optional ``qrcode`` package and lets tests force
    specific fallback paths.
    """
    json_text = compact_json(config)
    sha256 = _json_sha256(json_text)

    if token_fits(json_text):
        return QRJsonPayloadPlan(
            mode=RAW_JSON_MODE,
            tokens=(json_text,),
            original_chars=len(json_text),
            compressed_bytes=0,
            encoded_chars=0,
            sha256=sha256,
        )

    compressed = zlib.compress(json_text.encode("utf-8"), level=9)
    encoded = base45_encode(compressed)
    single = _single_token(sha256, encoded)
    if token_fits(single):
        return QRJsonPayloadPlan(
            mode=COMPRESSED_JSON_MODE,
            tokens=(single,),
            original_chars=len(json_text),
            compressed_bytes=len(compressed),
            encoded_chars=len(encoded),
            sha256=sha256,
        )

    body_size = min(max(1, chunk_body_size), max(1, len(encoded)))
    while body_size >= 1:
        tokens = _multipart_tokens(sha256, encoded, body_size)
        if all(token_fits(token) for token in tokens):
            return QRJsonPayloadPlan(
                mode=MULTIPART_JSON_MODE,
                tokens=tokens,
                original_chars=len(json_text),
                compressed_bytes=len(compressed),
                encoded_chars=len(encoded),
                sha256=sha256,
            )
        if body_size == 1:
            break
        body_size = max(1, body_size // 2)

    raise ValueError("unable to split payload into QR-sized chunks")


def _decode_compressed_payload(expected_sha256, encoded):
    compressed = base45_decode(encoded)
    try:
        json_text = zlib.decompress(compressed).decode("utf-8")
    except (zlib.error, UnicodeDecodeError) as exc:
        raise ValueError("payload is not valid zlib-compressed UTF-8 JSON") from exc

    actual_sha256 = _json_sha256(json_text)
    if actual_sha256 != expected_sha256:
        raise ValueError("payload checksum mismatch")

    try:
        json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError("decoded payload is not valid JSON") from exc
    return json_text


def decode_qr_json_tokens(tokens):
    material = [token.rstrip("\r\n") for token in tokens if token.rstrip("\r\n") != ""]
    if not material:
        raise ValueError("no QR payload tokens provided")

    if len(material) == 1 and material[0].startswith("{"):
        try:
            json.loads(material[0])
        except json.JSONDecodeError as exc:
            raise ValueError("raw QR payload is not valid JSON") from exc
        return material[0]

    if not all(token.startswith(f"{QR_JSON_PREFIX}:") for token in material):
        raise ValueError(f"expected raw JSON or {QR_JSON_PREFIX} tokens")

    first_header = material[0].split(":", 3)
    if len(first_header) < 3:
        raise ValueError("invalid QR payload header")

    if first_header[2] == "1":
        if len(material) != 1:
            raise ValueError("single QR payload cannot be combined with other tokens")
        parts = material[0].split(":", 4)
        if len(parts) != 5 or parts[0] != "SBOX" or parts[1] != "ZLIB45":
            raise ValueError("invalid single QR payload header")
        return _decode_compressed_payload(parts[3], parts[4])

    if first_header[2] != "2":
        raise ValueError("unsupported QR payload version")

    chunks = {}
    expected_sha256 = None
    expected_total = None
    for token in material:
        parts = token.split(":", 6)
        if len(parts) != 7 or parts[0] != "SBOX" or parts[1] != "ZLIB45" or parts[2] != "2":
            raise ValueError("invalid multipart QR payload header")

        sha256 = parts[3]
        try:
            index = int(parts[4])
            total = int(parts[5])
        except ValueError as exc:
            raise ValueError("multipart QR payload has invalid index") from exc

        if total < 1 or index < 1 or index > total:
            raise ValueError("multipart QR payload index is out of range")

        if expected_sha256 is None:
            expected_sha256 = sha256
            expected_total = total
        elif expected_sha256 != sha256 or expected_total != total:
            raise ValueError("multipart QR payload tokens do not belong together")

        body = parts[6]
        if index in chunks and chunks[index] != body:
            raise ValueError("multipart QR payload has conflicting duplicate chunk")
        chunks[index] = body

    missing = [str(index) for index in range(1, expected_total + 1) if index not in chunks]
    if missing:
        raise ValueError(f"missing multipart QR chunk(s): {', '.join(missing)}")

    encoded = "".join(chunks[index] for index in range(1, expected_total + 1))
    return _decode_compressed_payload(expected_sha256, encoded)
