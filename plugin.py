"""
<plugin key="Tasmoticz" name="Tasmota MQTT" version="0.1.0">
    <description>
      Plugin to discover and operate Tasmota devices through MQTT
      <br/>
    </description>
    <params>
        <param field="Address" label="MQTT broker address" width="300px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="300px" required="true" default="1883"/>
        <param field="Username" label="Username" width="300px"/>
        <param field="Password" label="Password" width="300px" default="" password="true"/>
        <param field="Topic" label="Tasmota Topic Format" width="300px" default="topic/prefix/subject"/>
        <param field="Base" label="Tasmota Base Topic" width="300px" default=""/>

        <param field="Mode1" label="Allow switching topic and prefix" width="75px">
            <options>
                <option label="True" value="1"/>
                <option label="False" value="0" default="true" />
            </options>
        </param>

        <param field="Mode6" label="Logging" width="75px">
            <options>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug" value="Debug"/>
                <option label="Normal" value="Normal" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
errmsg = ""
try:
 import Domoticz
except Exception as e:
 errmsg += "Domoticz core start error: "+str(e)
try:
 import json
except Exception as e:
 errmsg += " Json import error: "+str(e)
try:
 import time
except Exception as e:
 errmsg += " time import error: "+str(e)
try:
 import re
except Exception as e:
 errmsg += " re import error: "+str(e)
try:
 from mqtt import MqttClientTasmoticz
except Exception as e:
 errmsg += " MQTT client import error: "+str(e)

class BasePlugin:
    mqttClient = None

    def __init__(self):
     return

    def onStart(self):
     global errmsg
     if errmsg =="":
      try:
        Domoticz.Heartbeat(10)
        self.debugging = Parameters["Mode6"]
        self.topicswitch = Parameters["Mode1"]
        if self.debugging == "Verbose":
            Domoticz.Debugging(2+4+8+16+64)
        if self.debugging == "Debug":
            Domoticz.Debugging(2)
        self.base = Parameters["Base"].strip()
        self.topic = Parameters["Topic"].strip()
        self.mqttserveraddress = Parameters["Address"].strip()
        self.mqttserverport = Parameters["Port"].strip()
        self.mqttClient = MqttClientTasmoticz(self.mqttserveraddress, self.mqttserverport, "", self.onMQTTConnected, self.onMQTTDisconnected, self.onMQTTPublish, self.onMQTTSubscribed)
      except Exception as e:
        Domoticz.Error("MQTT client start error: "+str(e))
        self.mqttClient = None
     else:
        Domoticz.Error("Your Domoticz Python environment is not functional! "+errmsg)
        self.mqttClient = None

    def checkDevices(self):
        Domoticz.Debug("checkDevices called")

    def onStop(self):
        Domoticz.Debug("onStop called")

    # TODO
    def onCommand(self, Unit, Command, Level, Color):  # react to commands arrived from Domoticz
        # Log all requests from domoticz
        try:
            Domoticz.Debug("Domoticz Unit " + Unit + ", Command " + Command + ", Level " + str(Level) + ", Color:" + Color)
        except:
            Domoticz.Debug("Domoticz invalid command")

        # If not connected to broker, we can't do much...
        if self.mqttClient is None:
            Domoticz.Debug("not connected: ignoring domoticz command")
            return False

        # Translate domoticz command to tasmota command
        try:
            device = Devices[Unit]
            device_id = device.DeviceID.split('-')
        except Exception as e:
            Domoticz.Debug(str(e))
            return False

        # Dummy data for now...
        mqttpath = "tasmoticz"
        scmd = "hello world!"

        # Send the tasmota command to the broker
        try:
            self.mqttClient.publish(mqttpath, scmd)
        except Exception as e:
            Domoticz.Debug(str(e))
            return False

        return True

    def onConnect(self, Connection, Status, Description):
       if self.mqttClient is not None:
        self.mqttClient.onConnect(Connection, Status, Description)

    def onDisconnect(self, Connection):
       if self.mqttClient is not None:
        self.mqttClient.onDisconnect(Connection)

    def onMessage(self, Connection, Data):
       if self.mqttClient is not None:
        self.mqttClient.onMessage(Connection, Data)

    def onHeartbeat(self):
      Domoticz.Debug("Heartbeating...")
      if self.mqttClient is not None:
       try:
        # Reconnect if connection has dropped
        if (self.mqttClient._connection is None) or (not self.mqttClient.isConnected):
            Domoticz.Debug("Reconnecting")
            self.mqttClient._open()
        else:
            self.mqttClient.ping()
       except Exception as e:
        Domoticz.Error(str(e))

    def onMQTTConnected(self):
       if self.mqttClient is not None:
        self.mqttClient.subscribe([self.base + '#'])

    def onMQTTDisconnected(self):
        Domoticz.Debug("onMQTTDisconnected")

    def onMQTTSubscribed(self):
        Domoticz.Debug("onMQTTSubscribed")

    # TODO
    def onMQTTPublish(self, topic, message): # process incoming MQTT statuses
        # Log all requests from mqtt broker
        try:
            Domoticz.Debug("MQTT Topic " + str(topic) + ", Message " + str(message))
        except:
            Domoticz.Debug("MQTT invalid command")

        #  Domoticz.Device(Name=unitname, Unit=iUnit,TypeName="Switch",Used=1,DeviceID=unitname).Create()
        #  Domoticz.Device(Name=unitname, Unit=iUnit,Type=243,Subtype=29,Used=1,DeviceID=unitname).Create()
        #  Domoticz.Device(Name=unitname, Unit=iUnit,Type=244, Subtype=62, Switchtype=13,Used=1,DeviceID=unitname).Create() # create Blinds Percentage
        #  Domoticz.Device(Name=unitname, Unit=iUnit,Type=244, Subtype=62, Switchtype=15,Used=1,DeviceID=unitname).Create() # create Venetian Blinds EU type
        #  Domoticz.Device(Name=unitname+" BUTTON", Unit=iUnit,TypeName="Switch",Used=0,DeviceID=unitname).Create()
        #  Domoticz.Device(Name=unitname+" LONGPUSH", Unit=iUnit,TypeName="Switch",Used=0,DeviceID=unitname).Create()
        #  Domoticz.Device(Name=unitname, Unit=iUnit, TypeName="Temp+Hum",Used=1,DeviceID=unitname).Create() # create Temp+Hum Type=82
        #  for x in range(1, 256):
        #      if x not in Devices:
        #          iUnit=x
        #          break
        #  if iUnit==0:
        #      iUnit=len(Devices)+1
        #
        #  Devices[iUnit].Update(nValue=1, sValue="On")
        #  Devices[iUnit].Update(nValue=0, sValue=str(curval), BatteryLevel=int(mval))
        #
        #  curval = Devices[iUnit].sValue
        #  Domoticz.Device(Name=unitname, Unit=iUnit,Type=241, Subtype=3, Switchtype=7, Used=1,DeviceID=unitname).Create() # create Color White device
        #  Domoticz.Device(Name=unitname, Unit=iUnit,Type=241, Subtype=6, Switchtype=7, Used=1,DeviceID=unitname).Create() # create RGBZW device
        #  jmsg = json.loads(tmsg)
        #  if jmsg["turn"]=="on" or jmsg["turn"]=="1" or jmsg["turn"]==True:
        return True

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()
