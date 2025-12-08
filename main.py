# main.py
import os
import sys
import time
import subprocess
from datetime import datetime

from dotenv import load_dotenv

from overnight_testing import SSHCredentials, start_tests_bulk, stop_tests_bulk
from hosts_repo import HostsRepo
from models import is_ps1_name, is_ps2_name

SCRIPT_DIR = os.path.dirname(__file__)
HOSTS_FILE = os.path.join(SCRIPT_DIR, "hosts.txt")


def parse_since_input(user_text: str) -> str:
    """
    Accepts:
      - blank -> '0'
      - YYYYMMDDHHMM -> used as-is
      - YYYYMMDDHH -> padded to HH00
      - YYYY-MM-DD HH:MM
      - YYYY-MM-DDTHH:MM
      - YYYY/MM/DD HH:MM
    """
    t = user_text.strip()
    if not t:
        return "0"

    if t.isdigit() and len(t) == 12:
        return t

    if t.isdigit() and len(t) == 10:
        return t + "00"

    candidates = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H",
        "%Y/%m/%d %H",
    ]

    for fmt in candidates:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.strftime("%Y%m%d%H%M")
        except ValueError:
            continue

    print("⚠ Could not parse that date/time. Using '0' (beginning of time).")
    return "0"


def prompt_model_choice() -> str:
    raw = input("Which machine type are you setting up? [PS1 / PS2 / Both] ").strip().upper()
    if raw in ("PS1", "PS2", "BOTH"):
        return raw
    print("⚠ Invalid choice. Defaulting to PS1.")
    return "PS1"


def prompt_duration_hours():
    hours = input("How many hours should the overnight test run? ").strip()
    try:
        h = float(hours)
        if h <= 0:
            raise ValueError
        return h
    except:
        print("❌ Invalid number of hours.")
        return None


def run_scan_script(since: str) -> bool:
    scan_script = os.path.join(SCRIPT_DIR, "scan_network_for_ps_machines.py")

    if not os.path.exists(scan_script):
        print("❌ Could not find scan_network_for_ps_machines.py")
        return False

    print("\n▶ Running network scan to build hosts.txt ...\n")

    try:
        subprocess.run([sys.executable, scan_script, "--since", since], check=True)
        print("\n✔ Network scan complete.\n")
        return True
    except Exception as e:
        print(f"❌ Error running scan script: {e}")
        return False


def run_log_parser(model_choice: str):
    """Runs remote_error_log_parser.py with model selection"""
    log_script = os.path.join(SCRIPT_DIR, "remote_error_log_parser.py")

    if not os.path.exists(log_script):
        print("❌ Could not find remote_error_log_parser.py")
        return

    choice = model_choice.strip().upper()
    if choice == "BOTH":
        choice = "BOTH"  # normalize

    print("\n▶ Running error log parser...\n")
    subprocess.run([sys.executable, log_script, "--model", choice])



def filter_machines_for_choice(machines, choice: str):
    choice = choice.upper().strip()
    if choice == "PS1":
        return [(n, ip) for n, ip in machines if is_ps1_name(n)]
    if choice == "PS2":
        return [(n, ip) for n, ip in machines if is_ps2_name(n)]
    if choice == "BOTH":
        return [(n, ip) for n, ip in machines if is_ps1_name(n) or is_ps2_name(n)]
    return []


def main():
    load_dotenv()

    ps_user = os.getenv("SSH_USERNAME")
    ps_pass = os.getenv("SSH_PASSWORD")

    if not ps_user or not ps_pass:
        print("❌ Missing SSH_USERNAME or SSH_PASSWORD in .env")
        return

    creds = SSHCredentials(username=ps_user, password=ps_pass)
    repo = HostsRepo(HOSTS_FILE)

    print("\n===== OVERNIGHT TESTING SETUP =====\n")

    model_choice = prompt_model_choice()

    since_input = input(
        "When should error log retrieval start from?\n"
        "Examples:\n"
        "  - 202512081900\n"
        "  - 2025-12-08 19:00\n"
        "  - (blank) for 'beginning of time'\n"
        "> "
    )
    since = parse_since_input(since_input)

    hours_float = prompt_duration_hours()
    if hours_float is None:
        return

    wait_seconds = hours_float * 3600

    # STEP 1 → scan and write hosts.txt with SINCE from main
    if not run_scan_script(since):
        return

    # STEP 2 → load hosts via repo
    since_from_file, machine_objs = repo.load()
    if not machine_objs:
        print("❌ No machines found in hosts.txt.")
        return

    if since_from_file != since:
        print(f"⚠ SINCE mismatch! main={since} hosts.txt={since_from_file}")
        print("⚠ Ensure updated scan script is in place.")
        return

    machines = [(m.name, m.ip) for m in machine_objs]
    selected = filter_machines_for_choice(machines, model_choice)

    if not selected:
        print(f"❌ No {model_choice} machines found after filtering.")
        return

    ps1_selected = [(n, ip) for n, ip in selected if is_ps1_name(n)]
    ps2_selected = [(n, ip) for n, ip in selected if is_ps2_name(n)]

    print(f"\n📝 Confirmed SINCE from main is in hosts.txt: {since}")
    print(f"✔ Selected PS1 machines: {len(ps1_selected)}")
    print(f"✔ Selected PS2 machines: {len(ps2_selected)}\n")

    # STEP 3 → start overnight tests
    print("\n🛠 Setting up overnight testing...\n")

    if model_choice in ("PS1", "BOTH") and ps1_selected:
        start_tests_bulk(ps1_selected, creds, "PS1")

    if model_choice in ("PS2", "BOTH") and ps2_selected:
        print("⚠ PS2 remote overnight start is not implemented yet.")
        print("   Please start PS2 overnight testing manually.\n")

    # STEP 4 → wait
    print(f"\n⏳ Waiting {hours_float} hours ({int(wait_seconds)} seconds)...\n")
    time.sleep(wait_seconds)

    # STEP 5 → stop overnight tests

    if model_choice in ("PS1", "BOTH") and ps1_selected:
        stop_tests_bulk(ps1_selected, creds, "PS1")

    if model_choice in ("PS2", "BOTH") and ps2_selected:
        print("⚠ PS2 remote overnight stop is not implemented yet.")
        print("   Please stop PS2 overnight testing manually if needed.\n")

    # STEP 6 → run log parser
    print("\n⏰ Time's up — collecting logs!\n")
    run_log_parser(model_choice)


if __name__ == "__main__":
    main()
