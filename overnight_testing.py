# overnight_testing.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Dict

import paramiko

from models import Machine, is_ps1_name, is_ps2_name, infer_model_from_name


# PS1 sequences are known
MODEL_START_SEQUENCES: Dict[str, List[str]] = {
    "PS1": ["screen -x", "16", "14"],
    # PS2 placeholder (not used yet)
    "PS2": [],
}

MODEL_STOP_SEQUENCES: Dict[str, List[str]] = {
    "PS1": ["screen -x", "", "q", "\x03"],
    # PS2 placeholder (not used yet)
    "PS2": [],
}


@dataclass(frozen=True)
class SSHCredentials:
    username: str
    password: str
    timeout: int = 10


def _open_shell(ip: str, creds: SSHCredentials):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username=creds.username, password=creds.password, timeout=creds.timeout)
    channel = client.invoke_shell()
    time.sleep(1)
    return client, channel


def _send_sequence(channel, sequence: List[str], per_step_delay=1.0, attach_delay=2.0):
    for i, cmd in enumerate(sequence):
        if cmd == "\x03":
            channel.send(cmd)
        else:
            channel.send(cmd + "\n")

        if i == 0 and "screen -x" in cmd:
            time.sleep(attach_delay)
        else:
            time.sleep(per_step_delay)


class OvernightTester:
    def __init__(self, creds: SSHCredentials):
        self.creds = creds

    def start_one(self, machine: Machine) -> bool:
        sequence = MODEL_START_SEQUENCES["PS1"]

        client = None
        channel = None
        try:
            print(f"📡 Connecting to {machine.ip} to START overnight testing (PS1)...")
            client, channel = _open_shell(machine.ip, self.creds)
            _send_sequence(channel, sequence)
            print(f"✔ Overnight test mode enabled on {machine.ip}")
            return True
        except Exception as e:
            print(f"❌ Failed starting test on {machine.ip}: {e}")
            return False
        finally:
            try:
                if channel:
                    channel.close()
            except:
                pass
            try:
                if client:
                    client.close()
            except:
                pass

    def stop_one(self, machine: Machine) -> bool:
        sequence = MODEL_STOP_SEQUENCES["PS1"]

        client = None
        channel = None
        try:
            print(f"🛑 Connecting to {machine.ip} to STOP overnight testing (PS1)...")
            client, channel = _open_shell(machine.ip, self.creds)
            _send_sequence(channel, sequence, per_step_delay=0.7)
            print(f"✔ Overnight testing stopped on {machine.ip}")
            return True
        except Exception as e:
            print(f"❌ Failed stopping test on {machine.ip}: {e}")
            return False
        finally:
            try:
                if channel:
                    channel.close()
            except:
                pass
            try:
                if client:
                    client.close()
            except:
                pass

    def start_bulk(self, machines: Iterable[Machine], model_choice: str) -> None:
        choice = model_choice.upper().strip()

        for m in machines:
            # Strict selection filter
            if choice == "PS1" and not is_ps1_name(m.name):
                continue
            if choice == "PS2" and not is_ps2_name(m.name):
                continue
            if choice == "BOTH" and not (is_ps1_name(m.name) or is_ps2_name(m.name)):
                continue

            # PS2 not supported remotely yet
            if is_ps2_name(m.name):
                print("\n==============================")
                print(f"🟨 PS2 Machine: {m.name} ({m.ip})")
                print("⚠ PS2 remote overnight start is not implemented yet.")
                print("   Please start PS2 overnight testing manually.")
                print("==============================\n")
                continue

            print("\n==============================")
            print(f"🟦 Starting Overnight Test (PS1): {m.name} ({m.ip})")
            print("==============================\n")
            self.start_one(m)

    def stop_bulk(self, machines: Iterable[Machine], model_choice: str) -> None:
        choice = model_choice.upper().strip()

        for m in machines:
            # Strict selection filter
            if choice == "PS1" and not is_ps1_name(m.name):
                continue
            if choice == "PS2" and not is_ps2_name(m.name):
                continue
            if choice == "BOTH" and not (is_ps1_name(m.name) or is_ps2_name(m.name)):
                continue

            # PS2 not supported remotely yet
            if is_ps2_name(m.name):
                print("\n==============================")
                print(f"🟨 PS2 Machine: {m.name} ({m.ip})")
                print("⚠ PS2 remote overnight stop is not implemented yet.")
                print("   Please stop PS2 overnight testing manually if needed.")
                print("==============================\n")
                continue

            print("\n==============================")
            print(f"🟥 Stopping Overnight Test (PS1): {m.name} ({m.ip})")
            print("==============================\n")
            self.stop_one(m)


# Backward compatible helpers
def start_tests_bulk(machines, creds, model_choice):
    tester = OvernightTester(creds)
    tester.start_bulk([Machine(n, ip) for n, ip in machines], model_choice)

def stop_tests_bulk(machines, creds, model_choice):
    tester = OvernightTester(creds)
    tester.stop_bulk([Machine(n, ip) for n, ip in machines], model_choice)
