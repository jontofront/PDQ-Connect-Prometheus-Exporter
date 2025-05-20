import time
import requests
from prometheus_client import start_http_server, Gauge
from collections import defaultdict

# Constants
API_KEY = 'redacted'  # Replace with your actual API key
BASE_URL = 'https://app.pdq.com/v1/api'

# Prometheus metrics definitions (HARDWARE)
device_count = Gauge('pdq_device_count', 'Total number of devices managed by PDQ Connect')
device_info = Gauge('pdq_device_info', 'Basic information about the device', [
    'hostname', 'architecture', 'id', 'insertedAt', 'lastUser',
    'model', 'name', 'osVersion', 'publicIpAddress', 'serialNumber', 'servicePack'
])
disk_info = Gauge('pdq_disk_info', 'Information about the device disks', [
    'hostname', 'disk_id', 'model', 'mediaType', 'totalSpaceKb'
])
driver_info = Gauge('pdq_driver_info', 'Information about the device drivers', [
    'hostname', 'driver_id', 'name', 'version', 'provider'
])
ad_info = Gauge('pdq_ad_info', 'Active Directory information about the device', [
    'hostname', 'deviceName'
])
custom_fields_info = Gauge('pdq_custom_fields_info', 'Custom fields information about the device', [
    'hostname', 'field_name', 'field_value'
])

# ===================== ADDED: SOFTWARE METRICS DEFINITIONS =====================
software_total = Gauge('pdq_software_total', 'Total installs per software', ['software'])
software_updated = Gauge('pdq_software_updated', 'Updated installs (latest version) per software', ['software'])
software_updated_percent = Gauge('pdq_software_updated_percent', 'Percentage of installs updated to latest version', ['software'])
software_latest_version = Gauge('pdq_software_latest_version', 'Latest version per software', ['software', 'latest_version'])
software_version_count = Gauge('pdq_software_version_count', 'Install count per software version', ['software', 'version'])
# ================================================================================
# Function to get devices from PDQ Connect API
def get_devices():
    url = f'{BASE_URL}/devices'
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json"
    }
    devices = []
    page = 1
    while True:
        params = {
            # Includes all inventory + SOFTWARE for software metrics!
            "includes": "disks,drivers,features,networking,processors,updates,software,activeDirectory,activeDirectoryGroups,customFields",
            "pageSize": 100,
            "page": page,
            "sort": "insertedAt"
        }
        print(f"Fetching devices from {url} with params {params}")
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
    print(f"Total devices fetched: {len(devices)}")
    return devices

# Function to collect and update Prometheus metrics for devices (hardware)
def collect_device_metrics(devices):
    device_count.set(len(devices))
    print(f"Updating metrics for {len(devices)} devices")
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

        # Update device info metric
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

        # Update disk info metrics
        for disk in device.get('disks', []):
            disk_info.labels(
                hostname=hostname,
                disk_id=disk.get('id', 'unknown'),
                model=disk.get('model', 'unknown'),
                mediaType=disk.get('mediaType', 'unknown'),
                totalSpaceKb=disk.get('totalSpaceKb', 0)
            ).set(1)

        # Update driver info metrics
        for driver in device.get('drivers', []):
            driver_info.labels(
                hostname=hostname,
                driver_id=driver.get('id', 'unknown'),
                name=driver.get('name', 'unknown'),
                version=driver.get('version', 'unknown'),
                provider=driver.get('provider', 'unknown')
            ).set(1)

        # Update Active Directory info metric
        active_directory = device.get('activeDirectory', {})
        if active_directory:
            ad_info.labels(
                hostname=hostname,
                deviceName=active_directory.get('deviceName', 'unknown')
            ).set(1)

        # Update custom fields metrics
        for field in device.get('customFields', []):
            custom_fields_info.labels(
                hostname=hostname,
                field_name=field.get('name', 'unknown'),
                field_value=field.get('value', 'unknown')
            ).set(1)

        # print(f"Metrics updated for device: {hostname}")

# ===================== ADDED: SOFTWARE METRICS AGGREGATION =====================
def collect_software_metrics(devices):
    """
    Aggregates software statistics across all devices and exposes them as Prometheus metrics.
    """
    sw_stats = defaultdict(lambda: defaultdict(int))
    for device in devices:
        for sw in device.get('software', []):
            name = sw.get('name')
            version = sw.get('versionRaw')
            if name and version:
                sw_stats[name][version] += 1

    for sw, versions in sw_stats.items():
        total = sum(versions.values())
        # Find latest version (string-aware)
        try:
            latest = max(versions.keys(), key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('.', ' ').split()])
        except Exception:
            latest = max(versions.keys())
        updated = versions[latest]
        percent = updated / total * 100 if total > 0 else 0

        # Prometheus metrics
        software_total.labels(software=sw).set(total)
        software_updated.labels(software=sw).set(updated)
        software_updated_percent.labels(software=sw).set(percent)
        software_latest_version.labels(software=sw, latest_version=latest).set(1)
        for ver, count in versions.items():
            software_version_count.labels(software=sw, version=ver).set(count)
# ===============================================================================

if __name__ == '__main__':
    print("Starting Prometheus exporter")
    # Start up the server to expose the metrics.
    start_http_server(8000)
    print("Prometheus exporter started on port 8000")
    # ================== CHANGED: DATA SYNC INTERVAL SET TO 1 DAY ==============
    sync_interval = 60 * 60 * 24   # 24 hours (in seconds)
    # ==========================================================================
    while True:
        try:
            print("Collecting metrics...")
            devices = get_devices()
            collect_device_metrics(devices)      # Hardware inventory metrics
            collect_software_metrics(devices)    # Software version metrics   # >>> ADDED LINE
            print("Metrics collected successfully")
        except Exception as e:
            print(f"Error collecting metrics: {e}")
        time.sleep(sync_interval)
