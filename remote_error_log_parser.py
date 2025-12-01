import paramiko
import os
from dotenv import load_dotenv

LOG_COMMAND = r'''
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

def ssh_run(ip, user, passwd, since):
    cmd = LOG_COMMAND.replace("%SINCE%", since)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(ip, username=user, password=passwd, timeout=10)
    except Exception as e:
        print(f"❌ Could not SSH to {ip}: {e}")
        return None

    stdin, stdout, stderr = client.exec_command(cmd, timeout=25)
    output = stdout.read().decode()
    client.close()

    return output.strip() if output.strip() else None


def main():
    load_dotenv()

    user = os.getenv("SSH_USERNAME")
    passwd = os.getenv("SSH_PASSWORD")

    hosts_path = os.path.join(os.path.dirname(__file__), "hosts.txt")

    if not os.path.exists(hosts_path):
        print("❌ hosts.txt not found! Run the scanner first.")
        return

    with open(hosts_path) as f:
        lines = [x.strip() for x in f.readlines() if x.strip()]

    since_line = lines[0]
    since = since_line.replace("SINCE=", "")

    devices = []
    for line in lines[1:]:
        if "," in line:
            name, ip = line.split(",", 1)
            devices.append((name, ip))

    print(f"\n=== Starting Log Parsing (SINCE {since}) ===\n")

    for name, ip in devices:
        print("\n==============================")
        print(f"🟦 Machine: {name} ({ip})")
        print("==============================\n")

        result = ssh_run(ip, user, passwd, since)

        if not result:
            print("❌ No output (SSH or parsing failed)")
        else:
            print(result)


if __name__ == "__main__":
    main()
