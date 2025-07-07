import os
import re
import shutil
import subprocess

import psutil


def get_ram_usage():
    return psutil.virtual_memory().percent


def get_swap_usage():
    return psutil.swap_memory().percent


def get_cpu_usage():
    return psutil.cpu_percent(interval=1)


def get_cpu_frequency():
    freq = psutil.cpu_freq()
    return freq.current if freq else None


def get_system_load():
    if hasattr(os, "getloadavg"):
        return os.getloadavg()  # returns (1min, 5min, 15min)
    return None


def get_temperatures():
    temps = {}
    try:
        output = subprocess.check_output("sensors", universal_newlines=True)
        current_chip = None
        for line in output.splitlines():
            line = line.strip()
            if not line:
                current_chip = None
                continue
            if ":" not in line and not line.startswith(" "):
                current_chip = line
                continue

            match = re.search(r"([+\-]?\d+\.\d+)°C", line)
            if match:
                temp_value = float(match.group(1))
                key_match = re.match(r"^([\w\s\.\-]+):", line)
                key = key_match.group(1).strip() if key_match else "temp"
                label = f"{current_chip} {key}" if current_chip else key
                temps[label] = temp_value
    except Exception as e:
        temps["error"] = str(e)
    return temps


def get_gpu_info():
    if shutil.which("nvidia-smi") is None:
        return None

    try:
        query_fields = [
            "utilization.gpu",
            "temperature.gpu",
            "memory.used",
            "memory.total",
            "power.draw",
        ]
        output = subprocess.check_output(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(query_fields)}",
                "--format=csv,noheader,nounits",
            ],
            universal_newlines=True,
        )

        gpu_data = []
        for line in output.strip().splitlines():
            values = line.strip().split(", ")
            gpu_info = {}
            for field, val in zip(query_fields, values):
                try:
                    gpu_info[field] = float(val) if val != "[N/A]" else None
                except ValueError:
                    gpu_info[field] = None
            gpu_data.append(gpu_info)
        return gpu_data
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print("RAM Usage (%):", get_ram_usage())
    print("SWAP Usage (%):", get_swap_usage())
    print("CPU Usage (%):", get_cpu_usage())
    print("CPU Frequency (MHz):", get_cpu_frequency())
    print("System Load (1m, 5m, 15m):", get_system_load())
    print("\nTemperatures (°C):")
    temps = get_temperatures()
    for name, temp in temps.items():
        print(f"  {name}: {temp}")

    print("\nGPU Info:")
    gpu = get_gpu_info()
    if gpu is None:
        print("  No NVIDIA GPU or nvidia-smi not found.")
    elif isinstance(gpu, dict) and "error" in gpu:
        print("  Error:", gpu["error"])
    else:
        for i, g in enumerate(gpu):
            print(f"  GPU {i}:")
            for k, v in g.items():
                print(f"    {k}: {v}")
