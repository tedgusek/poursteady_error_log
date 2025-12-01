import base64
import urllib.request
import urllib.error
import ssl
import re
import json
from dotenv import load_dotenv
import os
import subprocess
import sys

POSSIBLE_ENDPOINTS = [
    "/device_map.json",
    "/device_map.js",
    "/ajax/device_info",
    "/ajax/device_map.json",
    "/ajax/device_list",
    "/attached_devices.json",
    "/DEV_device_info.htm",
    "/AttachedDevices.htm",
    "/attached_devices.htm",
    "/DEVICEINFOv2.htm",
]

SCHEMES = ["http", "https"]


def fetch_orbi_raw(router_ip, username, password):
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "User-Agent": "Mozilla/5.0",
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for scheme in SCHEMES:
        for ep in POSSIBLE_ENDPOINTS:
            url = f"{scheme}://{router_ip}{ep}"
            req = urllib.request.Request(url, headers=headers)

            try:
                resp = urllib.request.urlopen(req, timeout=5, context=ctx)
                raw = resp.read().decode("utf-8", errors="ignore")

                if "device_changed" in raw and "device=" in raw:
                    return raw, url

            except:
                pass

    return None, None


def parse_orbi_devices(raw_text):
    clean = raw_text.strip()

    device_match = re.search(r"device\s*=\s*(\[.*\])", clean, re.DOTALL)
    if not device_match:
        return None

    device_json_text = device_match.group(1)

    try:
        return json.loads(device_json_text)
    except:
        return None


def filter_ps_devices(devices):
    results = []
    for d in devices:
        name = d.get("name", "")
        ip = d.get("ip", "")
        if re.search(r"ps", name, re.IGNORECASE):
            results.append((name, ip))
    return results


def write_hosts_file(since_value, ps_devices):
    """Overwrites hosts.txt in the same folder as this script."""
    filepath = os.path.join(os.path.dirname(__file__), "hosts.txt")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"SINCE={since_value}\n\n")
        for name, ip in ps_devices:
            f.write(f"{name},{ip}\n")

    print(f"\n✔ hosts.txt updated at: {filepath}\n")


# def run_shell_script():
#     """Runs remote_error_log_parser.sh located in same folder."""
#     script_path = os.path.join(os.path.dirname(__file__), "remote_error_log_parser.sh")

#     if not os.path.exists(script_path):
#         print(f"❌ Shell script not found: {script_path}")
#         return

#     print(f"▶ Running shell script: {script_path}")

#     try:
#         subprocess.run(["bash", script_path], check=True)
#         print("✔ Shell script completed.\n")
#     except subprocess.CalledProcessError as e:
#         print(f"❌ Script failed with error: {e}")
#     except Exception as e:
#         print(f"❌ Unexpected error running script: {e}")

# def run_shell_script_windows_auto():
#     """
#     Automatically detects a usable bash interpreter in Windows:
#     - Git Bash
#     - WSL
#     - Cygwin
#     - MSYS2
#     Then executes remote_error_log_parser.sh with it.
#     """

#     script_path = os.path.join(os.path.dirname(__file__), "remote_error_log_parser.sh")

#     if not os.path.exists(script_path):
#         print(f"❌ Could not find remote_error_log_parser.sh at: {script_path}")
#         return

#     print("\n=== Detecting bash environments on Windows ===")

#     # 1️⃣ Check Git Bash
#     git_bash_paths = [
#         r"C:\Program Files\Git\bin\bash.exe",
#         r"C:\Program Files (x86)\Git\bin\bash.exe",
#         r"C:\Program Files\Git\usr\bin\bash.exe",
#     ]
#     for path in git_bash_paths:
#         if os.path.exists(path):
#             print(f"✔ Using Git Bash: {path}")
#             try:
#                 subprocess.run([path, script_path], check=True)
#                 print("✔ Shell script completed via Git Bash.\n")
#                 return
#             except Exception as e:
#                 print(f"❌ Git Bash failed: {e}")

#     # 2️⃣ Check WSL
#     try:
#         wsl_check = subprocess.run(
#             ["wsl", "bash", "-c", "echo WSL_OK"],
#             capture_output=True, text=True
#         )
#         if "WSL_OK" in wsl_check.stdout:
#             print("✔ Using WSL bash")
#             subprocess.run(["wsl", "bash", script_path], check=True)
#             print("✔ Shell script completed via WSL.\n")
#             return
#     except Exception:
#         pass

#     # 3️⃣ Check Cygwin
#     cygwin_bash = r"C:\cygwin64\bin\bash.exe"
#     if os.path.exists(cygwin_bash):
#         print(f"✔ Using Cygwin bash: {cygwin_bash}")
#         try:
#             subprocess.run([cygwin_bash, script_path], check=True)
#             print("✔ Shell script completed via Cygwin.\n")
#             return
#         except Exception as e:
#             print(f"❌ Cygwin bash failed: {e}")

#     # 4️⃣ Check MSYS2
#     msys_bash = r"C:\msys64\usr\bin\bash.exe"
#     if os.path.exists(msys_bash):
#         print(f"✔ Using MSYS2 bash: {msys_bash}")
#         try:
#             subprocess.run([msys_bash, script_path], check=True)
#             print("✔ Shell script completed via MSYS.\n")
#             return
#         except Exception as e:
#             print(f"❌ MSYS bash failed: {e}")

#     # ❌ Nothing found
#     print("\n❌ No bash environment found on Windows.")
#     print("Install Git for Windows here: https://git-scm.com/download/win")
#     print("or install WSL: wsl --install\n")


def run_python_log_parser():
    """
    Runs remote_error_log_parser.py using the same Python interpreter.
    """
    script_path = os.path.join(os.path.dirname(__file__), "remote_error_log_parser.py")

    if not os.path.exists(script_path):
        print(f"❌ Could not find remote_error_log_parser.py at: {script_path}")
        return

    print(f"▶ Running Python log parser: {script_path}")

    try:
        subprocess.run([sys.executable, script_path], check=True)
        print("✔ Log parser completed.\n")
    except Exception as e:
        print(f"❌ Error running log parser: {e}")


def main():
    # Load environment variables
    load_dotenv()

    router_ip = os.getenv("ORBI_IP")
    username = os.getenv("ORBI_USER")
    password = os.getenv("ORBI_PASS")

    if not router_ip or not username or not password:
        print("❌ Missing ORBI_IP, ORBI_USER, or ORBI_PASS in .env file.")
        return

    # Prompt for SINCE time
    user_input = input("Enter start time (YYYY-MM-DDTHH:MM) or leave blank: ").strip()
    since = user_input if user_input else "000000000000"

    # Fetch Orbi device list
    raw, url = fetch_orbi_raw(router_ip, username, password)
    if not raw:
        print("❌ Could not locate device list endpoint.")
        return

    devices = parse_orbi_devices(raw)
    if not devices:
        print("❌ Could not parse device list.")
        return

    ps_devices = filter_ps_devices(devices)

    # Write hosts.txt
    write_hosts_file(since, ps_devices)

    # Run remote_error_log_parser.sh
    run_python_log_parser()


if __name__ == "__main__":
    main()
