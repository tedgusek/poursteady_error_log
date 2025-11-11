#!/usr/bin/env python3
"""
collect_logs.py — Run a *local* parser script on remote machines over SSH and print results per machine.

Key features
- Reads hosts from hosts.txt (CSV: name,ip[,username][,port])
- Loads credentials/defaults from .env (SSH_USERNAME, SSH_PASSWORD, SSH_KEY, SSH_PORT, CONCURRENCY, TIMEOUT_SECS)
- Streams a local bash/awk parser to the remote via stdin (no files left on remote)
- Parameterizes the time cutoff ("since")
- Parallel execution; prints per-host results; optional JSON save
- Secure error handling (no credential echoing)

Examples
# Basic run using .env for username/key and a cutoff of Nov 5, 2025 20:00 local time
python3 collect_logs.py --targets hosts.txt --since 2025-11-05T20:00

# Use an external parser file (bash script); otherwise built-in default is used
python3 collect_logs.py --targets hosts.txt --since 2025-11-05T20:00 --parser-file ./collect_errors.sh

# Schedule for later (local time)
python3 collect_logs.py --targets hosts.txt --since 2025-11-05T20:00 --at 2025-11-12T03:00

# Save aggregate JSON too
python3 collect_logs.py --targets hosts.txt --since 2025-11-05T20:00 --save-json ./results/aggregate.json

hosts.txt format (CSV):
PS1428, 192.168.1.148
PS1429, 192.168.1.149, ubuntu
PS1430, 192.168.1.150, ubuntu, 2222

.env example (same folder):
SSH_USERNAME=ubuntu
SSH_PASSWORD=           # optional if key is used
SSH_KEY=C:/Users/PS Manufacturing/.ssh/id_ed25519
SSH_PORT=22
CONCURRENCY=8
TIMEOUT_SECS=180

"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import sys
from typing import List, Dict, Optional

import paramiko
from dotenv import load_dotenv

# -------------------------
# Defaults and parser script
# -------------------------
BUILTIN_PARSER = r"""#!/usr/bin/env bash
# Reads logs, filters by a numeric cutoff YYYYMMDDHHMM passed as $1
SINCE="$1"
if [[ -z "$SINCE" ]]; then
  echo "Missing SINCE argument (YYYYMMDDHHMM)" >&2
  exit 2
