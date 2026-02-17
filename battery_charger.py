#!/usr/bin/env python3

import argparse
import time
import pyvisa
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import datetime
import os
import re

def get_unique_filename(filepath):
    """
    Returns a unique filename. If the file already exists:
    - If it ends in a number (e.g., 'log1.csv'), increments the number (e.g., 'log2.csv').
    - If it doesn't end in a number, appends '1' (e.g., 'log.csv' -> 'log1.csv').
    """
    if not os.path.exists(filepath):
        return filepath

    directory, filename = os.path.split(filepath)
    basename, extension = os.path.splitext(filename)

    while os.path.exists(filepath):
        # Check if basename ends with a number
        match = re.search(r'(\d+)$', basename)
        if match:
            number = int(match.group(1))
            prefix = basename[:match.start()]
            new_number = number + 1
            basename = f"{prefix}{new_number}"
        else:
            basename = f"{basename}1"
        
        filepath = os.path.join(directory, basename + extension)
    
    return filepath

def load_config(config_path):
    """
    Parses a simple key=value config file.
    Lines starting with # are comments.
    """
    config = {}
    if not os.path.exists(config_path):
        print(f"Warning: Configuration file not found: {config_path}")
        return config

    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key:
                        config[key] = value
    except Exception as e:
        print(f"Error reading configuration file: {e}")
    return config

class RigolPSU:
    def __init__(self, resource_name):
        self.rm = pyvisa.ResourceManager()
        try:
            self.instrument = self.rm.open_resource(resource_name)
            self.instrument.read_termination = '\n'
            self.instrument.write_termination = '\n'
            self.idn = self.instrument.query('*IDN?')
            print(f"Connected to {self.idn.strip()}")
        except Exception as e:
            print(f"Failed to connect to {resource_name}: {e}")
            raise

    def set_channel_settings(self, channel, voltage, current):
        self.instrument.write(f":APPL CH{channel},{voltage},{current}")

    def get_measurements(self, channel):
        voltage = float(self.instrument.query(f":MEAS:VOLT? CH{channel}"))
        current = float(self.instrument.query(f":MEAS:CURR? CH{channel}"))
        return voltage, current

    def set_output(self, channel, state):
        self.instrument.write(f":OUTP CH{channel},{'ON' if state else 'OFF'}")

    def close(self):
        if hasattr(self, 'instrument'):
            self.instrument.close()


class RigolDP832(RigolPSU):
    pass


class RigolDP2031(RigolPSU):
    def enable_parallel_mode(self):
        print("Enabling Parallel Mode...")
        # Configure the instrument for parallel operation
        self.instrument.write(":SYST:POW:MODE PARA")
        self.is_parallel = True

    def enable_sense_mode(self, channel, state):
        print(f"{'Enabling' if state else 'Disabling'} Voltage Sense for CH{channel}...")
        # DP2000 series uses :OUTPut<n>:SENSe <bool>
        self.instrument.write(f":OUTP{channel}:SENS {'ON' if state else 'OFF'}")

    def get_measurements(self, channel):
        if getattr(self, 'is_parallel', False):
            # In parallel mode, measure voltage on the specific channel (or PAR),
            # but current must be measured via PAR to get the total current (sum of channels).
            # User specifically requested using PAR for current.
            voltage = float(self.instrument.query(f":MEAS:VOLT? CH{channel}"))
            current = float(self.instrument.query(f":MEAS:CURR? PAR"))
            return voltage, current
        else:
            return super().get_measurements(channel)


