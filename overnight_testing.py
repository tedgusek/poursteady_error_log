# overnight_testing.py
from __future__ import annotations

import time
import signal
import sys
from dataclasses import dataclass
from typing import Iterable, List, Dict, Optional

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


class UserCancelledException(Exception):
    """Raised when user requests to cancel operation"""
    pass


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
    def __init__(self, creds: SSHCredentials, max_retries: int = 3, retry_delay: float = 5.0):
        self.creds = creds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_cancelled = False

    def _retry_operation(self, operation_func, machine: Machine, operation_name: str) -> bool:
        """
        Retry an operation with exponential backoff.
        Returns True if successful, False if all retries exhausted.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                result = operation_func(machine, attempt)
                if result:
                    return True
                
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"   ⏱️  Retrying in {wait_time:.1f} seconds... (Attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    
            except UserCancelledException:
                raise
            except Exception as e:
                print(f"   ❌ Attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"   ⏱️  Retrying in {wait_time:.1f} seconds... (Attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
        
        print(f"   ❌ All {self.max_retries} attempts failed for {machine.name}")
        return False

    def _start_one_attempt(self, machine: Machine, attempt: int) -> bool:
        """Single attempt to start overnight testing"""
        sequence = MODEL_START_SEQUENCES["PS1"]

        client = None
        channel = None
        try:
            if attempt > 1:
                print(f"   🔄 Attempt {attempt}: Connecting to {machine.ip}...")
            else:
                print(f"📡 Connecting to {machine.ip} to START overnight testing (PS1)...")
            
            client, channel = _open_shell(machine.ip, self.creds)
            _send_sequence(channel, sequence)
            print(f"✅ Overnight test mode enabled on {machine.name} ({machine.ip})")
            return True
        except Exception as e:
            if attempt == 1:
                print(f"❌ Failed starting test on {machine.ip}: {e}")
            raise
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

    def _stop_one_attempt(self, machine: Machine, attempt: int) -> bool:
        """Single attempt to stop overnight testing"""
        sequence = MODEL_STOP_SEQUENCES["PS1"]

        client = None
        channel = None
        try:
            if attempt > 1:
                print(f"   🔄 Attempt {attempt}: Connecting to {machine.ip}...")
            else:
                print(f"🛑 Connecting to {machine.ip} to STOP overnight testing (PS1)...")
            
            client, channel = _open_shell(machine.ip, self.creds)
            _send_sequence(channel, sequence, per_step_delay=0.7)
            print(f"✅ Overnight testing stopped on {machine.name} ({machine.ip})")
            return True
        except Exception as e:
            if attempt == 1:
                print(f"❌ Failed stopping test on {machine.ip}: {e}")
            raise
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

    def start_one(self, machine: Machine) -> bool:
        """Start overnight testing with retry logic"""
        return self._retry_operation(self._start_one_attempt, machine, "start")

    def stop_one(self, machine: Machine) -> bool:
        """Stop overnight testing with retry logic"""
        return self._retry_operation(self._stop_one_attempt, machine, "stop")

    def _prompt_continue_or_skip(self, machine: Machine, operation: str) -> str:
        """
        Prompt user for action after a failure.
        Returns: 'continue', 'skip', or 'cancel'
        """
        print(f"\n⚠️  Failed to {operation} overnight testing on {machine.name} ({machine.ip})")
        print("Options:")
        print("  [C]ontinue to next machine")
        print("  [S]kip remaining machines")
        print("  [R]etry this machine")
        print("  [Q]uit program")
        
        while True:
            choice = input("Your choice [C/S/R/Q]: ").strip().upper()
            if choice in ('C', 'CONTINUE', ''):
                return 'continue'
            elif choice in ('S', 'SKIP'):
                return 'skip'
            elif choice in ('R', 'RETRY'):
                return 'retry'
            elif choice in ('Q', 'QUIT'):
                return 'cancel'
            else:
                print("Invalid choice. Please enter C, S, R, or Q.")

    def start_bulk(self, machines: Iterable[Machine], model_choice: str, interactive: bool = True) -> None:
        choice = model_choice.upper().strip()
        machines_list = list(machines)
        
        successful = []
        failed = []

        for idx, m in enumerate(machines_list, 1):
            if self.user_cancelled:
                print("\n⚠️  Operation cancelled by user. Skipping remaining machines.")
                break

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
                print("⚠️  PS2 remote overnight start is not implemented yet.")
                print("   Please start PS2 overnight testing manually.")
                print("==============================\n")
                continue

            print("\n==============================")
            print(f"🟦 Starting Overnight Test (PS1): {m.name} ({m.ip}) [{idx}/{len([x for x in machines_list if is_ps1_name(x.name)])}]")
            print("==============================\n")
            
            success = self.start_one(m)
            
            if success:
                successful.append(m)
            else:
                failed.append(m)
                
                if interactive:
                    action = self._prompt_continue_or_skip(m, "start")
                    
                    if action == 'retry':
                        print(f"\n🔄 Retrying {m.name}...\n")
                        success = self.start_one(m)
                        if success:
                            successful.append(m)
                            failed.remove(m)
                    elif action == 'skip':
                        print("\n⚠️  Skipping remaining machines.")
                        break
                    elif action == 'cancel':
                        self.user_cancelled = True
                        raise UserCancelledException("User cancelled operation")
                    # 'continue' just moves to next machine

        # Summary
        print("\n" + "="*50)
        print("START OPERATION SUMMARY")
        print("="*50)
        print(f"✅ Successful: {len(successful)}")
        print(f"❌ Failed: {len(failed)}")
        if failed:
            print("\nFailed machines:")
            for m in failed:
                print(f"  - {m.name} ({m.ip})")
        print("="*50 + "\n")

    def stop_bulk(self, machines: Iterable[Machine], model_choice: str, interactive: bool = True) -> None:
        choice = model_choice.upper().strip()
        machines_list = list(machines)
        
        successful = []
        failed = []

        for idx, m in enumerate(machines_list, 1):
            if self.user_cancelled:
                print("\n⚠️  Operation cancelled by user. Skipping remaining machines.")
                break

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
                print("⚠️  PS2 remote overnight stop is not implemented yet.")
                print("   Please stop PS2 overnight testing manually if needed.")
                print("==============================\n")
                continue

            print("\n==============================")
            print(f"🟥 Stopping Overnight Test (PS1): {m.name} ({m.ip}) [{idx}/{len([x for x in machines_list if is_ps1_name(x.name)])}]")
            print("==============================\n")
            
            success = self.stop_one(m)
            
            if success:
                successful.append(m)
            else:
                failed.append(m)
                
                if interactive:
                    action = self._prompt_continue_or_skip(m, "stop")
                    
                    if action == 'retry':
                        print(f"\n🔄 Retrying {m.name}...\n")
                        success = self.stop_one(m)
                        if success:
                            successful.append(m)
                            failed.remove(m)
                    elif action == 'skip':
                        print("\n⚠️  Skipping remaining machines.")
                        break
                    elif action == 'cancel':
                        self.user_cancelled = True
                        raise UserCancelledException("User cancelled operation")
                    # 'continue' just moves to next machine

        # Summary
        print("\n" + "="*50)
        print("STOP OPERATION SUMMARY")
        print("="*50)
        print(f"✅ Successful: {len(successful)}")
        print(f"❌ Failed: {len(failed)}")
        if failed:
            print("\nFailed machines:")
            for m in failed:
                print(f"  - {m.name} ({m.ip})")
        print("="*50 + "\n")


# Backward compatible helpers
def start_tests_bulk(machines, creds, model_choice):
    tester = OvernightTester(creds)
    tester.start_bulk([Machine(n, ip) for n, ip in machines], model_choice)

def stop_tests_bulk(machines, creds, model_choice):
    tester = OvernightTester(creds)
    tester.stop_bulk([Machine(n, ip) for n, ip in machines], model_choice)