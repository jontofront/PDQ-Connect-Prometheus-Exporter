import time
import requests
from prometheus_client import start_http_server, Gauge
from collections import defaultdict

# ==================== CONFIGURATION ====================
API_KEY = 'redacted'  # <-- Put your real PDQ API key here!
BASE_URL = 'https://app.pdq.com/v1/api'
PORT = 8000
SYNC_INTERVAL = 60 * 60 * 24  # Synchronize only once per day (24 hours)
# =======================================================

# ----------- HARDWARE METRICS DEFINITIONS --------------
device_count = Gauge('pdq_device_count', 'Total number of devices managed by PDQ Connect')
device_info = Gauge('pdq_device_info', 'Basic information about the device', [
    'hostname', 'architecture', 'id', 'insertedAt', 'lastUser',
    'model', 'name', 'osVersion', 'publicIpAddress', 'serialNumber', 'servicePack'
])
# Add more hardware metrics here if needed
# -------------------------------------------------------

# ----------- SOFTWARE METRICS DEFINITIONS --------------
software_total = Gauge('pdq_software_total', 'Total installs per software', ['software'])
software_updated = Gauge('pdq_software_updated', 'Updated installs (latest version) per software', ['software'])
software_updated_percent = Gauge('pdq_software_updated_percent', 'Percentage of installs updated to latest version', ['software'])
software_latest_version = Gauge('pdq_software_latest_version', 'Latest version per software', ['software', 'latest_version'])
software_version_count = Gauge('pdq_software_version_count', 'Install count per software version', ['software', 'version'])
# -------------------------------------------------------

def get_devices():
    """
    Retrieves all devices from the PDQ Connect API, including installed software.
    Returns a list of device dictionaries.
    """
    devices = []
    page = 1
    while True:
        params = {
            "includes": "software,disks,drivers,features,networking,processors,updates,activeDirectory,activeDirectoryGroups,customFields",
            "pageSize": 100,
            "page": page,
            "sort": "insertedAt"
        }
        url = f'{BASE_URL}/devices'
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "accept": "application/json"
        }
        print(f"Fetching page {page} from {url}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        batch = data.get("data", [])
        if not batch:
            break
        devices.extend(batch)
        if len(batch) < params["pageSize"]:
            break
        page += 1
    print(f"Fetched {len(devices)} devices.")
    return devices

def collect_device_metrics(devices):
    """
    Updates Prometheus hardware metrics for each device.
    Only basic info here for demonstration (extend as needed).
    """
    device_count.set(len(devices))
    print(f"Updating device metrics for {len(devices)} devices.")
    for device in devices:
        hostname = device.get('hostname', 'unknown')
        architecture = device.get('architecture', 'unknown')
        device_id = device.get('id', 'unknown')
        inserted_at = device.get('insertedAt', 'unknown')
        last_user = device.get('lastUser', 'unknown')
        model = device.get('model', 'unknown')
        name = device.get('name', 'unknown')
        os_version = device.get('osVersion', 'unknown')
        public_ip_address = device.get('publicIpAddress', 'unknown')
        serial_number = device.get('serialNumber', 'unknown')
        service_pack = device.get('servicePack', 'unknown')

        # Expose device info with labels
        device_info.labels(
            hostname=hostname,
            architecture=architecture,
            id=device_id,
            insertedAt=inserted_at,
            lastUser=last_user,
            model=model,
            name=name,
            osVersion=os_version,
            publicIpAddress=public_ip_address,
            serialNumber=serial_number,
            servicePack=service_pack
        ).set(1)

def collect_software_metrics(devices):
    """
    Aggregates software statistics across all devices
    and exposes them as Prometheus metrics.
    - Counts total installs per software
    - Counts updated (latest version) installs
    - Calculates percent updated
    - Tracks all version spreads per software
    """
    print("Updating software metrics...")
    sw_stats = defaultdict(lambda: defaultdict(int))
    for device in devices:
        for sw in device.get('software', []):
            name = sw.get('name')
            version = sw.get('versionRaw')
            if name and version:
                sw_stats[name][version] += 1

    for sw, versions in sw_stats.items():
        total = sum(versions.values())
        # Determine latest version (natural order, even if string)
        try:
            latest = max(versions.keys(), key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('.', ' ').split()])
        except Exception:
            latest = max(versions.keys())
        updated = versions[latest]
        percent = updated / total * 100 if total > 0 else 0

        # Update Prometheus metrics for software
        software_total.labels(software=sw).set(total)
        software_updated.labels(software=sw).set(updated)
        software_updated_percent.labels(software=sw).set(percent)
        software_latest_version.labels(software=sw, latest_version=latest).set(1)
        for ver, count in versions.items():
            software_version_count.labels(software=sw, version=ver).set(count)

if __name__ == '__main__':
    print(f"Starting Prometheus exporter on port {PORT}")
    # Start up HTTP server to expose Prometheus metrics endpoint
    start_http_server(PORT)
    while True:
        try:
            print("Collecting metrics from PDQ Connect API...")
            devices = get_devices()
            collect_device_metrics(devices)
            collect_software_metrics(devices)
            print("Metrics updated successfully.")
        except Exception as e:
            print(f"Error during metrics update: {e}")
        # Wait 24 hours before the next sync
        print(f"Waiting {SYNC_INTERVAL // 3600} hours for next sync...\n")
        time.sleep(SYNC_INTERVAL)