def main():
    # First pass: Check for config file argument only
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=str, help="Path to configuration file (.conf)")
    # Parse known args to find --config, ignore the rest for now
    pre_args, _ = pre_parser.parse_known_args()

    # Load config defaults if specified
    defaults = {}
    if pre_args.config:
        defaults = load_config(pre_args.config)

    # Main parser
    parser = argparse.ArgumentParser(description="Battery charger for Rigol DP832 / DP2031")
    
    # Helper to retrieve default value from config or None
    def get_default(key, cast_type=str):
        val = defaults.get(key)
        if val is not None:
            try:
                # Handle booleans specifically if needed, though 'store_true' usually implies False default
                if cast_type == bool:
                    return val.lower() in ('true', 'yes', '1', 'on')
                return cast_type(val)
            except ValueError:
                return None
        return None

    # Config argument (re-added to show in help)
    parser.add_argument("--config", type=str, help="Path to configuration file (.conf)")

    # Define arguments. essential: remove required=True, set default from config
    parser.add_argument("--charge_current", type=float, default=get_default('charge_current', float),
                        help="Charge current in Amps")
    parser.add_argument("--charge_voltage", type=float, default=get_default('charge_voltage', float),
                        help="Charge voltage in Volts")
    parser.add_argument("--cutoff_current", type=float, default=get_default('cutoff_current', float),
                        help="Cutoff current in Amps")
    parser.add_argument("--log_file", type=str, default=get_default('log_file', str),
                        help="Log file name")
    
    # Optional args, check config for defaults too
    parser.add_argument("--channel", type=int, default=get_default('channel', int) or 1, choices=[1, 2, 3], 
                        help="Power supply channel")
    parser.add_argument("--model", type=str, choices=['DP832', 'DP2031'], default=get_default('model', str),
                        help="Explicitly specify model (optional, will try auto-detect)")
    parser.add_argument("--parallel", action='store_true', default=get_default('parallel', bool),
                        help="Enable parallel channel mode (DP2031 only)")
    parser.add_argument("--sense", action='store_true', default=get_default('sense', bool),
                        help="Enable voltage sense (DP2031 only)")
    parser.add_argument("--resource_name", type=str, default=get_default('resource_name', str),
                        help="VISA resource name for the instrument.")

    args = parser.parse_args()

    # Manual validation for required arguments that might be missing from both CLI and Config
    required_args = ['charge_current', 'charge_voltage', 'cutoff_current', 'log_file', 'resource_name']
    missing = [arg for arg in required_args if getattr(args, arg) is None]
    
    if missing:
        parser.error(f"The following arguments are required (specify via CLI or Config): {', '.join(missing)}")

    # Ensure unique log filename
    args.log_file = get_unique_filename(args.log_file)
    print(f"Logging to: {args.log_file}")

    psu = None
    try:
        # Connect generically first to check IDN if model not specified
        base_psu = RigolPSU(args.resource_name)
        idn = base_psu.idn
        
        model = args.model
        if not model:
            if "DP832" in idn:
                model = "DP832"
            elif "DP2031" in idn:
                model = "DP2031"
            else:
                print(f"Warning: Could not auto-detect known model from IDN: {idn}. Defaulting to DP832 behavior.")
                model = "DP832"
        
        # We can reuse the base_psu connection by "upgrading" the class instance or just re-instantiating.
        # Re-instantiating is safer for clean init, but we'd need to close the first one.
        # However, since RigolPSU __init__ opens the resource, we can just cast the class or wrap it.
        # Simpler approach: Close base_psu and open the specific one, or just assume the methods work if we stick to one instance
        # but since we want specific methods like enable_parallel_mode on the specific class, let's use the specific class.
        # Actually, let's just make the 'psu' variable be the specific class instance.
        
        # To avoid re-opening which might fail or be slow, let's just dynamic cast?
        # Pythonic way: change __class__
        if model == "DP2031":
            base_psu.__class__ = RigolDP2031
            psu = base_psu
        else:
            base_psu.__class__ = RigolDP832
            psu = base_psu

        print(f"Operating as {model}")

        if args.parallel:
            if isinstance(psu, RigolDP2031):
                psu.enable_parallel_mode()
                # In parallel mode, we usually control via CH1?
                # If args.channel is not 1, warn user?
                if args.channel != 1:
                    print("Warning: Parallel mode usually combines CH1+CH2 and is controlled via CH1. Forcing channel to 1.")
                    args.channel = 1
            else:
                print("Warning: Parallel mode is only supported (in this script) for DP2031. Ignoring --parallel.")

        if args.sense:
            if isinstance(psu, RigolDP2031):
                psu.enable_sense_mode(args.channel, True)
            else:
                print("Warning: Sense mode is only supported (in this script) for DP2031. Ignoring --sense.")

        psu.set_channel_settings(args.channel, args.charge_voltage, args.charge_current)
        psu.set_output(args.channel, True)

        start_time = time.time()
        last_time = start_time
        time_values = []
        voltage_values = []
        ah_charge = 0
        wh_charge = 0

        plt.style.use('dark_background')
        fig, ax = plt.subplots()
        line, = ax.plot([], [], 'c-', label='Voltage')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Voltage (V)')
        ax.set_title('Battery Charging Voltage')
        ax.legend()
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)

        with open(args.log_file, 'w') as f:
            f.write("Timestamp,Elapsed Time (s),Voltage (V),Current (A),Amp-hours (Ah),Watt-hours (Wh)\n")

        ani = None
        def update(frame):
            nonlocal ah_charge, wh_charge, last_time
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            try:
                voltage, current = psu.get_measurements(args.channel)
            except pyvisa.errors.VisaIOError as e:
                print(f"Error reading from instrument: {e}")
                # Stop the animation if we can't read from the instrument
                if ani:
                    ani.event_source.stop()
                return line,

            time_delta = current_time - last_time
            last_time = current_time
            time_delta_hours = time_delta / 3600
            ah_charge += current * time_delta_hours
            wh_charge += voltage * current * time_delta_hours

            time_values.append(elapsed_time)
            voltage_values.append(voltage)
            
            timestamp = datetime.datetime.now().isoformat()
            with open(args.log_file, 'a') as f:
                f.write(f"{timestamp},{elapsed_time:.2f},{voltage:.4f},{current:.4f},{ah_charge:.4f},{wh_charge:.4f}\n")

            print(f"Time: {elapsed_time:.1f}s, Voltage: {voltage:.2f}V, Current: {current:.2f}A")

            line.set_data(time_values, voltage_values)
            ax.relim()
            ax.autoscale_view()
            
            # Explicitly force update of limits if auto-scaling isn't aggressive enough
            # But with blit=False, relim + autoscale_view should work.
            # Let's ensure y-axis also scales if voltage changes significantly.
            
            if current < args.cutoff_current:
                print(f"Charging complete. Cutoff current {args.cutoff_current}A reached.")
                if ani:
                    ani.event_source.stop()

            return line,

        ani = FuncAnimation(fig, update, interval=1000) # blit=False is default, allows axes to resize
        plt.show()

    except pyvisa.errors.VisaIOError as e:
        print(f"Error connecting to instrument: {e}")
        print("Please check the resource name and connection.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if psu:
            print("Turning off channel and closing connection.")
            psu.set_output(args.channel, False)
            psu.close()
        print("Charger script finished.")


if __name__ == "__main__":
    main()
