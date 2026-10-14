"""FILE: vidbyte/tools/builtins/prebuilt/hashing.py

PURPOSE: Defines HashingToolFunctions, the seven prebuilt tools that compute digests and checksums: a hash of a text, a hash of Base64 content, an HMAC signature, a digest check, CRC-32 and Adler-32 checksums, a Git blob object ID, and a stable bucket assignment.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the HASHING category is chosen. Builds on PrebuiltToolSupport in _support.py for strict text encoding and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Every digest object comes from hashlib.new with usedforsecurity=False, including the ones HMAC builds through a partial constructor, so md5 and sha1 work as checksums on hosts that restrict them for security use.
FUNCTION INVENTORY: hash_text, hash_base64_content, compute_hmac, verify_hash, crc32_checksum, git_blob_hash, and assign_stable_bucket are the tools; _digest_text writes digest bytes in a DigestFormat, _hex_bytes reads hexadecimal text and _base64_bytes reads Base64 with PrebuiltToolSupport.base64_bytes, each returning None for text it cannot read; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new hashing tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.22, and its entry in tool_functions. A new algorithm is a new HashAlgorithm member whose value hashlib.new accepts.
WHAT NOT TO DO IN THIS FILE: 1. Do not create a digest without usedforsecurity=False; T-6 and the source scan require it for md5 and sha1. 2. Do not put any part of an HMAC key in an output or an error message. 3. Do not describe md5 or sha1 as secure. 4. Do not compare digests with ==; verify_hash uses hmac.compare_digest.
KNOWN EDGE CASES: Base64 content follows the base64_decode rules, so whitespace is ignored, padding is optional, and a minus sign or underscore selects the URL-safe alphabet. A hexadecimal string is also valid Base64, so verify_hash tries both readings and only the one with the digest's length can match. The utf_16 and utf_32 codecs add a byte-order mark, which changes every digest.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.22, section 9.2 items 2, 13, and the DigestFormat rule, section 10 T-3 and T-6); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_formats_encoding.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import zlib
from functools import partial
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_BUCKETS,
    PREBUILT_MAX_ENCODED_TEXT_CHARS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    DigestFormat,
    HashAlgorithm,
    KeyFormat,
    TextEncoding,
)
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_HEX_DIGITS = re.compile(r"[0-9A-Fa-f]*")
_BUCKET_PREFIX_DIGITS = 16
_HEX_BASE = 16
_BASE64_EXPECTED = "Base64 text in either the standard or the URL-safe alphabet, with whitespace ignored and padding optional"
_KEY_FORMAT_EXPECTED = MappingProxyType({KeyFormat.HEX: "an even number of hexadecimal digits, with whitespace ignored", KeyFormat.BASE64: _BASE64_EXPECTED})

_ALGORITHM_DESCRIPTION = "The digest algorithm to use. The values md5 and sha1 are suitable only for checksums and legacy identifiers, not for security, while the SHA-2, SHA-3, and BLAKE2 algorithms are current cryptographic hashes. The digest length depends on the algorithm. The default is sha256."
_DIGEST_FORMAT_DESCRIPTION = "How the digest bytes are written. The value hex gives lowercase hexadecimal, base64 gives standard Base64 with its padding, and base64url gives URL-safe Base64 with no padding. All three formats hold the same bytes. The default is hex."
_TEXT_ENCODING_DESCRIPTION = "The character encoding that turns the text into the bytes being hashed. Encoding is strict, so a character the codec cannot represent fails with an error naming its position. The utf_16 and utf_32 codecs start the bytes with a byte-order mark, while their _le and _be variants do not. The default is utf_8."
_HASHED_TEXT_DESCRIPTION = "The text to hash, given as plain characters. It is turned into bytes with text_encoding before hashing, so the same text gives different digests in different encodings. Empty text has a well-defined digest of its own. The text may hold at most one million characters."


class HashingToolFunctions:
    """The hashing category: digests, HMAC signatures, checksums, Git object IDs, and stable buckets."""

    @staticmethod
    def hash_text(
        text: Annotated[str, Field(description=_HASHED_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        algorithm: Annotated[HashAlgorithm, Field(description=_ALGORITHM_DESCRIPTION)] = HashAlgorithm.SHA256,
        text_encoding: Annotated[TextEncoding, Field(description=_TEXT_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
        digest_format: Annotated[DigestFormat, Field(description=_DIGEST_FORMAT_DESCRIPTION)] = DigestFormat.HEX,
    ) -> PrebuiltToolOutput:
        """Compute the hash digest of a text with a chosen algorithm and return it as hexadecimal, Base64, or Base64url. Use it to fingerprint content, to compare texts without sending them, or to reproduce a digest another system expects. The text is first turned into bytes with text_encoding, and md5 and sha1 are offered for checksums only, not for security. A character the encoding cannot represent fails with an error naming text."""
        raw = PrebuiltToolSupport.encode_text(text, text_encoding, "text")
        digest = hashlib.new(algorithm.value, raw, usedforsecurity=False).digest()
        return {"digest": HashingToolFunctions._digest_text(digest, digest_format), "algorithm": algorithm.value}

    @staticmethod
    def hash_base64_content(
        data_base64: Annotated[str, Field(description="The binary content to hash, written as Base64 in the standard or the URL-safe alphabet. Spaces and line breaks are ignored, and the trailing equals signs may be left out. A mix of both alphabets or any other character makes the call fail. The text may hold at most two million characters.", max_length=PREBUILT_MAX_ENCODED_TEXT_CHARS)],
        algorithm: Annotated[HashAlgorithm, Field(description=_ALGORITHM_DESCRIPTION)] = HashAlgorithm.SHA256,
        digest_format: Annotated[DigestFormat, Field(description=_DIGEST_FORMAT_DESCRIPTION)] = DigestFormat.HEX,
    ) -> PrebuiltToolOutput:
        """Compute the hash digest of binary content given as Base64 and return it with the content size in bytes. Use it to checksum a file, an attachment, or any other binary payload that arrives Base64-encoded. Whitespace is ignored, missing padding is tolerated, the alphabet is detected from the characters, and md5 and sha1 are offered for checksums only, not for security. Text that is not valid Base64 fails with an error naming data_base64."""
        raw = HashingToolFunctions._base64_bytes(data_base64)
        if raw is None:
            raise PrebuiltToolSupport.argument_error("data_base64", "the text is not valid Base64 in one alphabet", _BASE64_EXPECTED)
        digest = hashlib.new(algorithm.value, raw, usedforsecurity=False).digest()
        return {"digest": HashingToolFunctions._digest_text(digest, digest_format), "algorithm": algorithm.value, "size_bytes": len(raw)}

    @staticmethod
    def compute_hmac(
        message: Annotated[str, Field(description="The message to sign, given as plain characters. It is turned into bytes as UTF-8 before signing. Empty text is a valid message. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        key: Annotated[str, Field(description="The signing key, written as plain text, hexadecimal, or Base64 according to key_format. It must hold at least one character and at most ten thousand. The key never appears in the result or in an error message. A key longer than the block size of the hash is hashed first, as HMAC requires.", min_length=1, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        key_format: Annotated[KeyFormat, Field(description="How the key is written. The value text signs with the UTF-8 bytes of the key, hex reads pairs of hexadecimal digits, and base64 reads Base64 in either alphabet with padding optional. Whitespace inside a hex or base64 key is ignored, and a key that is not valid in its format fails with an error. The default is text.")] = KeyFormat.TEXT,
        algorithm: Annotated[HashAlgorithm, Field(description=_ALGORITHM_DESCRIPTION)] = HashAlgorithm.SHA256,
        digest_format: Annotated[DigestFormat, Field(description=_DIGEST_FORMAT_DESCRIPTION)] = DigestFormat.HEX,
    ) -> PrebuiltToolOutput:
        """Compute an HMAC signature of a message with a key and a chosen hash algorithm, and return the digest. Use it to sign a webhook payload, to reproduce a signature another system sent, or to derive a keyed fingerprint. The message is signed as UTF-8, the key is read as text, hexadecimal, or Base64 according to key_format, and md5 and sha1 are offered for older systems, not for new security designs. A key that is not valid for its key_format fails with an error naming key, and neither the result nor any error repeats the key."""
        # @intent prebuilt-hmac-key-never-echoed
        # The key is a credential, so a key that does not decode fails
        # with an error that names only its format, never any of its
        # characters, and the result holds the digest alone.
        match key_format:
            case KeyFormat.HEX:
                key_bytes = HashingToolFunctions._hex_bytes(key)
            case KeyFormat.BASE64:
                key_bytes = HashingToolFunctions._base64_bytes(key)
            case _:
                key_bytes = PrebuiltToolSupport.encode_text(key, TextEncoding.UTF_8, "key")
        if key_bytes is None:
            raise PrebuiltToolSupport.argument_error("key", f"the key is not valid {key_format.value} text", _KEY_FORMAT_EXPECTED[key_format])

        # Sign the UTF-8 message, building each inner digest through
        # hashlib.new so md5 and sha1 count as non-security use.
        message_bytes = PrebuiltToolSupport.encode_text(message, TextEncoding.UTF_8, "message")
        digest_constructor = partial(hashlib.new, algorithm.value, usedforsecurity=False)
        digest = hmac.new(key_bytes, message_bytes, digest_constructor).digest()
        return {"digest": HashingToolFunctions._digest_text(digest, digest_format), "algorithm": algorithm.value}

    @staticmethod
    def verify_hash(
        text: Annotated[str, Field(description=_HASHED_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        expected_digest: Annotated[str, Field(description="The digest the text is expected to have. It may be hexadecimal in either case, standard Base64, or URL-safe Base64 with or without padding. Whitespace in it is ignored. The text must hold at least one character and at most two hundred.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        algorithm: Annotated[HashAlgorithm, Field(description=_ALGORITHM_DESCRIPTION)] = HashAlgorithm.SHA256,
        text_encoding: Annotated[TextEncoding, Field(description=_TEXT_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Check whether a text hashes to an expected digest, and return the result with the digest actually computed in lowercase hexadecimal. Use it to confirm a download, a stored fingerprint, or a checksum quoted in documentation. The expected digest may be hexadecimal in any case, Base64, or Base64url, and the comparison runs in constant time. A digest that decodes in no format or has the wrong length simply does not match, and only a character the encoding cannot represent fails with an error naming text."""
        # Hash the text the same way hash_text does.
        raw = PrebuiltToolSupport.encode_text(text, text_encoding, "text")
        digest = hashlib.new(algorithm.value, raw, usedforsecurity=False).digest()

        # Read the expected digest as hexadecimal and as Base64, since
        # hex text is valid Base64 too; a reading of the wrong length
        # never matches.
        readings = (HashingToolFunctions._hex_bytes(expected_digest), HashingToolFunctions._base64_bytes(expected_digest))
        matches = any(reading is not None and hmac.compare_digest(reading, digest) for reading in readings)
        return {"matches": matches, "computed_hex": digest.hex()}

    @staticmethod
    def crc32_checksum(
        text: Annotated[str, Field(description="The text to checksum, given as plain characters. It is turned into bytes with text_encoding first. Empty text has a CRC-32 of zero and an Adler-32 of one. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description=_TEXT_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Compute the CRC-32 and Adler-32 checksums of a text, with the CRC-32 as both hexadecimal and a decimal integer. Use it to reproduce a checksum that a ZIP, PNG, or gzip file holds, or to compare texts quickly where security does not matter. Hex values have exactly eight lowercase digits, and the text is first turned into bytes with text_encoding. These checksums detect accidental changes only, and a character the encoding cannot represent fails with an error naming text."""
        raw = PrebuiltToolSupport.encode_text(text, text_encoding, "text")
        crc = zlib.crc32(raw)
        return {"crc32_hex": f"{crc:08x}", "crc32_decimal": crc, "adler32_hex": f"{zlib.adler32(raw):08x}"}

    @staticmethod
    def git_blob_hash(
        content: Annotated[str, Field(description="The file content to hash, given as plain characters. It is turned into bytes with text_encoding, and line endings are kept exactly as given. Empty content gives the object ID of the empty blob. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description=_TEXT_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Compute the Git object ID that a text would have when stored as a file blob, with its size in bytes. Use it to check whether file content matches a blob in a repository, or to predict an ID before committing. The ID is the SHA-1 of the blob header followed by the bytes, line endings are not changed, and SHA-1 is used here only because Git defines it, not for security. A character the encoding cannot represent fails with an error naming content."""
        raw = PrebuiltToolSupport.encode_text(content, text_encoding, "content")
        blob = hashlib.new("sha1", f"blob {len(raw)}\0".encode("ascii"), usedforsecurity=False)
        blob.update(raw)
        return {"object_id": blob.hexdigest(), "size_bytes": len(raw)}

    @staticmethod
    def assign_stable_bucket(
        key: Annotated[str, Field(description="The key to place in a bucket, given as plain characters. The same key, salt, and bucket count always give the same bucket. Keys are compared exactly, with case and whitespace kept. The text must hold at least one character and at most ten thousand.", min_length=1, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        buckets: Annotated[int, Field(description="How many buckets there are. The result is a bucket number from zero to one less than this value. Changing the count moves most keys to other buckets. The value must be between 1 and 1,000,000.", ge=1, le=PREBUILT_MAX_BUCKETS)],
        salt: Annotated[str, Field(description="Text hashed in front of the key, so different experiments split the same keys differently. It is joined to the key with a colon. The default is empty text. The text may hold at most ten thousand characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)] = "",
    ) -> PrebuiltToolOutput:
        """Assign a key to one of a fixed number of buckets in a way that is stable across processes, machines, and versions. Use it for experiment groups, sharding, or sampling, where the same key must always land in the same bucket. The bucket is the first sixteen hexadecimal digits of the SHA-256 of the salt, a colon, and the key in UTF-8, read as an integer modulo buckets. The tool has no failure case beyond the parameter caps."""
        material = PrebuiltToolSupport.encode_text(salt, TextEncoding.UTF_8, "salt") + b":" + PrebuiltToolSupport.encode_text(key, TextEncoding.UTF_8, "key")
        prefix = hashlib.new("sha256", material, usedforsecurity=False).hexdigest()[:_BUCKET_PREFIX_DIGITS]
        return {"bucket": int(prefix, _HEX_BASE) % buckets, "hash_prefix": prefix}

    @staticmethod
    def _digest_text(digest: bytes, digest_format: DigestFormat) -> str:
        """Write digest bytes as lowercase hex, padded Base64, or unpadded Base64url."""
        match digest_format:
            case DigestFormat.BASE64:
                return base64.b64encode(digest).decode("ascii")
            case DigestFormat.BASE64URL:
                return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
            case _:
                return digest.hex()

    @staticmethod
    def _hex_bytes(text: str) -> bytes | None:
        """Read hexadecimal digits in pairs, ignoring whitespace, or return None when the text is not hexadecimal."""
        digits = "".join(text.split())
        if _HEX_DIGITS.fullmatch(digits) is None or len(digits) % 2:
            return None
        return bytes.fromhex(digits)

    @staticmethod
    def _base64_bytes(text: str) -> bytes | None:
        """Read Base64 with the shared reader and its alphabet detection, or return None when the text is not Base64."""
        # The shared reader's error is dropped, because each caller
        # reports its own, and a key's error must not describe the key.
        try:
            return PrebuiltToolSupport.base64_bytes(text, None, "text")
        except ToolExecutionError:
            return None

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.hash_text,
            cls.hash_base64_content,
            cls.compute_hmac,
            cls.verify_hash,
            cls.crc32_checksum,
            cls.git_blob_hash,
            cls.assign_stable_bucket,
        )


__all__ = ["HashingToolFunctions"]
