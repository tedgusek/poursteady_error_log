# scan_network_for_ps_machines.py
import argparse
import os

from scanner_orbi import OrbiScanner
from hosts_repo import HostsRepo

SCRIPT_DIR = os.path.dirname(__file__)
HOSTS_FILE = os.path.join(SCRIPT_DIR, "hosts.txt")


def main():
    parser = argparse.ArgumentParser(
        description="Scan Orbi network for strict PS1/PS2 machines and write hosts.txt"
    )
    parser.add_argument(
        "--since",
        required=True,
        help="Log start time (e.g. 202512081900 or 0)."
    )
    args = parser.parse_args()
    since = args.since.strip()

    repo = HostsRepo(HOSTS_FILE)

    try:
        scanner = OrbiScanner.from_env()
        machines = scanner.scan_ps_machines()
    except Exception as e:
        print(f"❌ Scan failed: {e}")
        return

    if not machines:
        print("❌ No strict PS1/PS2 machines found on scan.")
        return

    repo.write(since, machines)

    print(f"\n✔ hosts.txt updated at: {HOSTS_FILE}")
    print(f"✔ SINCE={since}")
    print(f"✔ PS devices found: {len(machines)}\n")


if __name__ == "__main__":
    main()
