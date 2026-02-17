import unittest
from unittest.mock import MagicMock, patch
import sys
import io
import argparse

# Mock modules before importing battery_charger
# This is necessary if the environment doesn't have them installed
mock_pyvisa = MagicMock()
class MockVisaIOError(Exception): pass
mock_pyvisa.errors.VisaIOError = MockVisaIOError
sys.modules['pyvisa'] = mock_pyvisa

sys.modules['matplotlib'] = MagicMock()
sys.modules['matplotlib.pyplot'] = MagicMock()
sys.modules['matplotlib.animation'] = MagicMock()

import battery_charger

class TestBatteryCharger(unittest.TestCase):
    def setUp(self):
        self.mock_rm_patcher = patch('pyvisa.ResourceManager')
        self.mock_rm = self.mock_rm_patcher.start()
        self.mock_resource = MagicMock()
        self.mock_rm.return_value.open_resource.return_value = self.mock_resource
        self.mock_resource.query.return_value = "Rigol Technologies,DP832,12345,01.00"
        
    def tearDown(self):
        self.mock_rm_patcher.stop()

    def test_dp832_run(self):
        print("\n--- Testing DP832 Standard Run ---")
        # Setup mock behavior
        self.mock_resource.query.side_effect = [
            "Rigol Technologies,DP832,12345,01.00", # IDN
            "12.0", # VOLT
            "0.5",  # CURR
            "12.0", "0.05" # Second iteration checking cutoff
        ]

        # Arguments
        args = [
            "--charge_current", "1.0",
            "--charge_voltage", "12.0",
            "--cutoff_current", "0.1",
            "--log_file", "test_dp832.csv",
            "--resource_name", "USB0::..."
        ]
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                charge_current=1.0, charge_voltage=12.0, cutoff_current=0.1, 
                log_file="test_dp832.csv", channel=1, model=None, 
                parallel=False, sense=False, resource_name="USB0::..."
            )):
                # We also need to mock matplotlib.pyplot.show and FuncAnimation
                with patch('matplotlib.pyplot.show'):
                    with patch('matplotlib.animation.FuncAnimation'):
                         battery_charger.main()

        # Verify calls
        self.mock_resource.write.assert_any_call(":APPL CH1,12.0,1.0")
        self.mock_resource.write.assert_any_call(":OUTP CH1,ON")
        
    def test_dp2031_parallel_sense(self):
        print("\n--- Testing DP2031 Parallel + Sense Run ---")
        self.mock_resource.query.side_effect = [
            "Rigol Technologies,DP2031,54321,01.00", # IDN
            "5.0", # VOLT CH1
            "2.0", # CURR PAR
            "5.0", # VOLT CH1 2nd call
            "0.05" # CURR PAR 2nd call
        ]

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
             with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                charge_current=2.0, charge_voltage=5.0, cutoff_current=0.1, 
                log_file="test_dp2031.csv", channel=1, model="DP2031", 
                parallel=True, sense=True, resource_name="TCPIP::..."
            )):
                with patch('matplotlib.pyplot.show'):
                    with patch('matplotlib.animation.FuncAnimation'):
                         battery_charger.main()

        # Verify DP2031 specific calls
        self.mock_resource.write.assert_any_call(":SYST:POW:MODE PARA")
        self.mock_resource.write.assert_any_call(":OUTP1:SENS ON")
        self.mock_resource.write.assert_any_call(":APPL CH1,5.0,2.0")
        self.mock_resource.write.assert_any_call(":OUTP CH1,ON")

class TestUniqueFilename(unittest.TestCase):
    def test_unique_filename(self):
        # We need to test the logic without actually touching the filesystem if possible,
        # but os.path.exists is hardcoded. We can patch os.path.exists.
        
        from battery_charger import get_unique_filename
        
        # Case 1: File does not exist
        with patch('os.path.exists', return_value=False):
            self.assertEqual(get_unique_filename("log.csv"), "log.csv")
            
        # Case 2: File exists, no number -> append 1
        # mocked exists returns True for log.csv, False for log1.csv
        with patch('os.path.exists', side_effect=lambda p: p == "log.csv"):
            self.assertEqual(get_unique_filename("log.csv"), "log1.csv")

        # Case 3: File exists, ends in number -> increment
        # log2.csv exists, should become log3.csv
        with patch('os.path.exists', side_effect=lambda p: p == "log2.csv"):
            self.assertEqual(get_unique_filename("log2.csv"), "log3.csv")
            
        # Case 4: log2.csv and log3.csv exist -> log4.csv
        with patch('os.path.exists', side_effect=lambda p: p in ["log2.csv", "log3.csv"]):
            self.assertEqual(get_unique_filename("log2.csv"), "log4.csv")

if __name__ == '__main__':
    unittest.main()
