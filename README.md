# Lightweight Blockchain Framework for Secure IoT Communication

A production-grade lightweight blockchain prototype designed for resource-constrained IoT environments. Uses **PBFT consensus** for fast finality and **hybrid AES-256 + ECC (secp256k1)** encryption for secure data transmission.

---

## Architecture

```
┌──────────────┐     HTTP/REST      ┌─────────────────────────────┐
│  IoT Device  │ ─────────────────► │  Flask API  (app.py)        │
│  (Client)    │  POST /txn/new     │  ┌───────────────────────┐  │
└──────────────┘                    │  │  Encryption Module     │  │
                                    │  │  (AES-256 + ECC)       │  │
                                    │  └───────────────────────┘  │
                                    │  ┌───────────────────────┐  │
                                    │  │  Node (node.py)        │  │
                                    │  │  ┌─────────────────┐  │  │
                                    │  │  │ Blockchain      │  │  │
                                    │  │  │ (Merkle + SHA)  │  │  │
                                    │  │  ├─────────────────┤  │  │
                                    │  │  │ PBFT Engine     │  │  │
                                    │  │  │ (3-Phase)       │  │  │
                                    │  │  └─────────────────┘  │  │
                                    │  └──────────┬────────────┘  │
                                    └─────────────┼───────────────┘
                                                  │  TCP Sockets
                                    ┌─────────────┼───────────────┐
                                    │  P2P Network │               │
                                    │  ┌──────┐ ┌──────┐ ┌──────┐ │
                                    │  │Node 2│ │Node 3│ │Node 4│ │
                                    │  └──────┘ └──────┘ └──────┘ │
                                    └─────────────────────────────┘
```

---

## Features

| Feature | Description |
|---|---|
| **PBFT Consensus** | 3-phase (Pre-Prepare → Prepare → Commit), tolerates f = ⌊(n-1)/3⌋ faults |
| **AES-256-CBC** | Fast symmetric encryption for IoT payloads |
| **ECC (secp256k1)** | Asymmetric key exchange for AES session keys (ECIES) |
| **ECDSA Signatures** | Digital signing for message authentication |
| **Merkle Trees** | Block-level transaction integrity proofs |
| **Thread Safety** | All shared state protected by locks |
| **Length-Prefixed TCP** | Reliable message framing on the socket layer |
| **Message Buffering** | Out-of-order PBFT messages are queued and replayed |

---

## Project Structure

```
project/
├── app.py              Flask REST API (8 endpoints)
├── blockchain.py        Block, Transaction, Blockchain classes
├── config.py            Network topology & system parameters
├── encryption.py        AES + ECC + ECDSA cryptography
├── node.py              P2P validator node with socket networking
├── pbft.py              PBFT consensus state machine
├── utils.py             Hashing, Merkle trees, TCP framing, logging
├── simulation.py        Automated multi-node simulation runner
├── test_client.py       IoT client simulator
├── requirements.txt     Python dependencies
└── README.md            This file
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Full Simulation

```bash
python simulation.py
```

This starts 4 nodes, sends 3 IoT transactions, verifies consensus, demonstrates decryption, and validates all chains.

### 3. Run Nodes Manually

Open 4 separate terminals:

```bash
python app.py --node_id node_1
python app.py --node_id node_2
python app.py --node_id node_3
python app.py --node_id node_4
```

### 4. Send Data via cURL

```bash
curl -X POST http://127.0.0.1:5001/transactions/new \
  -H "Content-Type: application/json" \
  -d '{"sender":"Sensor_01","receiver":"DataCenter","data":"Temp: 25C"}'
```

### 5. Check Chain

```bash
curl http://127.0.0.1:5001/chain
curl http://127.0.0.1:5001/status
curl http://127.0.0.1:5001/validate
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/transactions/new` | Submit IoT data (auto-encrypted) |
| `POST` | `/decrypt` | Decrypt a transaction payload |
| `GET` | `/chain` | Full blockchain ledger |
| `GET` | `/pending` | Pending transaction pool |
| `GET` | `/status` | Node health + PBFT state |
| `GET` | `/pubkey` | Node's ECC public key |
| `GET` | `/nodes` | Registered network peers |
| `GET` | `/validate` | Chain integrity validation |

---

## Security Pipeline

```
IoT Device                          Validator Node
──────────                          ──────────────
   │  1. Generate data                    │
   │  2. Generate AES-256 key             │
   │  3. Encrypt data with AES            │
   │  4. Encrypt AES key with ECC pub     │
   │  5. Send encrypted payload ────────► │
   │                                      │  6. ECC decrypt → AES key
   │                                      │  7. AES decrypt → plaintext
```

---

## PBFT Consensus Flow

```
Leader           Node 2          Node 3          Node 4
──────           ──────          ──────          ──────
  │ PRE-PREPARE ──►│               │               │
  │ PRE-PREPARE ──────────────────►│               │
  │ PRE-PREPARE ──────────────────────────────────►│
  │               │ PREPARE ──────►│               │
  │◄── PREPARE ───│               │               │
  │               │ PREPARE ──────────────────────►│
  │◄── PREPARE ──────────────────│                │
  │               │               │ PREPARE ──────►│
  │               │               │◄── PREPARE ───│
  │               │ COMMIT ───────►│               │
  │◄── COMMIT ────│               │               │
  │               │ COMMIT ───────────────────────►│
  │               │               │ COMMIT ───────►│
  │               │               │               │
  ▼               ▼               ▼               ▼
BLOCK COMMITTED ON ALL HONEST NODES
```

**Condition:** Block accepted when `commits ≥ 2f + 1` (with n=4, f=1, need ≥ 3 commits).

---

## Dependencies

- `Flask` — REST API server
- `pycryptodome` — AES-256-CBC encryption
- `eciespy` — ECC key exchange (ECIES on secp256k1)
- `coincurve` — ECDSA signing / verification
- `requests` — HTTP client for simulation
