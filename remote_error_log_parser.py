# remote_error_log_parser.py
import os
import argparse
from dotenv import load_dotenv

from hosts_repo import HostsRepo
from error_log_parser import ErrorLogParser

SCRIPT_DIR = os.path.dirname(__file__)
HOSTS_FILE = os.path.join(SCRIPT_DIR, "hosts.txt")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run remote error log parsing for PS1/PS2 based on hosts.txt"
    )
    parser.add_argument(
        "--model",
        default="BOTH",
        choices=["PS1", "PS2", "BOTH", "Both"],
        help="Which machine type to parse logs for."
    )
    args = parser.parse_args()

    model_choice = args.model.upper()
    if model_choice == "BOTH" or model_choice == "BOTH".upper():
        model_choice = "BOTH"

    repo = HostsRepo(HOSTS_FILE)
    log_parser = ErrorLogParser.from_env()

    log_parser.run_from_hosts(repo, model_choice=model_choice)


if __name__ == "__main__":
    main()
