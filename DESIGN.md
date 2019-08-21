# Tasmoticz

How it works

Listen for standard Tasmota messsages on the MQTT broker

## Messages we care:
* Switch/Button state
* Sensor values (including energy)
* Color setting (later, V2)
* Status with friendly name and module name (for names in domoticz and housekeeping on module type changes)

## Messages are associated with Domoticz devices via hash of MQTT full topic + sensor/button
* Hash in hex is stored as domoticz DeviceID
* Got message with state or sensor values?
    * Hash+valuename new?
        * Create device
        * Request status with friendly name
    * Hash+valuename exists -> store new sensor/energy/button value
* Message has friendly name?
    * Set name of sensors with same hash, if friendly name changed and domoticz name is still default
* Set Description as JSON if something changed:
    * Module type
    * Firmware version
    * ...
    
Let's see how this evolves...
