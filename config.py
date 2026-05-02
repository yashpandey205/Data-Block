# config.py
# ============================================================================
# Lightweight Blockchain Framework — Configuration
# ============================================================================
# Centralized configuration for all system parameters including network
# topology, consensus thresholds, block constraints, and encryption settings.
# ============================================================================

import logging
import os

# ---------------------------------------------------------------------------
# Network Topology
# ---------------------------------------------------------------------------
# Static node registry for local multi-node simulation.
# For n nodes, PBFT requires n >= 3f + 1 to tolerate f Byzantine faults.
# With n = 4, f = 1 (tolerates 1 faulty/malicious node).
# Each node has:
#   - api_port:    Flask REST API for client interaction
#   - socket_port: Raw TCP socket for P2P PBFT consensus messaging

NODES = {
    "node_1": {"host": "127.0.0.1", "api_port": 5001, "socket_port": 6001},
    "node_2": {"host": "127.0.0.1", "api_port": 5002, "socket_port": 6002},
    "node_3": {"host": "127.0.0.1", "api_port": 5003, "socket_port": 6003},
    "node_4": {"host": "127.0.0.1", "api_port": 5004, "socket_port": 6004},
}

# ---------------------------------------------------------------------------
# PBFT Consensus Parameters
# ---------------------------------------------------------------------------

# The initial leader (primary) that proposes blocks.
LEADER_NODE = "node_1"

# Maximum time (seconds) to wait for PBFT phases before timeout.
PBFT_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# Blockchain Parameters
# ---------------------------------------------------------------------------

# Maximum number of transactions per block.
MAX_TRANSACTIONS_PER_BLOCK = 50

# Minimum transactions required before the leader proposes a block.
# Set to 1 for real-time responsiveness in IoT scenarios.
MIN_TRANSACTIONS_PER_BLOCK = 1

# ---------------------------------------------------------------------------
# Networking Parameters
# ---------------------------------------------------------------------------

# Socket receive buffer size in bytes.
SOCKET_BUFFER_SIZE = 65536

# Socket connection timeout in seconds.
SOCKET_TIMEOUT = 5.0

# Maximum retries when sending a P2P message.
SOCKET_SEND_RETRIES = 2

# Delay between retries in seconds.
SOCKET_RETRY_DELAY = 0.5

# Length-prefix header size (4 bytes = up to ~4 GB messages).
MSG_HEADER_SIZE = 4

# ---------------------------------------------------------------------------
# Encryption Parameters
# ---------------------------------------------------------------------------

# AES key size in bytes (32 = AES-256).
AES_KEY_SIZE = 32

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = logging.INFO
LOG_FORMAT = "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
