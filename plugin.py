"""
<plugin 
    key="Tasmoticz" 
    name="Autodiscovery of Tasmota Devices"
    version="1.0.1"
    author="Joachim Banzhaf" 
    externallink="https://github.com/joba-1/Tasmoticz">
   
    <description>
        Plugin to discover and operate Tasmota devices through MQTT
        <br/>
        so far only switches are implemented
        <br/>
    </description>
    <params>
        <param field="Address" label="MQTT broker address" width="300px" required="true" default="localhost"/>
        <param field="Port" label="Port" width="300px" required="true" default="1883"/>
        <param field="Username" label="Username" width="300px"/>
        <param field="Password" label="Password" width="300px" default="" password="true"/>
        
        <param field="Mode1" label="Prefix1 (cmnd)" width="300px" default="cmnd"/>
        <param field="Mode2" label="Prefix2 (stat)" width="300px" default="stat"/>
        <param field="Mode3" label="Prefix3 (tele)" width="300px" default="tele"/>
        <param field="Mode4" label="Subscriptions" width="300px" default="%prefix%/%topic%|%topic%/%prefix%"/>

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
    from mqtt import MqttClient
except Exception as e:
    errmsg += " mqtt::MqttClient import error: "+str(e)
try:
    from tasmota import Handler
except Exception as e:
    errmsg += " tasmota::Handler import error: "+str(e)


pluginDebug = False


def Debug(msg):
    if pluginDebug:
        Domoticz.Debug(msg)
    
    
class Plugin:

    mqttClient = None
    tasmotaHandler = None

    def __init__(self):
        return

    def onStart(self):
        if errmsg == "":
            try:
                Domoticz.Heartbeat(10)
                self.debugging = Parameters["Mode6"]
                if self.debugging == "Verbose":
                    Domoticz.Debugging(2+4+8+16+64)
                if self.debugging == "Debug":
                    Domoticz.Debugging(2)
                self.debug(False)
                Domoticz.Status(
                    "Plugin::onStart: Parameters: {}".format(repr(Parameters)))
                self.mqttserveraddress = Parameters["Address"].strip()
                self.mqttserverport = Parameters["Port"].strip()
                self.mqttClient = MqttClient(self.mqttserveraddress, self.mqttserverport, "",
                                             self.onMQTTConnected, self.onMQTTDisconnected, self.onMQTTPublish, self.onMQTTSubscribed)
                self.mqttClient.debug(False)
                self.tasmotaHandler = Handler(Parameters["Mode4"].strip().split('|'), Parameters["Mode1"].strip(
                ), Parameters["Mode2"].strip(), Parameters["Mode3"].strip(), self.mqttClient, Devices)
                self.tasmotaHandler.debug(True)
            except Exception as e:
                Domoticz.Error("Plugin::onStart: init failed: {}".format(str(e)))
                self.mqttClient = None
        else:
            Domoticz.Error(
                "Plugin::onStart: Domoticz Python env error {}".format(errmsg))
            self.mqttClient = None

    def debug(self, flag):
        global pluginDebug
        pluginDebug = flag

    def checkDevices(self):
        Debug("Plugin::checkDevices")

    # Let tasmotaHandler react to commands from Domoticz

    def onCommand(self, Unit, Command, Level, Color):
        if self.mqttClient is None:
            return False
        return self.tasmotaHandler.onDomoticzCommand(Unit, Command, Level, Color)

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
        Debug("Plugin::onHeartbeat")
        if self.mqttClient is not None:
            try:
                # Reconnect if connection has dropped
                if (self.mqttClient._connection is None) or (not self.mqttClient.isConnected):
                    Debug("Plugin::onHeartbeat: Reconnecting")
                    self.mqttClient._open()
                else:
                    self.mqttClient.ping()
            except Exception as e:
                Domoticz.Error(str(e))

    # Let tasmotaHandler subscribe its topics

    def onMQTTConnected(self):
        if self.mqttClient is not None:
            self.tasmotaHandler.onMQTTConnected()

    def onMQTTDisconnected(self):
        Debug("Plugin::onMQTTDisconnected")

    def onMQTTSubscribed(self):
        Debug("Plugin::onMQTTSubscribed")

    # Let tasmotaHandler process incoming MQTT messages

    def onMQTTPublish(self, topic, message):
        return self.tasmotaHandler.onMQTTPublish(topic, message)


# Domoticz Python Plugin Interface

global _plugin
_plugin = Plugin()


def onStart():
    global _plugin
    _plugin.onStart()


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
