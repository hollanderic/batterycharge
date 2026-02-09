#!/usr/bin/env python3

import argparse
import time
import pyvisa
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import datetime

class RigolDP832:
    def __init__(self, resource_name):
        self.rm = pyvisa.ResourceManager()
        self.instrument = self.rm.open_resource(resource_name)
        self.instrument.read_termination = '\n'
        self.instrument.write_termination = '\n'
        print(f"Connected to {self.instrument.query('*IDN?')}")

    def set_channel_settings(self, channel, voltage, current):
        self.instrument.write(f":APPL CH{channel},{voltage},{current}")

    def get_measurements(self, channel):
        voltage = float(self.instrument.query(f":MEAS:VOLT? CH{channel}"))
        current = float(self.instrument.query(f":MEAS:CURR? CH{channel}"))
        return voltage, current

    def set_output(self, channel, state):
        self.instrument.write(f":OUTP CH{channel},{'ON' if state else 'OFF'}")

    def close(self):
        self.instrument.close()

def main():
    parser = argparse.ArgumentParser(description="Battery charger for Rigol DP832")
    parser.add_argument("--charge_current", type=float, required=True, help="Charge current in Amps")
    parser.add_argument("--charge_voltage", type=float, required=True, help="Charge voltage in Volts")
    parser.add_argument("--cutoff_current", type=float, required=True, help="Cutoff current in Amps")
    parser.add_argument("--log_file", type=str, required=True, help="Log file name")
    parser.add_argument("--channel", type=int, default=1, choices=[1, 2, 3], help="Power supply channel")
    parser.add_argument("--resource_name", type=str, required=True, 
                        help="VISA resource name for the instrument. "
                             "For TCP/IP, use format 'TCPIP0::IP_ADDRESS::INSTR' (e.g., 'TCPIP0::192.168.1.1::INSTR'). "
                             "For USB, use format 'USB0::VendorID::ProductID::SerialNumber::INSTR' (e.g., 'USB0::0x1AB1::0x0E11::DP8C123456789::INSTR'). "
                             "Use `pyvisa-info` in your terminal to find available resources.")
    args = parser.parse_args()

    psu = None
    try:
        psu = RigolDP832(args.resource_name)
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
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)

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

            if current < args.cutoff_current:
                print(f"Charging complete. Cutoff current {args.cutoff_current}A reached.")
                if ani:
                    ani.event_source.stop()

            return line,

        ani = FuncAnimation(fig, update, blit=True, interval=1000)
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
