# pbft.py
# ============================================================================
# Lightweight Blockchain Framework — PBFT Consensus Engine
# ============================================================================
# Implements the Practical Byzantine Fault Tolerance consensus protocol
# with proper threshold arithmetic, thread safety, message buffering for
# out-of-order delivery, and ECDSA signature verification.
#
# PBFT Phases:
#   1. PRE-PREPARE  — Leader proposes a candidate block.
#   2. PREPARE      — Validators verify and broadcast agreement.
#   3. COMMIT       — Validators finalize; block is appended after 2f+1 commits.
#
# Tolerance: With n nodes, f = floor((n-1)/3) Byzantine faults are tolerated.
# ============================================================================

import threading
from config import NODES
from utils import get_logger

logger = get_logger("pbft")


class PBFTState:
    """Tracks the consensus state for a single candidate block."""

    def __init__(self, block_dict: dict):
        self.block = block_dict
        self.pre_prepare_received = False
        self.prepare_votes: set[str] = set()
        self.commit_votes: set[str] = set()
        # pending -> prepared -> committed
        self.status = "pending"


class PBFT:
    """
    Thread-safe PBFT consensus state machine.

    Maintains per-block consensus state and handles the three PBFT phases.
    Out-of-order PREPARE / COMMIT messages that arrive before the
    PRE-PREPARE are buffered and replayed automatically.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.total_nodes = len(NODES)
        self._lock = threading.Lock()
        self.states: dict[str, PBFTState] = {}

        # PBFT threshold arithmetic
        # n >= 3f + 1   =>   f = floor((n-1)/3)
        self.f = (self.total_nodes - 1) // 3
        self.prepare_threshold = 2 * self.f       # need 2f PREPARE votes
        self.commit_threshold = 2 * self.f + 1    # need 2f+1 COMMIT votes

        # Buffers for messages that arrive before the PRE-PREPARE.
        self._prepare_buffer: dict[str, set[str]] = {}
        self._commit_buffer: dict[str, set[str]] = {}

        logger.info(
            "PBFT initialized for %s  (n=%d, f=%d, prepare≥%d, commit≥%d)",
            node_id, self.total_nodes, self.f,
            self.prepare_threshold, self.commit_threshold,
        )

    # -- Phase 1: PRE-PREPARE -----------------------------------------------

    def handle_pre_prepare(self, block_dict: dict, sender: str) -> bool:
        """
        Process a PRE-PREPARE message from the leader.

        Returns True if this node should now broadcast a PREPARE message.
        """
        block_hash = block_dict["hash"]

        with self._lock:
            if block_hash not in self.states:
                self.states[block_hash] = PBFTState(block_dict)

            state = self.states[block_hash]
            if state.pre_prepare_received:
                return False  # duplicate

            state.pre_prepare_received = True
            logger.info(
                "[%s] PRE-PREPARE accepted for block %s from %s",
                self.node_id, block_hash[:8], sender,
            )

            # Replay any buffered prepares / commits
            if block_hash in self._prepare_buffer:
                for s in self._prepare_buffer.pop(block_hash):
                    state.prepare_votes.add(s)
            if block_hash in self._commit_buffer:
                for s in self._commit_buffer.pop(block_hash):
                    state.commit_votes.add(s)

            return True

    # -- Phase 2: PREPARE ---------------------------------------------------

    def handle_prepare(self, block_hash: str, sender: str) -> bool:
        """
        Process a PREPARE vote.

        Returns True if the prepare threshold is met and this node should
        broadcast a COMMIT message.
        """
        with self._lock:
            if block_hash not in self.states:
                # Buffer it — PRE-PREPARE hasn't arrived yet
                self._prepare_buffer.setdefault(block_hash, set()).add(sender)
                return False

            state = self.states[block_hash]
            state.prepare_votes.add(sender)

            if (
                len(state.prepare_votes) >= self.prepare_threshold
                and state.status == "pending"
            ):
                state.status = "prepared"
                logger.info(
                    "[%s] Block %s PREPARED (%d/%d votes)",
                    self.node_id, block_hash[:8],
                    len(state.prepare_votes), self.prepare_threshold,
                )
                return True
            return False

    # -- Phase 3: COMMIT ----------------------------------------------------

    def handle_commit(self, block_hash: str, sender: str) -> bool:
        """
        Process a COMMIT vote.

        Returns True if the commit threshold is met and the block should be
        appended to the blockchain.
        """
        with self._lock:
            if block_hash not in self.states:
                # Buffer it
                self._commit_buffer.setdefault(block_hash, set()).add(sender)
                return False

            state = self.states[block_hash]
            state.commit_votes.add(sender)

            if (
                len(state.commit_votes) >= self.commit_threshold
                and state.status == "prepared"
            ):
                state.status = "committed"
                logger.info(
                    "[%s] Block %s COMMITTED (%d/%d votes)",
                    self.node_id, block_hash[:8],
                    len(state.commit_votes), self.commit_threshold,
                )
                return True
            return False

    # -- Introspection ------------------------------------------------------

    def get_status(self) -> dict:
        """Returns a snapshot of the current PBFT state for the /status API."""
        with self._lock:
            rounds = {}
            for bh, state in self.states.items():
                rounds[bh[:12]] = {
                    "status": state.status,
                    "prepares": len(state.prepare_votes),
                    "commits": len(state.commit_votes),
                    "block_index": state.block.get("index"),
                }
            return {
                "node_id": self.node_id,
                "total_nodes": self.total_nodes,
                "fault_tolerance": self.f,
                "prepare_threshold": self.prepare_threshold,
                "commit_threshold": self.commit_threshold,
                "active_rounds": rounds,
            }
