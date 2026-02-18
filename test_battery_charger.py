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
        
        # Mock time.sleep to speed up tests
        self.mock_sleep_patcher = patch('time.sleep')
        self.mock_sleep = self.mock_sleep_patcher.start()

    def tearDown(self):
        self.mock_rm_patcher.stop()
        self.mock_sleep_patcher.stop()

    def test_dp832_run_headless(self):
        print("\n--- Testing DP832 Standard Run (Headless) ---")
        # Setup mock behavior
        self.mock_resource.query.side_effect = [
            "Rigol Technologies,DP832,12345,01.00", # IDN
            "12.0", # VOLT
            "0.5",  # CURR
            "12.0", "0.05" # Second iteration checking cutoff
        ]

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                charge_current=1.0, charge_voltage=12.0, cutoff_current=0.1, 
                log_file="test_dp832.csv", channel=1, model=None, 
                parallel=False, sense=False, resource_name="USB0::...",
                plot=False, config=None # Explicitly False
            )):
                with patch('matplotlib.pyplot.show') as mock_show:
                    with patch('matplotlib.animation.FuncAnimation') as mock_ani:
                         battery_charger.main()
                         
                         # In headless mode, animation/plot should NOT be called
                         mock_ani.assert_not_called()
                         mock_show.assert_not_called()

        # Verify calls
        self.mock_resource.write.assert_any_call(":APPL CH1,12.0,1.0")
        self.mock_resource.write.assert_any_call(":OUTP CH1,ON")
        
    def test_plot_enabled(self):
        print("\n--- Testing Run With Plot ---")
        self.mock_resource.query.side_effect = [
            "Rigol Technologies,DP832,12345,01.00", # IDN
        ]
        # We don't need extensive measurements, acts mainly to check if plot setup is called
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                charge_current=1.0, charge_voltage=12.0, cutoff_current=0.1, 
                log_file="test_plot.csv", channel=1, model=None, 
                parallel=False, sense=False, resource_name="USB0::...",
                plot=True, config=None
            )):
                with patch('matplotlib.pyplot.show') as mock_show:
                    with patch('matplotlib.animation.FuncAnimation') as mock_ani:
                         battery_charger.main()
                         
                         mock_ani.assert_called()
                         mock_show.assert_called()

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
                parallel=True, sense=True, resource_name="TCPIP::...",
                plot=False, config=None
            )):
                # Mock sleep needed implicitly via setUp
                battery_charger.main()

        # Verify DP2031 specific calls
        self.mock_resource.write.assert_any_call(":SYST:POW:MODE PARA")
        self.mock_resource.write.assert_any_call(":SYST:SENS CH1, ON") # Updated expectation
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

class TestConfigSupport(unittest.TestCase):
    def setUp(self):
        # We need to clean up patches because they might interfere with imports if we were importing inside tests
        pass

    def test_load_config(self):
        from battery_charger import load_config
        with patch("builtins.open", unittest.mock.mock_open(read_data="key=value\n#comment\nnum=123")) as mock_file:
            with patch("os.path.exists", return_value=True):
                config = load_config("fake.conf")
                self.assertEqual(config.get("key"), "value")
                self.assertEqual(config.get("num"), "123")
                self.assertIsNone(config.get("#comment"))

    def test_args_precedence(self):
        # Test that CLI overrides Config
        from battery_charger import main
        
        # Mock load_config to return some defaults
        config_data = {
            'charge_current': '1.0',
            'charge_voltage': '5.0',
            'cutoff_current': '0.1',
            'log_file': 'config_log.csv',
            'resource_name': 'USB::CONFIG'
        }
        
        # We need to mock sys.argv, os.path.exists (for config file check), open (for reading config), 
        # and ALL the hardware calls (RigolPSU init etc) because main() runs them.
        # Alternatively, run main() but expect it to fail safely or just check args parsing logic if we extract it?
        # Since main() is monolithic, we mock everything inside it.
        
        # Easier: Mock argparse.ArgumentParser.parse_args to return what we want? NO, we want to TEST parsing logic.
        
        # Let's mock the internal components of main:
        # 1. load_config (we can patch battery_charger.load_config)
        # 2. RigolPSU (to avoid connection)
        # 3. plt (to avoid plotting)
        
        with patch('battery_charger.load_config', return_value=config_data):
            with patch('sys.argv', ['battery_charger.py', '--config', 'test.conf', '--charge_current', '2.0']): # CLI overrides current
                with patch('battery_charger.RigolPSU') as MockPSU, \
                     patch('battery_charger.RigolDP832'), \
                     patch('battery_charger.RigolDP2031'), \
                     patch('matplotlib.pyplot.subplots', return_value=(MagicMock(), MagicMock())), \
                     patch('matplotlib.pyplot.show'), \
                     patch('matplotlib.animation.FuncAnimation'):
                     
                    # We need to verify what args were actually parsed.
                    # Since main() doesn't return args, we can spy on RigolPSU initialization or set_channel_settings
                    
                    try:
                        battery_charger.main()
                    except Exception as e:
                       self.fail(f"Main failed with: {e}") 
                    
                    # Verify calls using the CLI override value (2.0) not config (1.0)
                    # And verify usage of config value for voltage (5.0)
                    
                    # RigolPSU instantiated with resource from config?
                    # Note: code uses base_psu = RigolPSU(args.resource_name)
                    MockPSU.assert_called_with('USB::CONFIG')
                    
                    # Check method calls on the instance
                    instance = MockPSU.return_value
                    # set_channel_settings(channel, voltage, current)
                    # CLI overridden current=2.0, Config voltage=5.0
                    instance.set_channel_settings.assert_called_with(1, 5.0, 2.0)

if __name__ == '__main__':
    unittest.main()
