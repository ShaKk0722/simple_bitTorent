import configparser
import os


config_py_directory = os.path.dirname(os.path.abspath(__file__))
config_py_path = os.path.join(config_py_directory, 'config.init')

config = configparser.ConfigParser()
config.read(config_py_path)

# Get the MODE of the settings
MODE = config.get('settings', 'mode')
INFO = MODE == 'INFO'
DEBUG = MODE == 'DEBUG'
DEMO = MODE == 'DEMO'