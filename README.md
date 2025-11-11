# Poursteady Error Log Retrieval System

A clean overview of how to fetch, parse, and aggregate error logs from multiple Poursteady machines over SSH using a local script streamed to the remote host.

---

## ⭐ Overview

This tool:

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
├── collect_logs.py              # Main controller script (Python)
├── collect_errors.sh (optional) # Local parser script (can be built-in)
├── hosts.txt                    # Machine list (NOT committed to git)
├── .env                         # SSH credentials & defaults (NOT committed)
├── results/                     # Optional output directory
└── README.md                    # Documentation
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
SSH_USERNAME=ubuntu
SSH_PASSWORD=
SSH_KEY=C:/Users/YourUser/.ssh/id_ed25519
SSH_PORT=22
CONCURRENCY=8
TIMEOUT_SECS=180
```

> Do **not** commit `.env` or `hosts.txt` to GitHub.

---

## 🏷️ hosts.txt Format

*The first line sets the SINCE variable, you can update accordingly.
*There are instructions in the file, but here's a quick overview:
*One of these lines should always be commented out depending on what you are trying to do:
*If you want to set a start day/time uncomment the first option, and enter the start time
*Alternatively, if you want to start from the beginning of time, uncomment the second line

```
#SINCE=2025-11-05T20:00
SINCE=000000000000 
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

```bash
py collect_logs.py --targets hosts.txt
```

### Use an external parser file

```bash
py collect_logs.py --targets hosts.txt --parser-file ./collect_errors.sh
```

### Run with sudo

```bash
py collect_logs.py --targets hosts.txt --sudo
```

### Save results to JSON

```bash
py collect_logs.py --targets hosts.txt --save-json ./results/aggregate.json
```

### Schedule for later

```bash
py collect_logs.py --targets hosts.txt --at 2025-11-12T03:00
```

---

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