fi
# Concatenate current and gz-rotated logs, ignoring missing .gz files
{ zcat /data/poursteady/log/*-console.txt-*.gz 2>/dev/null ; cat /data/poursteady/log/*-console.txt 2>/dev/null; } \
| awk -v since="$SINCE" 'BEGIN{IGNORECASE=1}
{
  # Expect first token to be ISO-like: 2025-11-05T20:13:00-05:00
  split($1, dt, /[T:-]/)
  if (length(dt[1])==0 || length(dt[2])==0 || length(dt[3])==0) next
  datenum = dt[1] dt[2] dt[3]
  timenum = dt[4] * 100 + dt[5]
  datetime = datenum * 10000 + timenum
  if (datetime >= since) {
    line = $0
    if (/EMCY/) {
      match(line, /(0000|1000|2310|2340|3210|3220|4280|4310|5441|5442|5443|6100|7500|8110|8130|8331|8580|8611|9000|FF01|FF02|FF03|FF04|FF05)/)
      if (RSTART > 0) {
        code = substr(line, RSTART, RLENGTH)
        timestamp = $1
        emcy_count[code]++
        emcy_last_time[code] = timestamp
      }
    }
    if (/failure/) {
      failure_count++
      failure_last_timestamp = $1
    }
  }
}
END {
  for (code in emcy_count) {
    print emcy_count[code], code, emcy_last_time[code]
  }
  print (failure_count ? failure_count : 0) " SAOBO Errors " failure_last_timestamp
}' | sort -rn
"""

# -------------------------
# Helpers
# -------------------------

def read_hosts(path: str) -> List[Dict]:
    hosts: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):  # skip comments/blank
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                raise ValueError(f"Each line must be at least name,ip — bad line: {line}")
            entry = {"name": parts[0], "ip": parts[1]}
            if len(parts) >= 3 and parts[2]:
                entry["username"] = parts[2]
            if len(parts) >= 4 and parts[3]:
                entry["port"] = int(parts[3])
            hosts.append(entry)
    return hosts


def iso_to_cutoff_yyyymmddhhmm(iso_str: str) -> str:
    # Accept local time ISO like 2025-11-05T20:00 or with seconds
    try:
        t = dt.datetime.fromisoformat(iso_str)
    except Exception as e:
        raise ValueError("--since must be ISO like 2025-11-05T20:00") from e
    return f"{t.year:04d}{t.month:02d}{t.day:02d}{t.hour:02d}{t.minute:02d}"


def _connect(ip: str, username: str, port: int, keyfile: Optional[str], password: Optional[str]) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=ip, port=port, username=username,
                   key_filename=keyfile if keyfile else None,
                   password=password if password else None,
                   timeout=15)
    return client


def run_parser_on_host(host: Dict, parser_text: str, since_cutoff: str, timeout_secs: int,
                       defaults: Dict) -> Dict:
    name = host.get("name")
    ip = host.get("ip")
    username = host.get("username") or defaults.get("username")
    port = int(host.get("port") or defaults.get("port", 22))

    result = {
        "name": name,
        "ip": ip,
        "username": username,
        "port": port,
        "ok": False,
        "output": "",
        "error": None,
        "exit_status": None,
    }

    if not username:
        result["error"] = "No username (set in hosts.txt or SSH_USERNAME in .env)"
        return result

    try:
        client = _connect(ip, username, port, defaults.get("key"), defaults.get("password"))
        try:
            # If sudo requested, wrap bash with sudo -n
            bash_cmd = "sudo -n bash -s" if defaults.get("sudo") else "bash -s"
            # Start remote bash; stream parser via stdin; pass cutoff as arg $1
            stdin, stdout, stderr = client.exec_command(f"{bash_cmd} -- {since_cutoff}", timeout=timeout_secs)
            stdin.write(parser_text)
            stdin.channel.shutdown_write()

            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")

            result.update({
                "ok": exit_status == 0,
                "output": out.strip(),
                "error": err.strip() if exit_status != 0 else None,
                "exit_status": exit_status,
            })
        finally:
            client.close()
    except paramiko.ssh_exception.AuthenticationException:
        result["error"] = "Authentication failed (check key/password and username)."
    except paramiko.ssh_exception.SSHException as e:
        result["error"] = f"SSH error: {str(e)}"
    except Exception as e:
        result["error"] = f"Connection/run error: {e.__class__.__name__}: {str(e)}"

    return result


# -------------------------
# Main
# -------------------------

def main():
    load_dotenv()  # from .env in CWD

    ap = argparse.ArgumentParser(description="Run a local parser script on remote machines via SSH")
    ap.add_argument("--targets", required=True, help="Path to hosts.txt (CSV: name,ip[,username][,port])")
    ap.add_argument("--since", required=True, help="ISO local datetime cutoff, e.g. 2025-11-05T20:00")
    ap.add_argument("--parser-file", help="Path to a local bash parser file; if omitted, built-in parser is used")
    ap.add_argument("--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "8")))
    ap.add_argument("--timeout", type=int, default=int(os.getenv("TIMEOUT_SECS", "180")))
    ap.add_argument("--at", help="Optional ISO local datetime to start (e.g. 2025-11-12T03:00)")
    ap.add_argument("--save-json", help="Optional path to write aggregate JSON results")
    ap.add_argument("--sudo", action="store_true", help="Run parser under sudo -n bash -s on remote")
    args = ap.parse_args()

    # Defaults from .env
    defaults = {
        "username": os.getenv("SSH_USERNAME"),
        "password": os.getenv("SSH_PASSWORD"),
        "key": os.getenv("SSH_KEY"),
        "port": int(os.getenv("SSH_PORT", "22")),
        "sudo": bool(args.sudo),
    }

    # Resolve since cutoff
    cutoff = iso_to_cutoff_yyyymmddhhmm(args.since)

    # Load parser text
    if args.parser_file:
        with open(args.parser_file, "r", encoding="utf-8") as f:
            parser_text = f.read()
    else:
        parser_text = BUILTIN_PARSER

    # Load hosts
    hosts = read_hosts(args.targets)

    # Optional schedule wait
    if args.at:
        try:
            when = dt.datetime.fromisoformat(args.at)
        except Exception:
            print("Bad --at; use ISO like 2025-11-12T03:00", file=sys.stderr)
            sys.exit(2)
        now = dt.datetime.now()
        delta = (when - now).total_seconds()
        if delta > 0:
            print(f"Waiting {delta:.0f}s until {when.isoformat()}...")
            import time
            time.sleep(delta)
        else:
            print("--at is in the past; running now.")

    # Run in parallel
    results: List[Dict] = []
    print(f"Running parser on {len(hosts)} hosts with concurrency={args.concurrency} ...\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [
            ex.submit(run_parser_on_host, h, parser_text, cutoff, args.timeout, defaults)
            for h in hosts
        ]
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            tag = f"{r.get('name')} ({r.get('ip')})"
            if r.get("ok"):
                print(f"===== {tag} — OK (exit {r.get('exit_status')}) =====")
                print(r.get("output") or "<no matches>")
            else:
                print(f"===== {tag} — FAIL =====")
                print(r.get("error") or "Unknown error")
            print()

    if args.save_json:
        os.makedirs(os.path.dirname(args.save_json) or ".", exist_ok=True)
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Aggregate JSON saved to {args.save_json}")

    # Summary
    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"Summary: {ok} succeeded, {fail} failed.")


if __name__ == "__main__":
    main()
