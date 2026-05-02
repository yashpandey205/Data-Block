# simulation.py
# ============================================================================
# Lightweight Blockchain Framework — Multi-Node Simulation Runner
# ============================================================================
# Boots N validator nodes as separate processes, then runs an automated
# end-to-end test:
#   1. Start all nodes.
#   2. Send multiple IoT transactions.
#   3. Wait for PBFT consensus.
#   4. Verify chain consistency across all nodes.
#   5. Demonstrate the full decrypt round-trip.
#   6. Run chain validation on every node.
# ============================================================================

import subprocess
import sys
import time
import json
import requests
from config import NODES

COLORS = {
    "HEADER":  "\033[95m",
    "BLUE":    "\033[94m",
    "GREEN":   "\033[92m",
    "YELLOW":  "\033[93m",
    "RED":     "\033[91m",
    "BOLD":    "\033[1m",
    "RESET":   "\033[0m",
}

def c(color: str, text: str) -> str:
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"


def banner(title: str):
    width = 60
    print(f"\n{c('BOLD', '=' * width)}")
    print(c("HEADER", f"  {title}"))
    print(f"{c('BOLD', '=' * width)}\n")


# ---------------------------------------------------------------------------
# 0. Pre-cleanup: kill stale node processes from previous runs
# ---------------------------------------------------------------------------

