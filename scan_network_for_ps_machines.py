'''
Written by Lindelle Anglin (Linux/Embedded Device Support)
	
- Network scanner for finding devices with 'PS' in their name
- Optimized for Linux devices like BeagleBone Black
- Built to run on Windows OS
'''
import subprocess
import socket
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor


def get_hostname_mdns(ip):
    """Try to resolve via mDNS/Avahi (common on Linux/embedded devices)"""
    try:
        # Try .local resolution (mDNS)
        result = subprocess.run(
            ['ping', '-a', '-n', '1', '-w', '1000', ip],
            capture_output=True,
            text=True,
            timeout=3
        )
        for line in result.stdout.splitlines():
            if 'Pinging' in line:
                match = re.search(r'Pinging\s+(.+?)\s+\[', line)
                if match:
                    hostname = match.group(1).strip()
                    if hostname != ip and '.local' in hostname.lower():
                        return hostname.replace('.local', '')
                    elif hostname != ip:
                        return hostname
    except:
        pass
    return None


def get_hostname_dns_ptr(ip):
    """Try reverse DNS lookup (PTR record)"""
    try:
        result = socket.gethostbyaddr(ip)
        hostname = result[0]
        # Remove domain suffix, keep just hostname
        return hostname.split('.')[0]
    except:
        return None


