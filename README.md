# Rigol DP832 / DP2031 Battery Charger Script

This Python script facilitates charging a battery using a Rigol DP832 or DP2031 programmable DC power supply. It allows users to set charging parameters, logs critical charging data, and provides real-time visualization of the battery voltage.

## Features

- **Configurable Charging:** Set desired charge current, charge voltage, and a cutoff current via command-line arguments.
- **Data Logging:** Records timestamp, elapsed time, measured voltage, measured current, cumulative Amp-hours (Ah), and cumulative Watt-hours (Wh) to a specified CSV file.
- **Real-time Voltage Plotting:** Displays a live graph of the battery voltage during charging with a dark, oscilloscope-like theme.
- **Automatic Cutoff:** Automatically stops the charging process when the measured current drops below the defined cutoff current.
- **Parallel Mode (DP2031):** Supports high-current charging by enabling parallel mode on the DP2031.
- **Voltage Sense (DP2031):** Supports remote voltage sensing for accurate voltage delivery at the load.
- **Unique Log Files:** Automatically increments log filenames (e.g., `log1.csv`) if the specified file already exists.
- **Console Output:** Echoes current voltage, current, and elapsed time to the console once per second.

## Requirements

- Python 3.x
- `pyvisa`: Python module for VISA (Virtual Instrument Software Architecture)
- `matplotlib`: Python plotting library
- A Rigol DP832 or DP2031 series programmable DC power supply
- A VISA backend installed (e.g., NI-VISA, PyVISA-py, Keysight VISA) for `pyvisa` to communicate with the instrument.

## Installation

1.  **Install Python (if not already installed):**
    Download from [python.org](https://www.python.org/).

2.  **Install VISA Backend:**
    Install a VISA runtime for your operating system. Popular choices include:
    *   **NI-VISA:** [National Instruments](https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html)
    *   **Keysight VISA:** [Keysight Technologies](https://www.keysight.com/us/en/lib/software-detail/instrument-control-software/io-libraries-suite.html)
    *   **PyVISA-py (backend for PyVISA):** A pure Python VISA backend, useful if you don't want to install proprietary drivers. Install with `pip install pyvisa-py`.

3.  **Install Python Libraries:**
    ```bash
    pip install pyvisa matplotlib
    ```

## Usage

Run the script from your terminal, providing the necessary arguments:

```bash
python battery_charger.py 
    --charge_current 1.0 
    --charge_voltage 4.2 
    --cutoff_current 0.05 
    --log_file battery_charge_log.csv 
    --channel 1 
    --resource_name "TCPIP0::192.168.1.1::INSTR"
```

For **DP2031** with parallel mode and sense enabled:

```bash
python battery_charger.py 
    --charge_current 5.0 
    --charge_voltage 12.0 
    --cutoff_current 0.1 
    --log_file charge_log.csv 
    --model DP2031
    --parallel
    --sense
```bash
python battery_charger.py --config my_charge_profile.conf
```

Or combine config with overrides:

```bash
python battery_charger.py --config my_charge_profile.conf --charge_current 2.0
```

### Configuration File Format (.conf)
A simple key=value text file:

```ini
# Charging Li-ion cell
charge_current = 1.0
charge_voltage = 4.2
cutoff_current = 0.05
log_file = my_log.csv
resource_name = USB0::0x1AB1::...
```

### Command-line Arguments:

-   `--config <str>` (Optional): Path to a configuration file containing default values.
-   `--charge_current <float>` (Required if not in config): The maximum current (in Amps) the power supply will provide during charging.
-   `--charge_voltage <float>` (Required if not in config): The target voltage (in Volts) the power supply will maintain.
-   `--cutoff_current <float>` (Required if not in config): The current (in Amps) at which the charging process should terminate.
-   `--log_file <str>` (Required if not in config): The path and filename for the CSV file.
-   `--channel <int>` (Optional, default: `1`): The output channel.
-   `--resource_name <str>` (Required if not in config): The VISA resource name.
    -   **For TCP/IP (Ethernet):** Use a format like `TCPIP0::IP_ADDRESS::INSTR`.
    -   **For USB:** Use a format like `USB0::VendorID::ProductID::SerialNumber::INSTR`.
-   `--model <str>` (Optional): Explicitly specify the model (`DP832` or `DP2031`). If not provided, the script attempts to auto-detect via `*IDN?`.
-   `--parallel` (Optional, flag): Enable parallel mode (DP2031 only). Combines channels for higher current.
-   `--sense` (Optional, flag): Enable voltage sense (DP2031 only). Compensates for voltage drop in cables.
-   `--plot` (Optional, flag): Enable real-time voltage plot. If omitted, the script runs in headless mode (text output only).

## Log File Format

The generated CSV log file (`battery_charge_log.csv` in the example) will have the following columns:

-   `Timestamp`: ISO format timestamp of the measurement.
-   `Elapsed Time (s)`: Time in seconds since the script started.
-   `Voltage (V)`: Measured battery voltage in Volts.
-   `Current (A)`: Measured charging current in Amps.
-   `Amp-hours (Ah)`: Cumulative Amp-hours delivered to the battery.
-   `Watt-hours (Wh)`: Cumulative Watt-hours delivered to the battery.

## Troubleshooting

-   **`pyvisa.errors.VisaIOError`:** This usually means the script couldn't connect to your instrument.
    -   Ensure your Rigol DP832 is powered on and connected (via USB or Ethernet).
    -   Verify the `resource_name` argument is correct. Use `pyvisa-info` in your terminal to find the exact resource string for your device.
    -   Confirm that your VISA backend is correctly installed and configured.
    -   For TCP/IP connections, ensure there's no firewall blocking the connection and the IP address is correct.
