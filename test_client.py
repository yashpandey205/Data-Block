# test_client.py
# ============================================================================
# Lightweight Blockchain Framework — IoT Client Simulator
# ============================================================================
# Standalone test script that simulates multiple IoT devices sending sensor
# data to the blockchain network.  Exercises the full pipeline:
#   encrypt → broadcast → consensus → commit → decrypt → validate
#
# Usage:
#   python test_client.py                       # defaults to node_1
#   python test_client.py --target node_2       # send to a different node
#   python test_client.py --count 10            # send 10 rapid transactions
# ============================================================================

import argparse
import time
import json
import random
import requests
from config import NODES

API_BASE = "http://127.0.0.1"


def send_iot_data(port: int, sender: str, data: str):
    """Sends a single IoT data payload to the specified node."""
    payload = {"sender": sender, "receiver": "DataCenter", "data": data}
    resp = requests.post(f"{API_BASE}:{port}/transactions/new",
                         json=payload, timeout=5)
    return resp.json()


def generate_sensor_reading() -> tuple[str, str]:
    """Generates a random IoT sensor identity and reading."""
    sensors = [
        ("TempSensor",     lambda: f"Temperature: {random.uniform(18, 40):.1f}°C"),
        ("HumiditySensor", lambda: f"Humidity: {random.uniform(30, 90):.1f}%"),
        ("PressureSensor", lambda: f"Pressure: {random.uniform(980, 1050):.2f} hPa"),
        ("MotionSensor",   lambda: f"Motion: {'detected' if random.random() > 0.5 else 'clear'}"),
        ("LightSensor",    lambda: f"Ambient light: {random.randint(0, 1000)} lux"),
    ]
    name, gen = random.choice(sensors)
    device_id = f"{name}_{random.randint(1, 99):02d}"
    return device_id, gen()


def main():
    parser = argparse.ArgumentParser(description="IoT client simulator")
    parser.add_argument("--target", default="node_1",
                        help="Target node ID (default: node_1)")
    parser.add_argument("--count", type=int, default=5,
                        help="Number of transactions to send (default: 5)")
    args = parser.parse_args()

    if args.target not in NODES:
        print(f"Invalid target. Choose from: {list(NODES.keys())}")
        return

    port = NODES[args.target]["api_port"]
    print(f"\n{'='*50}")
    print(f"  IoT Client Simulator → {args.target} (port {port})")
    print(f"  Sending {args.count} transactions")
    print(f"{'='*50}\n")

    tx_ids = []
    for i in range(1, args.count + 1):
        device, reading = generate_sensor_reading()
        try:
            result = send_iot_data(port, device, reading)
            tx_id = result.get("tx_id", "?")[:16]
            print(f"  [{i}/{args.count}] {device:25s} → {reading:40s}  tx={tx_id}…")
            tx_ids.append(result.get("tx_id"))
        except Exception as exc:
            print(f"  [{i}/{args.count}] FAILED: {exc}")
        time.sleep(0.3)

    # Wait for consensus
    print(f"\n  Waiting 6 seconds for consensus…")
    time.sleep(6)

    # Verify
    print(f"\n  Chain status across nodes:")
    for node_id, cfg in NODES.items():
        try:
            resp = requests.get(f"{API_BASE}:{cfg['api_port']}/chain", timeout=5)
            data = resp.json()
            print(f"    [{node_id}] blocks={data['length']}  "
                  f"tip={data['chain'][-1]['hash'][:16]}…")
        except Exception:
            print(f"    [{node_id}] unreachable")

    # Decrypt the first transaction
    if tx_ids:
        print(f"\n  Decrypt round-trip test:")
        try:
            resp = requests.get(f"{API_BASE}:{port}/chain", timeout=5)
            chain = resp.json()["chain"]
            for block in chain:
                if block["transactions"]:
                    tx = block["transactions"][0]
                    dec = requests.post(
                        f"{API_BASE}:{port}/decrypt",
                        json={
                            "encrypted_data": tx["encrypted_data"],
                            "encrypted_aes_key": tx["encrypted_aes_key"],
                        },
                        timeout=5,
                    )
                    print(f"    Decrypted: {dec.json().get('plaintext', '?')}")
                    break
        except Exception as exc:
            print(f"    Decrypt failed: {exc}")

    print(f"\n{'='*50}")
    print(f"  Simulation complete.")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
