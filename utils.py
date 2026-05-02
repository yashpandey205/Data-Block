# utils.py
# ============================================================================
# Lightweight Blockchain Framework — Utilities
# ============================================================================
# Provides hashing, timestamping, Merkle tree computation, structured logging,
# and message framing helpers used across the entire framework.
# ============================================================================

import hashlib
import json
import time
import struct
import logging
from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, MSG_HEADER_SIZE


def get_logger(name: str) -> logging.Logger:
    """Creates a consistently-formatted logger for any module."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(LOG_LEVEL)
    return logger


def hash_data(data) -> str:
    """Returns the SHA-256 hex digest of arbitrary data."""
    if isinstance(data, dict):
        data_str = json.dumps(data, sort_keys=True)
    elif isinstance(data, str):
        data_str = data
    else:
        data_str = str(data)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()


def compute_merkle_root(tx_hashes: list) -> str:
    """
    Computes the Merkle root of a list of transaction hashes.

    The Merkle root allows efficient and secure verification of transaction
    integrity.  If the list is empty, returns the hash of an empty string.
    Odd-length layers are handled by duplicating the last hash.
    """
    if not tx_hashes:
        return hash_data("")

    # Work on a copy
    current_level = list(tx_hashes)

    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            next_level.append(hash_data(left + right))
        current_level = next_level

    return current_level[0]


def timestamp_now() -> float:
    """Returns the current UTC timestamp as a float (seconds since epoch)."""
    return time.time()


# ---------------------------------------------------------------------------
# Length-prefixed message framing for reliable TCP communication
# ---------------------------------------------------------------------------

def frame_message(data: bytes) -> bytes:
    """
    Prepends a 4-byte big-endian length header to *data*.

    This is critical for TCP which is a stream protocol — without framing,
    message boundaries are lost and recv() may return partial messages or
    multiple messages concatenated together.
    """
    length = len(data)
    return struct.pack("!I", length) + data


def recv_framed_message(sock) -> bytes | None:
    """
    Reads a length-prefixed message from *sock*.

    Returns the complete message payload, or None on connection close / error.
    """
    header = _recv_exact(sock, MSG_HEADER_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack("!I", header)
    return _recv_exact(sock, length)


def _recv_exact(sock, num_bytes: int) -> bytes | None:
    """Reads exactly *num_bytes* from *sock*, handling partial reads."""
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
