#!/usr/bin/env python3
"""
collect_logs.py

Usage examples:
# Run now, using private key:
python3 collect_logs.py --targets hosts.txt --username ubuntu --key ~/.ssh/id_rsa \
    --remote-cmd "sudo /usr/local/bin/collect_logs.sh /tmp/collected.log" \
    --download-remote-file /tmp/collected.log --outdir ./results

# Run at designated time (ISO format):
python3 collect_logs.py --targets hosts.csv --username admin --key ~/.ssh/id_rsa \
    --remote-cmd "journalctl -u myservice --no-pager > /tmp/myservice.log" \
    --download-remote-file /tmp/myservice.log --at 2025-11-20T03:00

Targets file format (plain text): one IP per line
Or CSV: ip,username,port (port optional) - script handles simple formats
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import time
from typing import List, Dict, Optional

import paramiko

# -------------------------
# Utility functions
# -------------------------
def parse_targets_file(path: str) -> List[Dict]:
    """
    Accepts:
      - plain file with one IP per line
      - csv with ip,username,port columns (comma separated)
    Returns list of dicts: {ip, username (optional), port (optional)}
    """
    targets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 1:
                targets.append({"ip": parts[0]})
            elif len(parts) == 2:
                targets.append({"ip": parts[0], "username": parts[1]})
            else:
                # ip, username, port
                targets.append({"ip": parts[0], "username": parts[1], "port": int(parts[2])})
    return targets


def ssh_run_command(ip: str,
                    username: str,
                    port: int,
                    key_filename: Optional[str],
                    password: Optional[str],
                    remote_cmd: str,
                    timeout: int,
                    download_remote_file: Optional[str],
                    local_outdir: str,
                    max_retries: int = 1) -> Dict:
    """
    Connect to ip over SSH, run remote_cmd, capture stdout/stderr/exit_code.
    Optionally download a remote file via SFTP (download_remote_file -> saved with ip prefix).
    Returns dict with results.
    """
    attempt = 0
    last_err = None
    while attempt < max_retries:
        attempt += 1
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = dict(hostname=ip, port=port, username=username, timeout=10)
            if key_filename:
                connect_kwargs["key_filename"] = key_filename
            if password:
                connect_kwargs["password"] = password

            client.connect(**connect_kwargs)

            # run command
            stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=timeout)
            exit_status = stdout.channel.recv_exit_status()  # wait for completion

            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")

            result = {
                "ip": ip,
                "username": username,
                "port": port,
                "exit_status": exit_status,
                "stdout": out,
                "stderr": err,
                "attempt": attempt,
                "error": None,
            }

            # Save stdout/stderr locally
            safe_ip = ip.replace(":", "_")
            os.makedirs(local_outdir, exist_ok=True)
            with open(os.path.join(local_outdir, f"{safe_ip}_stdout.txt"), "w", encoding="utf-8") as fo:
                fo.write(out)
            with open(os.path.join(local_outdir, f"{safe_ip}_stderr.txt"), "w", encoding="utf-8") as fe:
                fe.write(err)

            # Optionally download file
            if download_remote_file:
                try:
                    sftp = client.open_sftp()
                    remote = download_remote_file
                    basename = os.path.basename(remote)
                    local_path = os.path.join(local_outdir, f"{safe_ip}_{basename}")
                    sftp.get(remote, local_path)
                    sftp.close()
                    result["downloaded_file"] = local_path
                except Exception as e:
                    # don't fail entire job if download failed
                    result["download_error"] = str(e)

            client.close()
            return result

        except Exception as e:
            last_err = e
            # keep trying until max_retries
            time.sleep(1)
            try:
                client.close()
            except:
                pass

    # If we got here, failed all attempts
    return {
        "ip": ip,
        "username": username,
        "port": port,
        "exit_status": None,
        "stdout": None,
        "stderr": None,
        "attempt": attempt,
        "error": str(last_err),
    }

# -------------------------
# CLI / Orchestration
# -------------------------
def main():
    p = argparse.ArgumentParser(description="Run a remote log-collection command across multiple machines via SSH.")
    p.add_argument("--targets", required=True, help="Path to targets file (one IP per line, or csv ip,username,port)")
    p.add_argument("--username", help="Default username if not present in targets file")
    p.add_argument("--key", help="Private key file path (use with key auth).")
    p.add_argument("--password", help="Password for SSH (not recommended).")
    p.add_argument("--port", type=int, default=22, help="Default SSH port")
    p.add_argument("--remote-cmd", required=True, help="Remote command to run on each host (e.g. '/usr/local/bin/collect_logs.sh /tmp/out.log')")
    p.add_argument("--download-remote-file", help="Remote file path to download after command runs (optional)")
    p.add_argument("--outdir", default="./results", help="Local folder to write results")
    p.add_argument("--concurrency", type=int, default=16, help="How many SSH sessions in parallel")
    p.add_argument("--timeout", type=int, default=120, help="Per-command timeout (seconds)")
    p.add_argument("--retries", type=int, default=2, help="Retries per host")
    p.add_argument("--at", help="Optional scheduled time to run (ISO format YYYY-MM-DDTHH:MM[:SS], local time). If omitted runs immediately.")
    args = p.parse_args()

    # Parse targets
    targets = parse_targets_file(args.targets)
    # Apply defaults
    for t in targets:
        if 'username' not in t or not t['username']:
            if not args.username:
                print(f"No username for {t['ip']} and no default provided. Use --username or supply csv with username.", file=sys.stderr)
                sys.exit(2)
            t['username'] = args.username
        t['port'] = int(t.get('port') or args.port)

    # Schedule if needed
    if args.at:
        try:
            run_time = datetime.datetime.fromisoformat(args.at)
        except Exception:
            print("Bad --at datetime. Use ISO format like 2025-11-20T03:00", file=sys.stderr)
            sys.exit(2)
        now = datetime.datetime.now()
        delta = (run_time - now).total_seconds()
        if delta > 0:
            print(f"Waiting {delta:.1f}s until scheduled time {run_time.isoformat()}...")
            time.sleep(delta)
        else:
            print("Scheduled time is in the past, running immediately.")

    print(f"Starting jobs on {len(targets)} targets with concurrency {args.concurrency} ...")
    results = []

    # Run in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = []
        for t in targets:
            futures.append(
                ex.submit(ssh_run_command,
                          t['ip'],
                          t['username'],
                          t['port'],
                          args.key,
                          args.password,
                          args.remote_cmd,
                          args.timeout,
                          args.download_remote_file,
                          args.outdir,
                          args.retries)
            )
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            results.append(r)
            # print summary line
            if r.get("error"):
                print(f"[FAIL] {r['ip']}: {r['error']}")
            else:
                print(f"[OK] {r['ip']}: exit={r.get('exit_status')} downloaded={r.get('downloaded_file','-')}")

    # Save aggregated JSON
    os.makedirs(args.outdir, exist_ok=True)
    out_json = os.path.join(args.outdir, "aggregate_results.json")
    with open(out_json, "w", encoding="utf-8") as fj:
        json.dump(results, fj, indent=2)

    print("Done. Aggregate saved to:", out_json)
    # Optionally print summary to stdout
    ok = sum(1 for r in results if not r.get("error"))
    fail = len(results) - ok
    print(f"Summary: {ok} succeeded, {fail} failed.")

if __name__ == "__main__":
    main()
