# Tasmoticz - Domoticz Plugin for Tasmota

Python plugin for autodetecting devices with Tasmota firmware in Domoticz 

MQTT parts heavily based on Shelly_MQTT by enesbcs who was very helpful in making my Shelly 2.5 driven shutters work and inspired me for this.
Big thanks!

Tasmota devices usually have builtin domoticz support, but that is only required for manual configuration with the generic domoticz mqtt plugin and not needed for this plugin.
If anything, all you need to do is to configure the mqtt topic format you use in your Tasmota devices if you changed it from the Tasmota default setting.

## Prerequisites

Will be tested and working with Domoticz v4.x.

If you do not have a working Python >=3.5 installation, please install it first! (https://www.domoticz.com/wiki/Using_Python_plugins)

Setup and run MQTT broker, e.g. Mosquitto (https://mosquitto.org/) and an MQTT capable Tasmota device. (https://github.com/arendst/Sonoff-Tasmota/wiki)

## Installation

1. Clone repository into your domoticz plugins folder
```
cd domoticz/plugins
git clone https://github.com/joba-1/Tasmoticz.git
```
2. Restart domoticz
3. Go to "Hardware" page and add new item with type "Tasmoticz"
4. Set your MQTT server address and port to plugin settings
5. Remember to allow new devices discovery in Domoticz settings

Once plugin receives any MQTT message from Tasmota devices it will try to create an appropriate domoticz device.

## Plugin update

Warning: if you use this method, Domoticz may duplicate devices after it! Download only plugin.py if you have a lot of Tasmota devices and do not want to risk it!

1. Stop domoticz
2. Go to plugin folder and pull new version
```
cd domoticz/plugins/Tasmoticz
git pull
```
3. Start domoticz

## Supported devices

Planned to work with:
 - Relays and Switches of Tasmota devices
 - Sensors in Tasmota devices for sensors I use or YOU send pull requests
 - RGBW strips attached to Tasmota devices
 - Shutters operated by Tasmota devices once I have one or YOU send pull requests

## How To Contribute

* Open an issue if you think you discovered a bug, have a feature request or a question
    * I'll close it if  think I can't help
    * You close it if the issue is solved for you
* Open a pull request if you think you fixed a bug or implemented a new feature or need help with that
    * Fork my github repository 
    * Clone your fork
    * Implement the fix in your clone (don't change anything else)
    * Push your changes to your fork
    * Open a pull request from your fork against my repository
         * I'll merge it if I think it is useful
         * If I dont't merge it, at least others can see what you've done and use your fork if they need it