def get_hostname_nmap_scan(ip):
    """Try nmap if available (requires nmap installed)"""
    try:
        result = subprocess.run(
            ['nmap', '-sn', '-T4', ip],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.splitlines():
            if 'Nmap scan report for' in line:
                # Format: "Nmap scan report for hostname (ip)"
                match = re.search(r'for\s+(.+?)\s+\(', line)
                if match:
                    hostname = match.group(1).strip()
                    if hostname != ip:
                        return hostname
    except:
        pass
    return None


def get_hostname_arp_scan(network_prefix):
    """Try arp-scan if available (Linux tool, but can work on Windows with WSL)"""
    try:
        result = subprocess.run(
            ['arp-scan', f'{network_prefix}.0/24'],
            capture_output=True,
            text=True,
            timeout=30
        )
        devices = {}
        for line in result.stdout.splitlines():
            # Format: IP    MAC    Hostname
            parts = line.split()
            if len(parts) >= 3 and '.' in parts[0]:
                ip = parts[0]
                if len(parts) >= 4:
                    hostname = ' '.join(parts[3:])
                    devices[ip] = hostname
        return devices
    except:
        pass
    return {}


def get_hostname_ssh_banner(ip):
    """Try to get hostname from SSH banner (common on Linux devices)"""
    try:
        # Connect to SSH port and read banner
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((ip, 22))
        banner = sock.recv(1024).decode('utf-8', errors='ignore')
        sock.close()
        
        # SSH banner often contains hostname
        # Format: SSH-2.0-OpenSSH_7.4 hostname
        if 'SSH' in banner:
            parts = banner.strip().split()
            if len(parts) >= 2:
                # Try to extract hostname from banner
                for part in parts[1:]:
                    if not part.startswith('OpenSSH') and not part.startswith('SSH'):
                        return part
    except:
        pass
    return None


def get_mac_vendor(ip):
    """Get MAC address vendor (might give clues about device type)"""
    try:
        result = subprocess.run('arp -a', capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if ip in line:
                # Extract MAC address
                match = re.search(r'([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})', line)
                if match:
                    return match.group(0)
    except:
        pass
    return None


def check_http_header(ip):
    """Try to get hostname from HTTP Server header"""
    import urllib.request
    try:
        # Try HTTP
        req = urllib.request.Request(f'http://{ip}', method='HEAD')
        response = urllib.request.urlopen(req, timeout=2)
        server = response.headers.get('Server', '')
        if server:
            return None  # Server header usually doesn't have hostname
    except:
        pass
    return None


def resolve_hostname_linux(ip):
    """Try methods that work for Linux/embedded devices"""
    
    methods = [
        ('mDNS/Ping', get_hostname_mdns),
        ('DNS-PTR', get_hostname_dns_ptr),
        ('SSH-Banner', get_hostname_ssh_banner),
        ('Nmap', get_hostname_nmap_scan),
    ]
    
    for method_name, method_func in methods:
        try:
            hostname = method_func(ip)
            if hostname and hostname != ip:
                return (hostname, method_name)
        except:
            continue
    
    return (None, None)


def scan_network_for_ps_machines(case_sensitive=False):
    """
    Scans network for BeagleBone Black or other Linux devices with 'PS' in hostname.
    """
    print("=" * 70)
    print("LINUX/EMBEDDED DEVICE SCANNER - BeagleBone Black".center(70))
    print("=" * 70)
    print("\n📟 Optimized for Linux/embedded devices (BeagleBone, Raspberry Pi, etc.)")
    
    search_term = 'PS' if case_sensitive else 'ps'
    print(f"\nSearch mode: {'Case-sensitive' if case_sensitive else 'Case-insensitive'}")
    print(f"Looking for '{search_term}' in device names...\n")
    
    t1 = datetime.now()
    
    # Get local IP
    print("[1/3] Getting local network information...")
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"      Local machine: {hostname} ({local_ip})")
    except:
        local_ip = "192.168.1.1"
    
    network_prefix = '.'.join(local_ip.split('.')[:-1])
    print(f"      Scanning network: {network_prefix}.0/24\n")
    
    # Step 2: Ping sweep to ensure devices are in ARP cache
    print("[2/3] Pinging network to discover devices...")
    print("      (This helps populate the ARP cache)")
    
    active_ips = set()
    
    def ping_and_check(i):
        ip = f"{network_prefix}.{i}"
        try:
            result = subprocess.run(
                ['ping', '-n', '1', '-w', '100', ip],
                capture_output=True,
                timeout=1
            )
            if result.returncode == 0:
                return ip
        except:
            pass
        return None
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(ping_and_check, range(1, 255))
        active_ips = {ip for ip in results if ip}
    
    print(f"      Found {len(active_ips)} responding devices\n")
    
    # Step 3: Get ARP table for additional IPs
    print("[3/3] Checking ARP table and resolving hostnames...")
    
    try:
        result = subprocess.run('arp -a', capture_output=True, text=True, timeout=10)
        lines = result.stdout.splitlines()
        
        for line in lines:
            if line.strip():
                parts = line.strip().split()
                for part in parts:
                    if '.' in part:
                        ip = part.strip('.:,;')
                        octets = ip.split('.')
                        if len(octets) == 4:
                            try:
                                if all(0 <= int(o) <= 255 for o in octets):
                                    active_ips.add(ip)
                            except:
                                pass
    except:
        pass
    
    print(f"      Total active IPs: {len(active_ips)}")
    print("      Now resolving hostnames...\n")
    print("-" * 70)
    
    targetmachines = []
    resolved_devices = []
    unresolved_ips = []
    
    total_ips = len(active_ips)
    current = 0
    
    for ip in sorted(active_ips):
        current += 1
        print(f"  [{current}/{total_ips}] {ip:15s} ... ", end='', flush=True)
        
        hostname, method = resolve_hostname_linux(ip)
        
        if hostname:
            # Check for 'PS' in hostname
            if case_sensitive:
                match = 'PS' in hostname
            else:
                match = 'ps' in hostname.lower()
            
            resolved_devices.append((ip, hostname, method))
            
            if match:
                print(f"✓✓✓ MATCH: {hostname:25s} (via {method})")
                targetmachines.append((hostname, ip, method))
            else:
                print(f"{hostname:25s} (via {method})")
        else:
            # Get MAC for unresolved devices
            mac = get_mac_vendor(ip)
            if mac:
                print(f"❌ No hostname (MAC: {mac})")
            else:
                print(f"❌ No hostname")
            unresolved_ips.append(ip)
    
    print("-" * 70)
    
    t2 = datetime.now()
    total = t2 - t1
    
    print(f"\nScanning completed in: {total}")
    print(f"Resolved: {len(resolved_devices)}/{total_ips} devices")
    print(f"Unresolved: {len(unresolved_ips)} devices")
    
    print("\n" + "=" * 70)
    print(f"RESULTS: Found {len(targetmachines)} machine(s) with 'PS' in name")
    print("=" * 70 + "\n")
    
    if targetmachines:
        for hostname, ip, method in targetmachines:
            print(f"  ✓ {hostname}")
            print(f"    IP: {ip}")
            print(f"    Method: {method}\n")
    else:
        print("❌ No devices with 'PS' found.\n")
        
        if unresolved_ips:
            print(f"⚠️  {len(unresolved_ips)} BeagleBone device(s) may not have DNS/mDNS configured:")
            for ip in unresolved_ips:
                mac = get_mac_vendor(ip)
                if mac:
                    print(f"    {ip:15s} (MAC: {mac})")
                else:
                    print(f"    {ip}")
            
            print("\n💡 For BeagleBone Black devices without hostnames:")
            print("    1. Check if they have hostnames configured in /etc/hostname")
            print("    2. Try accessing them directly by IP")
            print("    3. Configure mDNS/Avahi on the BeagleBones")
            print("    4. Set up DNS entries on your router")
            print("\n   If you know the IPs of your PS devices, you can access them directly!")
        
        if resolved_devices:
            print(f"\n📋 All {len(resolved_devices)} resolved devices:")
            for ip, hostname, method in resolved_devices:
                print(f"    {hostname:30s} ({ip})")
    
    return targetmachines


if __name__ == "__main__":
    machines = scan_network_for_ps_machines(case_sensitive=False)
    
    if machines:
        print(f"\n\n✅ SUCCESS! Found {len(machines)} PS machine(s):")
        for hostname, ip, method in machines:
            print(f"   • {hostname} @ {ip}")
    else:
        print("\n\n💡 TIP: BeagleBone Blacks may not broadcast hostnames.")
        print("   You may need to configure /etc/hostname or mDNS on the devices.")