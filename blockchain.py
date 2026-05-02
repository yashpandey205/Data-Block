# blockchain.py
# ============================================================================
# Lightweight Blockchain Framework — Blockchain Data Structures
# ============================================================================
# Defines Transaction, Block, and Blockchain classes.
#
# Industry-grade features:
#   - Merkle root in every block for efficient transaction integrity proofs.
#   - Nonce field for future proof-of-work or protocol extensions.
#   - Block-size enforcement via MAX_TRANSACTIONS_PER_BLOCK.
#   - Full chain validation with hash-chain and Merkle-root checks.
#   - Thread-safe pending transaction pool.
# ============================================================================

import threading
import time
from utils import hash_data, compute_merkle_root, timestamp_now, get_logger
from config import MAX_TRANSACTIONS_PER_BLOCK, MIN_TRANSACTIONS_PER_BLOCK

logger = get_logger("blockchain")


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

class Transaction:
    """Represents an encrypted IoT data payload ready for inclusion in a block."""

    def __init__(self, sender: str, receiver: str, encrypted_data: str,
                 encrypted_aes_key: str):
        self.sender = sender
        self.receiver = receiver
        self.encrypted_data = encrypted_data
        self.encrypted_aes_key = encrypted_aes_key
        self.timestamp = timestamp_now()
        self.tx_id = self._calculate_hash()

    def _calculate_hash(self) -> str:
        payload = (
            f"{self.sender}{self.receiver}"
            f"{self.encrypted_data}{self.encrypted_aes_key}"
            f"{self.timestamp}"
        )
        return hash_data(payload)

    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "encrypted_data": self.encrypted_data,
            "encrypted_aes_key": self.encrypted_aes_key,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> "Transaction":
        tx = Transaction(
            sender=data["sender"],
            receiver=data["receiver"],
            encrypted_data=data["encrypted_data"],
            encrypted_aes_key=data["encrypted_aes_key"],
        )
        tx.timestamp = data["timestamp"]
        tx.tx_id = data["tx_id"]
        return tx


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

class Block:
    """
    A block containing a batch of validated transactions.

    Fields:
      - index:         Sequential block number.
      - previous_hash: SHA-256 hash of the preceding block.
      - transactions:  List of Transaction objects.
      - timestamp:     UTC creation time.
      - merkle_root:   Merkle root of all transaction hashes.
      - nonce:         Reserved for future protocol extensions.
      - hash:          SHA-256 hash of this block's header fields.
    """

    def __init__(self, index: int, previous_hash: str,
                 transactions: list, nonce: int = 0):
        self.index = index
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.nonce = nonce
        self.timestamp = timestamp_now()
        self.merkle_root = self._compute_merkle_root()
        self.hash = self.calculate_hash()

    def _compute_merkle_root(self) -> str:
        tx_hashes = [tx.tx_id for tx in self.transactions]
        return compute_merkle_root(tx_hashes)

    def calculate_hash(self) -> str:
        header = (
            f"{self.index}{self.previous_hash}{self.merkle_root}"
            f"{self.timestamp}{self.nonce}"
        )
        return hash_data(header)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "timestamp": self.timestamp,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @staticmethod
    def from_dict(data: dict) -> "Block":
        transactions = [Transaction.from_dict(tx) for tx in data["transactions"]]
        block = Block(
            index=data["index"],
            previous_hash=data["previous_hash"],
            transactions=transactions,
            nonce=data.get("nonce", 0),
        )
        block.timestamp = data["timestamp"]
        block.merkle_root = data.get("merkle_root", block._compute_merkle_root())
        block.hash = data["hash"]
        return block


# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------

class Blockchain:
    """
    In-memory blockchain ledger.

    Thread-safe for concurrent access from the Flask API thread and the
    P2P socket listener threads.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.chain: list[Block] = [self._create_genesis_block()]
        self.pending_transactions: list[Transaction] = []

    # -- Genesis block (deterministic) --------------------------------------

    @staticmethod
    def _create_genesis_block() -> Block:
        block = Block(index=0, previous_hash="0", transactions=[])
        block.timestamp = 0  # deterministic across all nodes
        block.merkle_root = block._compute_merkle_root()
        block.hash = block.calculate_hash()
        return block

    # -- Accessors ----------------------------------------------------------

    def get_latest_block(self) -> Block:
        with self._lock:
            return self.chain[-1]

    def get_chain_length(self) -> int:
        with self._lock:
            return len(self.chain)

    # -- Transaction pool ---------------------------------------------------

    def add_transaction(self, transaction: Transaction) -> bool:
        with self._lock:
            # Deduplicate
            if any(tx.tx_id == transaction.tx_id for tx in self.pending_transactions):
                return False
            self.pending_transactions.append(transaction)
            return True

    # -- Block creation (leader only) ---------------------------------------

    def create_block(self) -> Block | None:
        """Creates a candidate block from the pending transaction pool."""
        with self._lock:
            if len(self.pending_transactions) < MIN_TRANSACTIONS_PER_BLOCK:
                return None

            batch = self.pending_transactions[:MAX_TRANSACTIONS_PER_BLOCK]
            latest = self.chain[-1]
            new_block = Block(
                index=latest.index + 1,
                previous_hash=latest.hash,
                transactions=batch,
            )
            return new_block

    # -- Block commitment ---------------------------------------------------

    def add_block(self, block: Block) -> bool:
        """
        Appends a PBFT-committed block to the chain after validation.

        Validation checks:
          1. Index continuity.
          2. Previous-hash linkage.
          3. Merkle root integrity.
        """
        with self._lock:
            latest = self.chain[-1]

            if block.index != latest.index + 1:
                logger.warning(
                    "Block index mismatch: expected %d, got %d",
                    latest.index + 1,
                    block.index,
                )
                return False

            if block.previous_hash != latest.hash:
                logger.warning(
                    "Previous-hash mismatch at block %d", block.index
                )
                return False

            # Verify Merkle root
            expected_merkle = compute_merkle_root([tx.tx_id for tx in block.transactions])
            if block.merkle_root != expected_merkle:
                logger.warning(
                    "Merkle root mismatch at block %d", block.index
                )
                return False

            self.chain.append(block)

            # Remove committed transactions from the pool
            committed_ids = {tx.tx_id for tx in block.transactions}
            self.pending_transactions = [
                tx for tx in self.pending_transactions
                if tx.tx_id not in committed_ids
            ]
            logger.info(
                "Block %d committed (%d txns, hash=%s)",
                block.index,
                len(block.transactions),
                block.hash[:12],
            )
            return True

    # -- Full chain validation ----------------------------------------------

    def validate_chain(self) -> bool:
        """Validates the entire chain from genesis to tip."""
        with self._lock:
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i - 1]

                if current.hash != current.calculate_hash():
                    logger.error("Hash mismatch at block %d", current.index)
                    return False
                if current.previous_hash != previous.hash:
                    logger.error("Chain linkage broken at block %d", current.index)
                    return False

                expected_merkle = compute_merkle_root(
                    [tx.tx_id for tx in current.transactions]
                )
                if current.merkle_root != expected_merkle:
                    logger.error("Merkle root invalid at block %d", current.index)
                    return False
            return True
