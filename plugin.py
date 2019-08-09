"""
<plugin 
    key="Tasmoticz" 
    name="Autodiscovery of Tasmota Devices"
    version="0.1.0"
    author="Joachim Banzhaf" 
    externallink="https://github.com/joba-1/Tasmoticz">
   
    <description>
        Plugin to discover and operate Tasmota devices through MQTT
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
try:
    import binascii
except Exception as e:
    errmsg += " binascii import error: "+str(e)


class BasePlugin:
    mqttClient = None

    def __init__(self):
        self.topics = ['LWT', 'STATE', 'SENSOR', 'ENERGY',
                       'RESULT', 'STATUS', 'STATUS2', 'STATUS5', 'STATUS8', 'STATUS11']
        return

    def onStart(self):
        if errmsg == "":
            try:
                Domoticz.Heartbeat(10)
                self.prefix1 = Parameters["Mode1"].strip()
                if self.prefix1 == "":
                    self.prefix1 = 'cmnd'
                self.prefix2 = Parameters["Mode2"].strip()
                if self.prefix2 == "":
                    self.prefix2 = 'stat'
                self.prefix3 = Parameters["Mode3"].strip()
                if self.prefix3 == "":
                    self.prefix3 = 'tele'
                self.subscriptions = Parameters["Mode4"].strip().split('|')
                self.debugging = Parameters["Mode6"]
                if self.debugging == "Verbose":
                    Domoticz.Debugging(2+4+8+16+64)
                if self.debugging == "Debug":
                    Domoticz.Debugging(2)
                Domoticz.Debug("Parameters: "+str(Parameters))
                self.mqttserveraddress = Parameters["Address"].strip()
                self.mqttserverport = Parameters["Port"].strip()
                self.mqttClient = MqttClientTasmoticz(self.mqttserveraddress, self.mqttserverport, "",
                                                      self.onMQTTConnected, self.onMQTTDisconnected, self.onMQTTPublish, self.onMQTTSubscribed)
            except Exception as e:
                Domoticz.Error("MQTT client start error: "+str(e))
                self.mqttClient = None
        else:
            Domoticz.Error(
                "Your Domoticz Python environment is not functional! "+errmsg)
            self.mqttClient = None
        #Domoticz.Debug("started on {}".format(sys.version))

    def checkDevices(self):
        Domoticz.Debug("checkDevices called")

    # TODO
    # react to commands arrived from Domoticz
    def onCommand(self, Unit, Command, Level, Color):
        # Log all requests from domoticz
        try:
            Domoticz.Debug("onCommand(): Unit: {}, Command: {}, Level: {}, Color: {}".format(
                Unit, Command, Level, Color))
        except Exception as e:
            Domoticz.Debug("onCommand(): invalid command: {}".format(str(e)))
            return False

        # If not connected to broker, we can't do much...
        if self.mqttClient is None:
            Domoticz.Debug("onCommand(): ignored, MQTT not connected")
            return False

        # Translate domoticz command to tasmota command
        try:
            topic = '{}/{}'.format(Devices[Unit].Options['Topic'],
                                   Devices[Unit].Options['Command'])
        except:
            return False

        msg = self.d2t(Devices[Unit].Options['Command'], Command)
        if msg is None:
            Domoticz.Debug("onCommand(): no message")
            return False

        # Send the tasmota command to the broker
        try:
            self.mqttClient.publish(topic, msg)
        except Exception as e:
            Domoticz.Error("onCommand(): {}".format(str(e)))
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
            subs = []
            for topic in self.subscriptions:
                topic = topic.replace('%topic%', '+')
                subs.append(topic.replace('%prefix%', self.prefix2) + '/+')
                subs.append(topic.replace('%prefix%', self.prefix3) + '/+')
            Domoticz.Debug(
                'onMQTTConnected: Subscriptions: {}'.format(repr(subs)))
            self.mqttClient.subscribe(subs)

    def onMQTTDisconnected(self):
        Domoticz.Debug("onMQTTDisconnected")

    def onMQTTSubscribed(self):
        Domoticz.Debug("onMQTTSubscribed")

    def findDevices(self, fullName):
        idxs = []
        deviceHash = self.deviceId(fullName)
        for device in Devices:
            deviceId = Devices[device].DeviceID
            # Domoticz.Debug('findDevices(): Fullname: {}, Hash: {}, DeviceId: {}'.format(fullName, deviceHash, deviceId))
            if deviceId == deviceHash:
                idxs.append(device)

        Domoticz.Debug('findDevices(): Fullname: {}, Idxs {}'.format(
            fullName, repr(idxs)))
        return idxs

    def getStateDevices(self, fullname, message):
        states = []
        baseattrs = ['POWER', 'POWER1', 'POWER2', 'POWER3', 'Heap', 'LoadAvg']
        for attr in baseattrs:
            try:
                value = message[attr]
                states.append((fullname+' '+attr, attr, value))
            except:
                pass

        wifiattrs = ['RSSI']
        for attr in wifiattrs:
            try:
                value = message['Wifi'][attr]
                states.append((fullname+' '+attr, attr, value))
            except:
                pass
        return states

    # TODO check which methods could be functions (i.e dont use self)

    def deviceId(self, deviceName):
        return '{:08X}'.format(binascii.crc32(deviceName.encode('utf8')) & 0xffffffff)

    def deviceByName(self, idxs, deviceName):
        for idx in idxs:
            try:
                if Devices[idx].Options['Name'] == deviceName:
                    return idx
            except:
                pass
        return None

    def createDevice(self, fullName, cmndName, deviceAttr, deviceName):
        '''
        Create domoticz device for deviceName
        DeviceID is hash of fullname
        Options dict contains necessary info
        Description contains options as json
        '''

        for idx in range(1, 512):
            if idx not in Devices:
                break

        if deviceAttr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
            deviceHash = self.deviceId(fullName)
            options = {'Name': deviceName,
                       'Topic': cmndName, 'Command': deviceAttr}
            Domoticz.Device(Name=deviceName, Unit=idx, TypeName="Switch", Used=1, Options=options,
                            Description=json.dumps(options, indent=2), DeviceID=deviceHash).Create()
            if idx in Devices:
                # Remove hardware/plugin name from device name
                Devices[idx].Update(
                    nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, Name=deviceName, SuppressTriggers=True)
                Domoticz.Log("Created Device ID: {}, Name: {}, On: {}, Hash: {}".format(
                    idx, deviceName, fullName, deviceHash))
                return idx
            Domoticz.Error("Failed creating Device ID: {}, Name: {}, On: {}".format(
                idx, deviceName, fullName))

        return None

    def d2t(self, attr, value):
        if attr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
            if value == "On":
                return "on"
            elif value == "Off":
                return "off"
        return None

    def t2d(self, attr, value):
        if attr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
            if value == "ON":
                return 1, "On"
            elif value == "OFF":
                return 0, "Off"
        return None, None

    def updateStateDevices(self, fullname, cmndname, message):
        idxs = self.findDevices(fullname)
        # deviceName derived from fullname and attribute name like POWER1, POWER2, Heap, LoadAvg, Wifi.RSSI
        for deviceName, deviceAttr, deviceValue in self.getStateDevices(fullname, message):
            # Domoticz.Debug('findOrCreateDevices(): Name: {}, Attr: {}, Value: {}'.format(deviceName, deviceAttr, deviceValue))
            idx = self.deviceByName(idxs, deviceName)
            if idx == None:
                idx = self.createDevice(
                    fullname, cmndname, deviceAttr, deviceName)
            if idx != None:
                nValue, sValue = self.t2d(deviceAttr, deviceValue)
                if nValue != None and sValue != None and (Devices[idx].nValue != nValue or Devices[idx].sValue != sValue):
                    Devices[idx].Update(nValue=nValue, sValue=sValue)

    def findResultDevice(self, fulltopic, jmsg):
        return []

    def findStatusDevices(self, fulltopic, jmsg):
        return []

    def findSensorDevices(self, fulltopic, jmsg):
        return []

    def findEnergyDevices(self, fulltopic, jmsg):
        return []

    def updateDeviceResult(self, idx, jmsg):
        pass

    def updateDeviceStatus(self, idx, jmsg):
        pass

    def updateDeviceVersion(self, idx, jmsg):
        pass

    def updateDeviceNet(self, idx, jmsg):
        pass

    def updateDeviceSensor(self, idx, jmsg):
        pass

    def updateDeviceEnergy(self, idx, jmsg):
        pass

    # TODO
    def onMQTTPublish(self, topic, message):  # process incoming MQTT statuses
        # Log all requests from mqtt broker
        Domoticz.Debug(
            "onMQTTPublish(): topic: {}, message: {}".format(topic, str(message)))

        # Check if we handle this topic tail at all
        subtopics = topic.split('/')
        tail = subtopics[-1]
        if tail not in self.topics:
            return True

        # Tasmota devices can have different FullTopic patterns.
        # All FullTopic patterns we care about are in self.subscriptions
        # Tasmota devices will be identified by a max 25 byte hex hash from FullTopic without %prefix%

        # Identify the subscription that matches our received subtopics
        fulltopic = []
        cmndtopic = []
        for subscription in self.subscriptions:
            patterns = subscription.split('/')
            for subtopic, pattern in zip(subtopics[:-1], patterns):
                if((pattern not in ('%topic%', '%prefix%', '+', subtopic)) or
                        (pattern == '%prefix%' and subtopic != self.prefix2 and subtopic != self.prefix3) or
                        (pattern == '%topic%' and subtopic == 'sonoff')):
                    fulltopic = []
                    cmndtopic = []
                    break
                if(pattern != '%prefix%'):
                    fulltopic.append(subtopic)
                    cmndtopic.append(subtopic)
                else:
                    cmndtopic.append(self.prefix1)
            if fulltopic != []:
                break

        if not fulltopic:
            return True

        fullname = '/'.join(fulltopic)
        cmndname = '/'.join(cmndtopic)

        # fullname should now contain all subtopic parts except for %prefix%es and tail
        # I.e. fullname is uniquely identifying the sensor or button refered by the message
        Domoticz.Log("onMQTTPublish(): device: {}, cmnd: {}, tail: {}, message: {}".format(
            fullname, cmndname, tail, str(message)))

        if tail == 'STATE':
            self.updateStateDevices(fullname, cmndname, message)

        elif tail == 'RESULT':
            idx = self.findResultDevice(fulltopic, message)
            if idx != None:
                self.updateDeviceResult(idx, message)

        elif tail == 'STATUS':
            for idx in self.findStatusDevices(fulltopic, message):
                self.updateDeviceStatus(idx, message)

        elif tail == 'STATUS2':
            for idx in self.findDevices(fulltopic):
                self.updateDeviceVersion(idx, message)

        elif tail == 'STATUS5':
            for idx in self.findDevices(fulltopic):
                self.updateDeviceNet(idx, message)

        elif tail == 'SENSOR':
            for idx in self.findSensorDevices(fulltopic, message):
                self.updateDeviceSensor(idx, message)

        elif tail == 'ENERGY':
            for idx in self.findEnergyDevices(fulltopic, message):
                self.updateDeviceEnergy(idx, message)

        # sensor/switch from tail/message (can be more than one per device)
        # Find device - update value
        # Not found: create device and Request STATUS, STATUS8, STATUS10, STATUS11 for friendly name, sensor, power

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
