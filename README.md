# Poursteady Error Log Retrieval System

A clean overview of how to fetch, parse, and aggregate error logs from multiple Poursteady machines over SSH using a local script streamed to the remote host.

---

## ⭐ Overview

This tool:

* Scans Network for PS machines
* Connects to many Poursteady machines over SSH
* Streams a local Bash/AWK parser into the remote shell (no files written remotely)
* Processes logs since a specified timestamp
* Prints friendly machine-named results
* Optionally saves aggregate JSON output
* Supports scheduling, sudo mode, and `.env`-based configuration

---

## 📁 Project Structure

```
ErrorLogRetrieval/
├── overnight_testing.py             # Main Controller Script (Python)
├── scan_network_for_ps_machines.py  # Scans Network for PS Machines (Python)
├── remote_error_log_parser.py       # Parses through the logs on the Machines and returns an Error Count (Python)
├── hosts.txt                        # Machine list (NOT committed to git and re-written every run)
├── .env                             # SSH credentials & defaults (NOT committed)
├── results/                         # Optional output directory
└── README.md                        # Documentation
```

---

## ✅ Requirements

Install Python dependencies:

```bash
py -m pip install paramiko python-dotenv
```

---

## ⚙️ Configuration

### `.env`

Create a `.env` file to store SSH defaults:

```dotenv
# SSH auth (prefer keys in production)
SSH_USERNAME= enter your user name here
SSH_PASSWORD= enter your password here

# Optional defaults (CLI flags still override these)
SSH_PORT= enter your port here
TARGETS_FILE=hosts.txt
CONCURRENCY=12
TIMEOUT=120
RETRIES=2
# ISO local time; leave blank to run immediately (example below)
# AT=2025-11-20T03:00

# Orbi auth (prefer keys in production)
ORBI_IP= enter your IP here
ORBI_USER= enter your user name here
ORBI_PASS= enter your password here
```

> Do **not** commit `.env` or `hosts.txt` to GitHub.

---

## 🏷️ hosts.txt Format

The first line sets the SINCE variable, you can update accordingly.
And the following lines will have the PS Device name and IP address
ie:
PS####,###.###.#.###

```
SINCE=2025-11-05T20:00
 
```
Each line must be:

```
name, ip[, username][, port]
```

Examples:

```
PS1428, 192.168.1.148
PS1550, 192.168.1.200, ubuntu
LA_Cafe_01, 10.0.3.44, ubuntu, 2222
```

* Names appear in the console output
* Username/port override `.env` defaults

---

## 🚀 Running the Tool

### Basic
Go to the directory this is saved and run
```bash
py overnight_testing.py
```
You will be prompted to enter how long you want the test to run and from what date/time you want the error parser to start

### Run with sudo

```bash
py collect_logs.py --targets hosts.txt --sudo
```

## 📤 Example Output

```
===== PS1428 (192.168.1.148) — OK (exit 0) =====
12 3220 2025-11-05T20:03:00
3  7500 2025-11-05T20:10:10
0  SAOBO Errors -
```

Failed example:

```
===== PS1550 (192.168.1.200) — FAIL =====
Authentication failed (check key/password and username).
```

---

## 🧩 JSON Output Schema

Each host result looks like:

```json
{
  "name": "PS1428",
  "ip": "192.168.1.148",
  "username": "ubuntu",
  "port": 22,
  "ok": true,
  "output": "full parser output here",
  "error": null,
  "exit_status": 0
}
```

---

## 🛠️ Troubleshooting

**python not recognized**

```bash
winget install Python.Python.3
```

**Permission denied (publickey)**

* Ensure your SSH key is added to the SSH agent
* Ensure the `.pub` file is in the remote's `authorized_keys`

**Log folder missing**
Different machines may store logs differently:

```bash
ls /data/poursteady/log
```

Update parser path as needed.

---

## 🔒 Security Notes

* No scripts or files are written to the remote machines
* Secrets stay in `.env` and are gitignored
* Output sanitization protects credentials

---

## 📄 License

Internal use only.

```
```
