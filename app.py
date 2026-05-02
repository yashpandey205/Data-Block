# app.py
# ============================================================================
# Lightweight Blockchain Framework — Flask REST API
# ============================================================================
# Exposes HTTP endpoints for IoT clients and monitoring dashboards to
# interact with the blockchain network.  Each running instance wraps a
# single Node object.
#
# Endpoints:
#   POST /transactions/new  — Submit IoT sensor data (auto-encrypted).
#   POST /decrypt            — Decrypt a transaction payload (demo / debug).
#   GET  /chain              — Full blockchain ledger.
#   GET  /pending            — Pending transaction pool.
#   GET  /status             — Node health + PBFT consensus state.
#   GET  /pubkey             — This node's ECC public key.
#   GET  /nodes              — Registered network peers.
#   GET  /validate           — Run full chain integrity validation.
# ============================================================================

from flask import Flask, jsonify, request, render_template
import argparse
import sys
import logging

from node import Node
from encryption import process_iot_data_encryption, process_iot_data_decryption
from blockchain import Transaction
from config import NODES

# Suppress noisy Flask/Werkzeug request logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)
node: Node | None = None


@app.errorhandler(Exception)
def handle_exception(e):
    """Global handler: always return JSON, never HTML error pages."""
    return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "GET  /",
            "POST /transactions/new",
            "POST /decrypt",
            "GET  /chain",
            "GET  /pending",
            "GET  /status",
            "GET  /pubkey",
            "GET  /nodes",
            "GET  /validate",
        ],
    }), 404


# ---------------------------------------------------------------------------
# GET / (Web Dashboard)
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Serves the web-based blockchain dashboard."""
    return render_template("dashboard.html")


@app.route("/api", methods=["GET"])
def api_index():
    """JSON API index — lists all available endpoints."""
    return jsonify({
        "project": "Lightweight Blockchain for Secure IoT Communication",
        "node_id": node.node_id,
        "endpoints": {
            "GET  /": "Web Dashboard",
            "POST /transactions/new": "Submit IoT sensor data (auto-encrypted)",
            "POST /decrypt": "Decrypt a transaction payload",
            "GET  /chain": "Full blockchain ledger",
            "GET  /pending": "Pending transaction pool",
            "GET  /status": "Node health + PBFT consensus state",
            "GET  /pubkey": "This node's ECC public key",
            "GET  /nodes": "Registered network peers",
            "GET  /validate": "Run chain integrity validation",
        },
    }), 200


# ---------------------------------------------------------------------------
# POST /transactions/new
# ---------------------------------------------------------------------------

@app.route("/transactions/new", methods=["POST"])
def new_transaction():
    """
    Accepts raw IoT sensor data, encrypts it with the hybrid AES+ECC
    pipeline, and broadcasts the resulting transaction to all peers.
    """
    values = request.get_json(silent=True)
    if not values:
        return jsonify({"error": "Request body must be JSON"}), 400

    required = ["sender", "receiver", "data"]
    missing = [k for k in required if k not in values]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # Encrypt the payload using this node's ECC public key.
    # In production, the client would use the *receiver's* public key.
    pub_key = node.ecc_manager.get_public_key()
    enc = process_iot_data_encryption(values["data"], pub_key)

    tx = Transaction(
        sender=values["sender"],
        receiver=values["receiver"],
        encrypted_data=enc["encrypted_data"],
        encrypted_aes_key=enc["encrypted_aes_key"],
    )

    node.submit_transaction(tx)

    return jsonify({
        "message": "Transaction encrypted and broadcasted",
        "tx_id": tx.tx_id,
        "encrypted_data_preview": enc["encrypted_data"][:40] + "…",
    }), 201


# ---------------------------------------------------------------------------
# POST /decrypt
# ---------------------------------------------------------------------------

@app.route("/decrypt", methods=["POST"])
def decrypt_transaction():
    """
    Decrypts a previously-encrypted transaction payload.

    Expects JSON body with ``encrypted_data`` and ``encrypted_aes_key``.
    Useful for demonstrating the full encrypt → decrypt round-trip.
    """
    values = request.get_json(silent=True)
    if not values:
        return jsonify({"error": "Request body must be JSON"}), 400

    required = ["encrypted_data", "encrypted_aes_key"]
    missing = [k for k in required if k not in values]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        plaintext = process_iot_data_decryption(
            values["encrypted_data"],
            values["encrypted_aes_key"],
            node.ecc_manager,
        )
        return jsonify({"plaintext": plaintext}), 200
    except Exception as exc:
        return jsonify({"error": f"Decryption failed: {exc}"}), 400


# ---------------------------------------------------------------------------
# GET /chain
# ---------------------------------------------------------------------------

@app.route("/chain", methods=["GET"])
def get_chain():
    """Returns the full blockchain ledger."""
    with node.blockchain._lock:
        chain_data = [block.to_dict() for block in node.blockchain.chain]
    return jsonify({
        "node_id": node.node_id,
        "chain": chain_data,
        "length": len(chain_data),
    }), 200


# ---------------------------------------------------------------------------
# GET /pending
# ---------------------------------------------------------------------------

@app.route("/pending", methods=["GET"])
def get_pending():
    """Returns the current pending (un-committed) transaction pool."""
    with node.blockchain._lock:
        pending = [tx.to_dict() for tx in node.blockchain.pending_transactions]
    return jsonify({
        "node_id": node.node_id,
        "pending_transactions": pending,
        "count": len(pending),
    }), 200


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@app.route("/status", methods=["GET"])
def get_status():
    """Returns node health, chain stats, and PBFT consensus state."""
    return jsonify({
        "node_id": node.node_id,
        "public_key": node.ecc_manager.get_public_key(),
        "chain_length": node.blockchain.get_chain_length(),
        "pending_transactions": len(node.blockchain.pending_transactions),
        "chain_valid": node.blockchain.validate_chain(),
        "pbft": node.pbft.get_status(),
    }), 200


# ---------------------------------------------------------------------------
# GET /pubkey
# ---------------------------------------------------------------------------

@app.route("/pubkey", methods=["GET"])
def get_pubkey():
    """Returns this node's ECC public key (for external clients to encrypt to)."""
    return jsonify({
        "node_id": node.node_id,
        "public_key": node.ecc_manager.get_public_key(),
    }), 200


# ---------------------------------------------------------------------------
# GET /nodes
# ---------------------------------------------------------------------------

@app.route("/nodes", methods=["GET"])
def get_nodes():
    """Returns the list of all registered network peers."""
    return jsonify({
        "nodes": NODES,
        "total": len(NODES),
    }), 200


# ---------------------------------------------------------------------------
# GET /validate
# ---------------------------------------------------------------------------

@app.route("/validate", methods=["GET"])
def validate_chain():
    """Runs full chain integrity validation and returns the result."""
    is_valid = node.blockchain.validate_chain()
    return jsonify({
        "node_id": node.node_id,
        "chain_length": node.blockchain.get_chain_length(),
        "is_valid": is_valid,
    }), 200


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Start a blockchain validator node."
    )
    parser.add_argument(
        "--node_id", type=str, required=True,
        help=f"Node identifier. Choose from: {list(NODES.keys())}",
    )
    args = parser.parse_args()

    if args.node_id not in NODES:
        print(f"Error: Invalid node_id '{args.node_id}'. "
              f"Valid options: {list(NODES.keys())}")
        sys.exit(1)

    node = Node(args.node_id)

    api_port = NODES[args.node_id]["api_port"]
    print(f"[{args.node_id}] Flask API running on http://127.0.0.1:{api_port}")
    app.run(host="127.0.0.1", port=api_port, threaded=True)
