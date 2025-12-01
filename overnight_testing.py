import os
import time
import paramiko
import subprocess
import sys
from dotenv import load_dotenv


def run_scan_script():
    """Runs scan_network_for_ps_machines.py before starting overnight testing."""
    scan_script = os.path.join(os.path.dirname(__file__), "scan_network_for_ps_machines.py")

    if not os.path.exists(scan_script):
        print("❌ Could not find scan_network_for_ps_machines.py")
        return False

    print("\n▶ Running network scan to build hosts.txt ...\n")

    try:
        subprocess.run([sys.executable, scan_script], check=True)
        print("\n✔ Network scan complete.\n")
        return True

    except Exception as e:
        print(f"❌ Error running scan script: {e}")
        return False


def load_hosts():
    hosts_file = os.path.join(os.path.dirname(__file__), "hosts.txt")

    if not os.path.exists(hosts_file):
        print("❌ hosts.txt not found after scanning. Something went wrong.")
        return None, None

    with open(hosts_file) as f:
        lines = [x.strip() for x in f.readlines() if x.strip()]

    since = lines[0].replace("SINCE=", "")
    machines = []

    for line in lines[1:]:
        if "," in line:
            name, ip = line.split(",", 1)
            machines.append((name, ip))

    return since, machines


def ssh_send_commands(ip, user, passwd):
    """Use Paramiko to attach to screen and send commands."""
    print(f"📡 Connecting to {ip}...")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=passwd, timeout=10)

        channel = client.invoke_shell()
        time.sleep(1)

        # Enter screen session
        channel.send("screen -x\n")
        time.sleep(2)

        # Run commands inside screen
        channel.send("16\n")
        time.sleep(1)

        channel.send("14\n")
        time.sleep(1)

        print(f"✔ Overnight test mode enabled on {ip}")

        channel.close()
        client.close()
        return True

    except Exception as e:
        print(f"❌ Failed on {ip}: {e}")
        return False

def ssh_stop_testing(ip, user, passwd):
    """Exit the overnight testing loop by sending Enter, 'q', Enter."""
    print(f"🛑 Connecting to {ip} to STOP testing...")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=passwd, timeout=10)

        channel = client.invoke_shell()
        time.sleep(1)

        channel.send("screen -x\n")  # Attach
        time.sleep(2)

        channel.send("\n")           # Enter  
        time.sleep(0.5)
        channel.send("q\n")          # q + Enter
        time.sleep(1)

        channel.send("\x03")        # Send CTRL+C
        time.sleep(0.7)

        print(f"✔ Overnight testing stopped on {ip}")

        channel.close()
        client.close()
        return True

    except Exception as e:
        print(f"❌ Failed stopping test on {ip}: {e}")
        return False


def run_log_parser():
    """Runs remote_error_log_parser.py"""
    log_script = os.path.join(os.path.dirname(__file__), "remote_error_log_parser.py")

    if not os.path.exists(log_script):
        print("❌ Could not find remote_error_log_parser.py")
        return

    print("\n▶ Running error log parser...\n")
    subprocess.run([sys.executable, log_script])


def main():
    load_dotenv()

    ps_user = os.getenv("SSH_USERNAME")
    ps_pass = os.getenv("SSH_PASSWORD")

    if not ps_user or not ps_pass:
        print("❌ Missing PS_USER or PS_PASS in .env")
        return

    # STEP 1 → run scanner to rebuild hosts.txt
    if not run_scan_script():
        return

    # STEP 2 → load hosts
    since, machines = load_hosts()

    if machines is None:
        return

    print("\n===== OVERNIGHT TESTING SETUP =====\n")

    hours = input("How many hours should the test run before collecting logs? ").strip()

    try:
        hours_float = float(hours)
        wait_seconds = hours_float * 3600
    except:
        print("❌ Invalid number of hours.")
        return

    print("\n🛠 Sending machines into overnight testing mode...\n")

    # STEP 3 → put each machine into test mode
    for name, ip in machines:
        print("\n==============================")
        print(f"🟦 Machine: {name} ({ip})")
        print("==============================\n")

        ssh_send_commands(ip, ps_user, ps_pass)

    # STEP 4 → wait
    print(f"\n⏳ Waiting {hours_float} hours ({int(wait_seconds)} seconds)...\n")
    time.sleep(wait_seconds)

    # STEP 5 → Quit the Overnight Testing
    print("\n🛑 Stopping overnight test mode on all machines...\n")

    for name, ip in machines:
        print("\n==============================")
        print(f"🟥 Stopping: {name} ({ip})")
        print("==============================\n")

        ssh_stop_testing(ip, ps_user, ps_pass)

    
    # STEP 6 → run log parser
    print("\n⏰ Time's up — collecting logs!\n")
    run_log_parser()


if __name__ == "__main__":
    main()
