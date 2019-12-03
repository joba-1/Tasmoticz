# Tasmoticz

## Autodiscovery of Tasmota Devices for Domoticz

Python plugin for autodetecting ESP8266 devices with [Tasmota firmware](https://github.com/arendst/Tasmota) in [Domoticz Homeautomation](https://www.domoticz.com/).

* Tasmotas native and manually configured domoticz support is not required, but can be used in parallel if you leave it compiled in for things I didn't implement yet (I use this).
* Tasmotas native homeassistant support or [Setoption19](https://github.com/arendst/Sonoff-Tasmota/wiki/Commands#setoption19) is not required, but probably can be used in parallel with [emontnemery's plugin](https://github.com/emontnemery/domoticz_mqtt_discovery "emontnemery's github repo") if you leave it compiled in (not tested)
* Domoticzs native MQTT plugin is not required
* No cloud required :)

MQTT parts are heavily based on [Shelly_MQTT by enesbcs](https://github.com/enesbcs/Shelly_MQTT "enesbcs's github repo") who was very helpful in making my Shelly 2.5 driven shutters work and inspired me for this.
Big thanks!

Tasmota devices usually have builtin domoticz and home assistant support. If you want or need to save space, ram or cpu cycles you can remove that from the tasmota firmware.

## Prerequisites

Will be tested and working with Domoticz v4.x.

If you do not have a working Python >=3.5 installation, please install it first! [Documented by Domoticz](https://www.domoticz.com/wiki/Using_Python_plugins)

Setup and run MQTT broker, e.g. [Mosquitto](https://mosquitto.org/) and an MQTT capable [Tasmota device](https://github.com/arendst/Tasmota/wiki).

## Installation

1. Clone this repository into your domoticz plugins folder (or just put the *.py files in a Tasmoticz folder there) 
```
cd domoticz/plugins
git clone https://github.com/joba-1/Tasmoticz.git
```
2. Restart domoticz
3. Go to "Hardware" page and add new item with type "Autodiscovery of Tasmota Devices" and activate it
4. Make sure your devices have unique mqtt topics and can talk to the broker. The default topic 'sonoff' is ignored by this plugin so unconfigured devices are not picked up

If you use an mqtt broker on the same host with standard port and standard tasmota firmware with standard configuration (with or without home assistant autodetection), that should be enough. 

## Optional Configuration

1. Set your MQTT broker name or ip address and port in the plugin settings if they differ from the default
2. Set patterns of full topics of your tasmota devices that should be picked up if they are not standard
3. Set the friendly name of your tasmota device. It will be picked up and used as device name in domoticz if you have left the generated name untouched. The standard friendly name 'Sonoff' will be ignored. 

Once the plugin receives any MQTT status message from Tasmota devices it will try to create an appropriate domoticz device.

## Plugin update

1. Stop domoticz
2. Go to plugin folder and pull new version
```
cd domoticz/plugins/Tasmoticz
git pull
```
3. Start domoticz

## Supported devices and sensors

- Relays of Tasmota devices (POWER*)
- Sensors in Tasmota devices for sensors I use (adding more should be easy)
    - DHT11 (nostalgia, not recommended because inaccurate)
    - AM2301
    - ENERGY
    - TSL2561
    - VL53L0X
    - BMP280/BME280
    - SI7021 (by Eddie-BS)
    - all other sensors using the data types (temperature, humidity, ...) of above sensors (by Hello1024)

Planned to work with:
 - Sensors in Tasmota devices for sensors YOU send pull requests (or device logs including the SENSOR message)
 - RGBW strips attached to Tasmota devices (my next step...)
 - Shutters operated by Tasmota devices once I have one or YOU send pull requests

## How To Contribute

* Open an issue if you think you discovered a bug, have a feature request or just a question
    * I'll close it if I think I can't help
    * You close it if the issue is solved for you
* Open a pull request if you think you fixed a bug or implemented a new feature or need help with that
    * Fork my github repository
    * Clone your fork
    * Implement the fix in your clone (don't change anything else)
    * Push your changes to your fork
    * Open a pull request from your fork against my repository
        * I'll merge it if I think it is useful
        * If I don't merge it, at least others can see what you've done and use your fork if they need it
