# error_log_parser.py
from __future__ import annotations

import os
import paramiko
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from hosts_repo import HostsRepo
from models import Machine, is_ps1_name, is_ps2_name


LOG_COMMAND_PS1 = r'''
{ zcat /data/poursteady/log/*-console.txt-*.gz 2>/dev/null;
  cat /data/poursteady/log/*-console.txt 2>/dev/null;
} | awk -v since="%SINCE%" '
BEGIN{IGNORECASE=1}
{
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
'''


@dataclass(frozen=True)
class SSHCredentials:
    username: str
    password: str
    timeout: int = 10


class ErrorLogParser:
    def __init__(self, creds: SSHCredentials):
        self.creds = creds

    @classmethod
    def from_env(cls):
        load_dotenv()
        user = os.getenv("SSH_USERNAME")
        passwd = os.getenv("SSH_PASSWORD")
        if not user or not passwd:
            raise ValueError("Missing SSH_USERNAME or SSH_PASSWORD in .env")
        return cls(SSHCredentials(user, passwd))

    def ssh_run_ps1(self, machine: Machine, since: str) -> Optional[str]:
        cmd = LOG_COMMAND_PS1.replace("%SINCE%", since)

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(machine.ip, username=self.creds.username, password=self.creds.password, timeout=self.creds.timeout)
            stdin, stdout, stderr = client.exec_command(cmd, timeout=25)
            output = stdout.read().decode()
            return output.strip() if output.strip() else None
        except Exception as e:
            print(f"❌ PS1 log SSH failed on {machine.ip}: {e}")
            return None
        finally:
            try:
                client.close()
            except:
                pass

    def run_from_hosts(self, repo: HostsRepo, model_choice: str = "BOTH") -> None:
        since, machines = repo.load()

        if not since:
            print("❌ hosts.txt missing SINCE line or file is empty.")
            return

        if not machines:
            print("❌ No devices found in hosts.txt.")
            return

        choice = model_choice.upper().strip()

        print(f"\n=== Starting Log Parsing (SINCE {since}) [{choice}] ===\n")

        for m in machines:
            if choice == "PS1" and not is_ps1_name(m.name):
                continue
            if choice == "PS2" and not is_ps2_name(m.name):
                continue
            if choice == "BOTH" and not (is_ps1_name(m.name) or is_ps2_name(m.name)):
                continue

            if is_ps1_name(m.name):
                print("\n==============================")
                print(f"🟦 PS1 Machine: {m.name} ({m.ip})")
                print("==============================\n")

                result = self.ssh_run_ps1(m, since)
                if not result:
                    print("❌ No output (SSH or parsing failed)")
                else:
                    print(result)

            elif is_ps2_name(m.name):
                print("\n==============================")
                print(f"🟨 PS2 Machine: {m.name} ({m.ip})")
                print("==============================\n")
                print("⚠ PS2 error log retrieval is not implemented yet.")
                print("   Skipping PS2 for now.")
