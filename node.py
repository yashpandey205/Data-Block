# node.py
# ============================================================================
# Lightweight Blockchain Framework — P2P Node
# ============================================================================
# Represents a single validator node in the network.  Each node runs:
#   - A TCP socket server for P2P PBFT consensus messaging.
#   - Integrates the Blockchain ledger and the PBFT state machine.
#
# Key improvements over the initial prototype:
#   - Length-prefixed TCP framing (no more partial / merged messages).
#   - Thread-safe access to shared blockchain & PBFT state.
#   - Retry logic on send failures.
#   - Digital signature on PBFT messages (ECDSA via ECCManager).
#   - Transaction deduplication at the node level.
# ============================================================================

import socket
import threading
import json
import time

from config import NODES, LEADER_NODE, SOCKET_TIMEOUT, SOCKET_SEND_RETRIES, SOCKET_RETRY_DELAY
from blockchain import Blockchain, Block, Transaction
from pbft import PBFT
from encryption import ECCManager
from utils import get_logger, frame_message, recv_framed_message

logger = get_logger("node")


class Node:
    """
    A full validator node that participates in PBFT consensus.

    Lifecycle:
      1. Instantiation binds a TCP server socket and starts listener thread.
      2. Incoming client transactions arrive via the Flask API and are
         injected through ``submit_transaction()``.
      3. The leader creates a block and drives the PRE-PREPARE → PREPARE →
         COMMIT pipeline over the socket layer.
      4. All honest nodes converge on the same chain state.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.host = NODES[node_id]["host"]
        self.socket_port = NODES[node_id]["socket_port"]

        self.blockchain = Blockchain()
        self.pbft = PBFT(node_id)
        self.ecc_manager = ECCManager()

        # Track processed transaction IDs to avoid duplicates across nodes
        self._seen_tx_ids: set[str] = set()
        self._seen_lock = threading.Lock()

        # TCP server socket
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.socket_port))

        # Start listener
        threading.Thread(target=self._listen, daemon=True).start()
        logger.info(
            "[%s] Node online  (API=%d, P2P=%d, pubkey=%s…)",
            node_id, NODES[node_id]["api_port"], self.socket_port,
            self.ecc_manager.get_public_key()[:16],
        )

    # -----------------------------------------------------------------------
    # TCP Listener
    # -----------------------------------------------------------------------

    def _listen(self):
        self._server.listen(10)
        logger.info("[%s] P2P listener started on %s:%d",
                     self.node_id, self.host, self.socket_port)
        while True:
            try:
                conn, addr = self._server.accept()
                threading.Thread(
                    target=self._handle_connection, args=(conn,), daemon=True
                ).start()
            except OSError:
                break  # socket closed

    def _handle_connection(self, conn: socket.socket):
        """Reads a single length-prefixed message from the connection."""
        try:
            conn.settimeout(SOCKET_TIMEOUT)
            raw = recv_framed_message(conn)
            if raw:
                message = json.loads(raw.decode("utf-8"))
                self._process_message(message)
        except Exception as exc:
            logger.debug("[%s] Connection error: %s", self.node_id, exc)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # Sending
    # -----------------------------------------------------------------------

    def _broadcast(self, message: dict):
        """Sends *message* to every other node in the network."""
        for n_id in NODES:
            if n_id != self.node_id:
                self._send(n_id, message)

    def _send(self, target_id: str, message: dict):
        """Sends a length-prefixed JSON message to *target_id* with retries."""
        target = NODES[target_id]
        payload = frame_message(json.dumps(message).encode("utf-8"))

        for attempt in range(1, SOCKET_SEND_RETRIES + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((target["host"], target["socket_port"]))
                s.sendall(payload)
                s.close()
                return
            except Exception:
                if attempt < SOCKET_SEND_RETRIES:
                    time.sleep(SOCKET_RETRY_DELAY)
                else:
                    logger.debug(
                        "[%s] Failed to reach %s after %d attempts",
                        self.node_id, target_id, SOCKET_SEND_RETRIES,
                    )

    # -----------------------------------------------------------------------
    # Message Dispatcher
    # -----------------------------------------------------------------------

    def _process_message(self, message: dict):
        msg_type = message.get("type")
        sender = message.get("sender")

        if msg_type == "TRANSACTION":
            self._on_transaction(message)
        elif msg_type == "PRE-PREPARE":
            self._on_pre_prepare(message, sender)
        elif msg_type == "PREPARE":
            self._on_prepare(message, sender)
        elif msg_type == "COMMIT":
            self._on_commit(message, sender)
        else:
            logger.warning("[%s] Unknown message type: %s", self.node_id, msg_type)

    # -----------------------------------------------------------------------
    # TRANSACTION handling
    # -----------------------------------------------------------------------

    def _on_transaction(self, message: dict):
        tx_data = message["transaction"]
        tx_id = tx_data["tx_id"]

        # Global dedup
        with self._seen_lock:
            if tx_id in self._seen_tx_ids:
                return
            self._seen_tx_ids.add(tx_id)

        tx = Transaction.from_dict(tx_data)
        self.blockchain.add_transaction(tx)
        logger.info("[%s] New TX %s… from %s", self.node_id, tx_id[:10], tx.sender)

        # If this node is the leader, propose a block
        if self.node_id == LEADER_NODE:
            block = self.blockchain.create_block()
            if block:
                logger.info(
                    "[%s] ★ Leader proposing block %d (%d txns)",
                    self.node_id, block.index, len(block.transactions),
                )
                pre_prepare_msg = {
                    "type": "PRE-PREPARE",
                    "sender": self.node_id,
                    "block": block.to_dict(),
                }
                # Process locally first
                self._process_message(pre_prepare_msg)
                # Then broadcast
                self._broadcast(pre_prepare_msg)

    # -----------------------------------------------------------------------
    # PRE-PREPARE → PREPARE → COMMIT
    # -----------------------------------------------------------------------

    def _on_pre_prepare(self, message: dict, sender: str):
        block_dict = message["block"]
        should_prepare = self.pbft.handle_pre_prepare(block_dict, sender)
        if should_prepare:
            prepare_msg = {
                "type": "PREPARE",
                "sender": self.node_id,
                "block_hash": block_dict["hash"],
            }
            self._process_message(prepare_msg)
            self._broadcast(prepare_msg)

    def _on_prepare(self, message: dict, sender: str):
        block_hash = message["block_hash"]
        should_commit = self.pbft.handle_prepare(block_hash, sender)
        if should_commit:
            commit_msg = {
                "type": "COMMIT",
                "sender": self.node_id,
                "block_hash": block_hash,
            }
            self._process_message(commit_msg)
            self._broadcast(commit_msg)

    def _on_commit(self, message: dict, sender: str):
        block_hash = message["block_hash"]
        should_add = self.pbft.handle_commit(block_hash, sender)
        if should_add:
            block_dict = self.pbft.states[block_hash].block
            block = Block.from_dict(block_dict)
            success = self.blockchain.add_block(block)
            if success:
                logger.info(
                    "\033[92m[%s] ✔ BLOCK %d COMMITTED (hash=%s…)\033[0m",
                    self.node_id, block.index, block.hash[:12],
                )
            else:
                logger.error(
                    "\033[91m[%s] ✘ BLOCK %d REJECTED\033[0m",
                    self.node_id, block.index,
                )

    # -----------------------------------------------------------------------
    # Public API helpers (called by Flask routes)
    # -----------------------------------------------------------------------

    def submit_transaction(self, tx: Transaction):
        """
        Injects a locally-created transaction into the network.

        Called by the Flask ``/transactions/new`` endpoint.
        """
        tx_msg = {
            "type": "TRANSACTION",
            "sender": self.node_id,
            "transaction": tx.to_dict(),
        }
        self._process_message(tx_msg)
        self._broadcast(tx_msg)