def cleanup_ports():
    """Kills any processes still listening on our API/P2P ports."""
    import subprocess as _sp
    ports_to_check = []
    for cfg in NODES.values():
        ports_to_check.extend([str(cfg["api_port"]), str(cfg["socket_port"])])

    try:
        lines = _sp.check_output("netstat -ano", shell=True).decode(errors="ignore").splitlines()
        pids = set()
        for line in lines:
            if "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    addr = parts[1]
                    port = addr.split(":")[-1]
                    if port in ports_to_check:
                        pids.add(parts[-1])
        for pid in pids:
            if pid != "0":
                _sp.run(["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5)
        if pids:
            print(f"  Cleaned up {len(pids)} stale process(es) on simulation ports.")
            time.sleep(1)
    except Exception:
        pass  # best-effort


# ---------------------------------------------------------------------------
# 1. Start all nodes
# ---------------------------------------------------------------------------

def start_nodes() -> list:
    banner("PHASE 1 — Starting Validator Nodes")
    processes = []
    for node_id in NODES:
        cmd = [sys.executable, "app.py", "--node_id", node_id]
        p = subprocess.Popen(cmd)
        processes.append((node_id, p))
        port_info = (
            f"API={NODES[node_id]['api_port']}, "
            f"P2P={NODES[node_id]['socket_port']}"
        )
        print(f"  ► Started {c('BLUE', node_id)}  ({port_info})")
        time.sleep(1.2)
    return processes


# ---------------------------------------------------------------------------
# 2. Send IoT transactions
# ---------------------------------------------------------------------------

IOT_PAYLOADS = [
    {"sender": "IoT_TempSensor_01",  "receiver": "DataCenter_A",
     "data": "Temperature: 24.5°C, Humidity: 62%"},
    {"sender": "IoT_MotionSensor_02","receiver": "DataCenter_A",
     "data": "Motion detected in Zone B at 14:32:07"},
    {"sender": "IoT_PressureSensor_03","receiver": "DataCenter_B",
     "data": "Pressure: 1013.25 hPa, Altitude: 120m"},
]


def send_transactions() -> list:
    banner("PHASE 2 — Submitting IoT Transactions")
    results = []
    for i, payload in enumerate(IOT_PAYLOADS, 1):
        try:
            resp = requests.post(
                "http://127.0.0.1:5001/transactions/new",
                json=payload,
                timeout=5,
            )
            data = resp.json()
            tx_id = data.get("tx_id", "?")
            print(f"  TX {i}: {c('GREEN', 'OK')}  id={tx_id[:16]}…  "
                  f"from={payload['sender']}")
            results.append(data)
        except Exception as exc:
            print(f"  TX {i}: {c('RED', 'FAIL')}  {exc}")
        time.sleep(0.5)
    return results


# ---------------------------------------------------------------------------
# 3. Verify chain consistency
# ---------------------------------------------------------------------------

def verify_chains():
    banner("PHASE 3 — Verifying Chain Consistency Across Nodes")
    hashes = {}
    for node_id, cfg in NODES.items():
        try:
            resp = requests.get(
                f"http://127.0.0.1:{cfg['api_port']}/chain", timeout=5
            )
            chain = resp.json()
            tip_hash = chain["chain"][-1]["hash"][:16]
            length = chain["length"]
            hashes[node_id] = tip_hash
            print(f"  [{c('BLUE', node_id)}] length={length}  "
                  f"tip={tip_hash}…")
        except Exception as exc:
            print(f"  [{c('RED', node_id)}] UNREACHABLE — {exc}")

    if len(set(hashes.values())) == 1:
        print(f"\n  {c('GREEN', '✔ ALL NODES AGREE')} — chains are consistent!")
    else:
        print(f"\n  {c('RED', '✘ CHAIN MISMATCH')} — nodes have diverged!")


# ---------------------------------------------------------------------------
# 4. Decrypt round-trip demo
# ---------------------------------------------------------------------------

def demo_decrypt():
    banner("PHASE 4 — Decrypt Round-Trip Demonstration")
    try:
        # Get the latest block's first transaction
        resp = requests.get("http://127.0.0.1:5001/chain", timeout=5)
        chain = resp.json()["chain"]
        # Find the first block with transactions
        for block in chain:
            if block["transactions"]:
                tx = block["transactions"][0]
                break
        else:
            print("  No transactions found to decrypt.")
            return

        print(f"  Encrypted data : {tx['encrypted_data'][:50]}…")
        print(f"  Encrypted key  : {tx['encrypted_aes_key'][:50]}…")

        dec_resp = requests.post(
            "http://127.0.0.1:5001/decrypt",
            json={
                "encrypted_data": tx["encrypted_data"],
                "encrypted_aes_key": tx["encrypted_aes_key"],
            },
            timeout=5,
        )
        result = dec_resp.json()
        if "plaintext" in result:
            print(f"  {c('GREEN', 'Decrypted')}     : {result['plaintext']}")
        else:
            print(f"  {c('RED', 'Decrypt error')} : {result.get('error', 'Unknown')}")
    except Exception as exc:
        print(f"  {c('RED', 'Decryption demo failed')}: {exc}")


# ---------------------------------------------------------------------------
# 5. Chain validation
# ---------------------------------------------------------------------------

def validate_all():
    banner("PHASE 5 — Chain Integrity Validation")
    for node_id, cfg in NODES.items():
        try:
            resp = requests.get(
                f"http://127.0.0.1:{cfg['api_port']}/validate", timeout=5
            )
            data = resp.json()
            valid = data["is_valid"]
            icon = c("GREEN", "✔ VALID") if valid else c("RED", "✘ INVALID")
            print(f"  [{c('BLUE', node_id)}] {icon}  (length={data['chain_length']})")
        except Exception as exc:
            print(f"  [{c('RED', node_id)}] UNREACHABLE — {exc}")


# ---------------------------------------------------------------------------
# 6. Node status
# ---------------------------------------------------------------------------

def show_status():
    banner("PHASE 6 — Node Status Summary")
    for node_id, cfg in NODES.items():
        try:
            resp = requests.get(
                f"http://127.0.0.1:{cfg['api_port']}/status", timeout=5
            )
            data = resp.json()
            print(f"  [{c('BLUE', node_id)}]  chain={data['chain_length']}  "
                  f"pending={data['pending_transactions']}  "
                  f"valid={data['chain_valid']}  "
                  f"pubkey={data['public_key'][:16]}…")
        except Exception as exc:
            print(f"  [{c('RED', node_id)}] UNREACHABLE — {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cleanup_ports()
    processes = start_nodes()

    try:
        print(f"\n  Waiting 3 seconds for all nodes to stabilize…")
        time.sleep(3)

        send_transactions()

        print(f"\n  Waiting 6 seconds for PBFT consensus to finalize…")
        time.sleep(6)

        verify_chains()
        demo_decrypt()
        validate_all()
        show_status()

        banner("SIMULATION COMPLETE")
        print("  Press Ctrl+C to terminate all nodes.\n")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{c('YELLOW', 'Shutting down…')}")
        for node_id, p in processes:
            p.terminate()
            print(f"  Terminated {node_id}")
        print(c("GREEN", "All nodes terminated."))
