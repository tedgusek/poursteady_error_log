# main.py
import os
import sys
import time
import subprocess
import signal
from datetime import datetime

from dotenv import load_dotenv

from overnight_testing import SSHCredentials, OvernightTester, UserCancelledException
from hosts_repo import HostsRepo
from models import Machine, is_ps1_name, is_ps2_name

SCRIPT_DIR = os.path.dirname(__file__)
HOSTS_FILE = os.path.join(SCRIPT_DIR, "hosts.txt")


class InterruptibleTimer:
    """A timer that can be interrupted by the user"""
    
    def __init__(self):
        self.cancelled = False
        self.original_handler = None
    
    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C during wait"""
        print("\n\n⚠️  Wait interrupted by user!")
        print("\nOptions:")
        print("  [C]ontinue waiting")
        print("  [S]kip to log collection now")
        print("  [Q]uit program")
        
        while True:
            choice = input("\nYour choice [C/S/Q]: ").strip().upper()
            if choice in ('C', 'CONTINUE', ''):
                print("Continuing to wait...\n")
                return
            elif choice in ('S', 'SKIP'):
                print("Skipping remaining wait time...\n")
                self.cancelled = True
                return
            elif choice in ('Q', 'QUIT'):
                print("\n👋 Exiting program...")
                sys.exit(0)
            else:
                print("Invalid choice. Please enter C, S, or Q.")
    
    def wait_with_progress(self, total_seconds: float, check_interval: float = 10.0):
        """
        Wait for specified seconds with progress updates and interrupt capability.
        
        Args:
            total_seconds: Total time to wait in seconds
            check_interval: How often to print progress (default: 10 seconds)
        """
        # Set up signal handler for Ctrl+C
        self.original_handler = signal.signal(signal.SIGINT, self._signal_handler)
        
        start_time = time.time()
        last_progress = 0
        
        try:
            while True:
                elapsed = time.time() - start_time
                remaining = total_seconds - elapsed
                
                if remaining <= 0 or self.cancelled:
                    break
                
                # Print progress at intervals
                progress_pct = (elapsed / total_seconds) * 100
                if progress_pct >= last_progress + 10:  # Every 10%
                    hours_remaining = remaining / 3600
                    mins_remaining = (remaining % 3600) / 60
                    print(f"⏳ Progress: {progress_pct:.0f}% | Remaining: {int(hours_remaining)}h {int(mins_remaining)}m | Press Ctrl+C to skip")
                    last_progress = progress_pct
                
                # Sleep in small chunks to be responsive to interrupt
                sleep_time = min(check_interval, remaining)
                time.sleep(sleep_time)
                
        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, self.original_handler)
        
        if self.cancelled:
            print("⏭️  Wait skipped by user\n")
        else:
            print("✅ Wait complete!\n")


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

    print("⚠️  Could not parse that date/time. Using '0' (beginning of time).")
    return "0"


def prompt_model_choice() -> str:
    raw = input("Which machine type are you setting up? [PS1 / PS2 / Both] ").strip().upper()
    if raw in ("PS1", "PS2", "BOTH"):
        return raw
    print("⚠️  Invalid choice. Defaulting to PS1.")
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


def confirm_action(prompt: str) -> bool:
    """Ask user for yes/no confirmation"""
    while True:
        response = input(f"{prompt} [Y/n]: ").strip().upper()
        if response in ('Y', 'YES', ''):
            return True
        elif response in ('N', 'NO'):
            return False
        else:
            print("Please enter Y or N.")


def run_scan_script(since: str) -> bool:
    scan_script = os.path.join(SCRIPT_DIR, "scan_network_for_ps_machines.py")

    if not os.path.exists(scan_script):
        print("❌ Could not find scan_network_for_ps_machines.py")
        return False

    print("\n▶ Running network scan to build hosts.txt ...\n")

    try:
        subprocess.run([sys.executable, scan_script, "--since", since], check=True)
        print("\n✅ Network scan complete.\n")
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
    try:
        subprocess.run([sys.executable, log_script, "--model", choice], check=True)
    except KeyboardInterrupt:
        print("\n\n⚠️  Log parsing interrupted by user")
        if confirm_action("Do you want to continue with the program?"):
            pass
        else:
            print("👋 Exiting...")
            sys.exit(0)


def filter_machines_for_choice(machines, choice: str):
    choice = choice.upper().strip()
    if choice == "PS1":
        return [m for m in machines if is_ps1_name(m.name)]
    if choice == "PS2":
        return [m for m in machines if is_ps2_name(m.name)]
    if choice == "BOTH":
        return [m for m in machines if is_ps1_name(m.name) or is_ps2_name(m.name)]
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
    print("\n" + "="*50)
    print("STEP 1: SCANNING NETWORK")
    print("="*50)
    
    if not confirm_action("\nProceed with network scan?"):
        print("👋 Cancelled by user")
        return
    
    if not run_scan_script(since):
        return

    # STEP 2 → load hosts via repo
    print("\n" + "="*50)
    print("STEP 2: LOADING MACHINE LIST")
    print("="*50)
    
    since_from_file, machine_objs = repo.load()
    if not machine_objs:
        print("❌ No machines found in hosts.txt.")
        return

    if since_from_file != since:
        print(f"⚠️  SINCE mismatch! main={since} hosts.txt={since_from_file}")
        print("⚠️  Ensure updated scan script is in place.")
        if not confirm_action("Continue anyway?"):
            return

    selected = filter_machines_for_choice(machine_objs, model_choice)

    if not selected:
        print(f"❌ No {model_choice} machines found after filtering.")
        return

    ps1_selected = [m for m in selected if is_ps1_name(m.name)]
    ps2_selected = [m for m in selected if is_ps2_name(m.name)]

    print(f"\n📝 Confirmed SINCE from main is in hosts.txt: {since}")
    print(f"✅ Selected PS1 machines: {len(ps1_selected)}")
    print(f"✅ Selected PS2 machines: {len(ps2_selected)}")
    
    if ps1_selected:
        print("\nPS1 machines:")
        for m in ps1_selected:
            print(f"   • {m.name} ({m.ip})")
    
    if ps2_selected:
        print("\nPS2 machines:")
        for m in ps2_selected:
            print(f"   • {m.name} ({m.ip})")

    # STEP 3 → start overnight tests
    print("\n" + "="*50)
    print("STEP 3: STARTING OVERNIGHT TESTS")
    print("="*50)
    
    if not confirm_action("\nProceed with starting overnight tests?"):
        print("⏭️  Skipping test start")
    else:
        print("\n🛠️  Setting up overnight testing...\n")
        
        tester = OvernightTester(creds, max_retries=3, retry_delay=5.0)
        
        try:
            if model_choice in ("PS1", "BOTH") and ps1_selected:
                tester.start_bulk(ps1_selected, "PS1", interactive=True)

            if model_choice in ("PS2", "BOTH") and ps2_selected:
                print("⚠️  PS2 remote overnight start is not implemented yet.")
                print("   Please start PS2 overnight testing manually.\n")
        
        except UserCancelledException:
            print("\n⚠️  Test start cancelled by user")
            if not confirm_action("Do you want to continue with the program?"):
                print("👋 Exiting...")
                return

    # STEP 4 → wait
    print("\n" + "="*50)
    print("STEP 4: WAITING FOR TEST COMPLETION")
    print("="*50)
    print(f"\n⏳ Waiting {hours_float} hours ({int(wait_seconds)} seconds)...")
    print("💡 Tip: Press Ctrl+C anytime to skip the wait\n")
    
    timer = InterruptibleTimer()
    timer.wait_with_progress(wait_seconds, check_interval=60)

    # STEP 5 → stop overnight tests
    print("\n" + "="*50)
    print("STEP 5: STOPPING OVERNIGHT TESTS")
    print("="*50)
    
    if not confirm_action("\nProceed with stopping overnight tests?"):
        print("⏭️  Skipping test stop")
    else:
        tester = OvernightTester(creds, max_retries=3, retry_delay=5.0)
        
        try:
            if model_choice in ("PS1", "BOTH") and ps1_selected:
                tester.stop_bulk(ps1_selected, "PS1", interactive=True)

            if model_choice in ("PS2", "BOTH") and ps2_selected:
                print("⚠️  PS2 remote overnight stop is not implemented yet.")
                print("   Please stop PS2 overnight testing manually if needed.\n")
        
        except UserCancelledException:
            print("\n⚠️  Test stop cancelled by user")
            if not confirm_action("Do you want to continue with log collection?"):
                print("👋 Exiting...")
                return

    # STEP 6 → run log parser
    print("\n" + "="*50)
    print("STEP 6: COLLECTING ERROR LOGS")
    print("="*50)
    
    if not confirm_action("\nProceed with log collection?"):
        print("⏭️  Skipping log collection")
        print("\n✅ Program complete!")
        return
    
    print("\n⏰ Time's up — collecting logs!\n")
    run_log_parser(model_choice)
    
    print("\n" + "="*50)
    print("✅ ALL STEPS COMPLETE!")
    print("="*50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Program interrupted by user")
        print("👋 Goodbye!")
        sys.exit(0)