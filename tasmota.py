import collections
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
    import binascii
except Exception as e:
    errmsg += " binascii import error: "+str(e)


tasmotaDebug = True


# Decide if tasmota.py debug messages should be displayed if domoticz debug is enabled for this plugin
def setTasmotaDebug(flag):
    global tasmotaDebug
    tasmotaDebug = flag


# Replaces Domoticz.Debug() so tasmota related messages can be turned off from plugin.py
def Debug(msg):
    if tasmotaDebug:
        Domoticz.Debug(msg)


# Handles incoming Tasmota messages from MQTT or Domoticz commands for Tasmota devices
class Handler:
    def __init__(self, subscriptions, prefix1, prefix2, prefix3, mqttClient, devices):
        Debug("Handler::__init__(cmnd: {}, stat: {}, tele: {}, subs: {})".format(
            prefix1, prefix2, prefix3, repr(subscriptions)))

        if errmsg != "":
            Domoticz.Error(
                "Handler::__init__: Domoticz Python env error {}".format(errmsg))

        # So far only STATUS, STATE, SENSOR and RESULT are used. Others just for research...
        self.topics = ['INFO1', 'STATE', 'SENSOR', 'RESULT', 'STATUS',
                       'STATUS5', 'STATUS8', 'STATUS11', 'ENERGY']

        self.prefix = [None, prefix1, prefix2, prefix3]
        self.subscriptions = subscriptions
        self.mqttClient = mqttClient

        # I don't understand variable (in)visibility
        global Devices
        Devices = devices

    def debug(self, flag):
        global tasmotaDebug
        tasmotaDebug = flag

    # Translate domoticz command to tasmota mqtt command(s?)
    def onDomoticzCommand(self, Unit, Command, Level, Color):
        Debug("Handler::onDomoticzCommand: Unit: {}, Command: {}, Level: {}, Color: {}".format(
            Unit, Command, Level, Color))

        if self.mqttClient is None:
            return False

        try:
            description = json.loads(Devices[Unit].Description)
            topic = '{}/{}'.format(description['Topic'],
                                   description['Command'])
        except:
            return False

        msg = d2t(description['Command'], Command)
        if msg is None:
            Debug("Handler::onDomoticzCommand: no message")
            return False

        try:
            self.mqttClient.publish(topic, msg)
        except Exception as e:
            Domoticz.Error("Handler::onDomoticzCommand: {}".format(str(e)))
            return False

        return True

    # Subscribe to our topics
    def onMQTTConnected(self):
        subs = []
        for topic in self.subscriptions:
            topic = topic.replace('%topic%', '+')
            subs.append(topic.replace('%prefix%', self.prefix[2]) + '/+')
            subs.append(topic.replace('%prefix%', self.prefix[3]) + '/+')
        Debug('Handler::onMQTTConnected: Subscriptions: {}'.format(repr(subs)))
        self.mqttClient.subscribe(subs)

    # Process incoming MQTT messages
    def onMQTTPublish(self, topic, message):
        Debug("Handler::onMQTTPublish: topic: {}".format(topic))

        # Check if we handle this topic tail at all
        subtopics = topic.split('/')
        tail = subtopics[-1]
        if tail not in self.topics:
            return True

        # Different Tasmota devices can have different FullTopic patterns.
        # All FullTopic patterns we care about are in self.subscriptions
        # Tasmota devices will be identified by a hex hash from FullTopic without %prefix%

        # Identify the subscription that matches our received subtopics
        fulltopic = []
        cmndtopic = []
        for subscription in self.subscriptions:
            patterns = subscription.split('/')
            for subtopic, pattern in zip(subtopics[:-1], patterns):
                if((pattern not in ('%topic%', '%prefix%', '+', subtopic)) or
                    (pattern == '%prefix%' and subtopic != self.prefix[2] and subtopic != self.prefix[3]) or
                        (pattern == '%topic%' and (subtopic == 'sonoff' or subtopic == 'tasmota'))):
                    fulltopic = []
                    cmndtopic = []
                    break
                if(pattern != '%prefix%'):
                    fulltopic.append(subtopic)
                    cmndtopic.append(subtopic)
                else:
                    cmndtopic.append(self.prefix[1])
            if fulltopic != []:
                break

        if not fulltopic:
            return True

        fullName = '/'.join(fulltopic)
        cmndName = '/'.join(cmndtopic)

        # fullName should now contain all subtopic parts except for %prefix%es and tail
        # I.e. fullName is uniquely identifying the sensor or button refered by the message
        Debug("Handler::onMQTTPublish: device: {}, cmnd: {}, tail: {}, message: {}".format(
            fullName, cmndName, tail, str(message)))

        if tail == 'STATE':
            if updateStateDevices(fullName, cmndName, message):
                self.requestStatus(cmndName)
        elif tail == 'SENSOR':
            if updateSensorDevices(fullName, cmndName, message):
                self.requestStatus(cmndName)
        elif tail == 'RESULT':
            updateResultDevice(fullName, message)
        elif tail == 'STATUS':
            updateStatusDevices(fullName, cmndName, message)
        if tail == 'INFO1':
            updateInfo1Devices(fullName, cmndName, message)
            self.requestStatus(cmndName)
        elif tail == 'STATUS5':
            updateNetDevices(fullName, cmndName, message)
        elif tail == 'ENERGY':
            updateEnergyDevices(fullName, cmndName, message)

        return True

    # Request device STATUS via mqtt
    def requestStatus(self, cmdName):
        Debug("Handler::requestStatus: {}".format(cmdName))
        try:
            topic = '{}/{}'.format(cmdName, "STATUS")
            self.mqttClient.publish(topic, "")
        except Exception as e:
            Domoticz.Error("Handler::requestStatus: {}".format(str(e)))


###########################
# Tasmota Utility functions


# Generate a hash identifying a tasmota device as a whole. Stored as DeviceId in domoticz devices (1:n relation)
def deviceId(deviceName):
    return '{:08X}'.format(binascii.crc32(deviceName.encode('utf8')) & 0xffffffff)


# Collects a list of unit ids of all domoticz devices refering to the same tasmota device
def findDevices(fullName):
    idxs = []
    deviceHash = deviceId(fullName)
    for device in Devices:
        if Devices[device].DeviceID == deviceHash:
            idxs.append(device)

    Debug('tasmota::findDevices: fullName: {}, Idxs {}'.format(fullName, repr(idxs)))
    return idxs


# Collects a list of all supported attribute key/value pairs from tasmota tele STATE messages
def getStateDevices(message):
    states = []
    for attr in ['POWER', 'Heap', 'LoadAvg'] + ['POWER{}'.format(r) for r in range(1, 33)]:
        try:
            value = message[attr]
            states.append((attr, value))
        except:
            pass

    wifiattrs = ['RSSI']
    for attr in wifiattrs:
        try:
            value = message['Wifi'][attr]
            states.append((attr, value))
        except:
            pass
    return states


# Collects a list of all supported attribute sensor/type/value tuples from tasmota tele SENSOR messages
# * One sensor can contain several types (e.g. DHT11 has Temperature and Humidity)
# * Additional desc contains info needed to create a matching domoticz device
#  * Name is used for display / translation
#  * Unit is only relevant for DomoType Custom (AFAIK other types have fixed units in domoticz)
def getSensorDevices(message):
    states = []

    typeDb = {
        'Temperature':   {'Name': 'Temperatur',      'Unit': '°C',   'DomoType': 'Temperature'},
        'Humidity':      {'Name': 'Feuchtigkeit',    'Unit': '%',    'DomoType': 'Humidity'},
        'Pressure':      {'Name': 'Luftdruck',       'Unit': 'hPa',  'DomoType': 'Barometer'},
        'Illuminance':   {'Name': 'Helligkeit',      'Unit': 'lux',  'DomoType': 'Illumination'},
        'Distance':      {'Name': 'Abstand',         'Unit': 'mm ',  'DomoType': 'Distance'},
        'Total':         {'Name': 'Gesamt',          'Unit': 'kWh',  'DomoType': 'Custom'},
        'Yesterday':     {'Name': 'Gestern',         'Unit': 'kWh',  'DomoType': 'Custom'},
        'Today':         {'Name': 'Heute',           'Unit': 'kWh',  'DomoType': 'Custom'},
        'Power':         {'Name': 'Leistung',        'Unit': 'kW',   'DomoType': 'Usage'},
        'ApparentPower': {'Name': 'Scheinleistung',  'Unit': 'kW',   'DomoType': 'Usage'},
        'ReactivePower': {'Name': 'Blindleistung',   'Unit': 'kW',   'DomoType': 'Usage'},
        'Factor':        {'Name': 'Leistungsfaktor', 'Unit': 'W/VA', 'DomoType': 'Custom'},
        'Voltage':       {'Name': 'Spannung',        'Unit': 'V',    'DomoType': 'Voltage'},
        'Current':       {'Name': 'Strom',           'Unit': 'A',    'DomoType': 'Current (Single)'}
    }

    if isinstance(message, collections.Mapping):
        for sensor, sensorData in message.items():
            if isinstance(sensorData, collections.Mapping):
                for type, value in sensorData.items():
                    if type in typeDb:
                        desc = typeDb[type].copy()
                        desc['Sensor'] = sensor
                        if sensor == 'ENERGY':
                            desc['Sensor'] = 'Energie'
                        states.append((sensor, type, value, desc))

    return states


# Find the domoticz device unit id matching a STATE or SENSOR attribute coming from tasmota
def deviceByAttr(idxs, attr):
    for idx in idxs:
        try:
            description = json.loads(Devices[idx].Description)
            if description['Command'] == attr:
                return idx
        except:
            pass
    return None


# Some domoticz device Create(), Update() and query value examples
#
#  Domoticz.Device(Name=unitname, Unit=iUnit,TypeName="Switch",Used=1,DeviceID=unitname).Create()
#  Domoticz.Device(Name=unitname, Unit=iUnit,Type=243,Subtype=29,Used=1,DeviceID=unitname).Create()
#  Domoticz.Device(Name=unitname, Unit=iUnit,Type=244, Subtype=62, Switchtype=13,Used=1,DeviceID=unitname).Create() # create Blinds Percentage
#  Domoticz.Device(Name=unitname, Unit=iUnit,Type=244, Subtype=62, Switchtype=15,Used=1,DeviceID=unitname).Create() # create Venetian Blinds EU type
#  Domoticz.Device(Name=unitname+" BUTTON", Unit=iUnit,TypeName="Switch",Used=0,DeviceID=unitname).Create()
#  Domoticz.Device(Name=unitname+" LONGPUSH", Unit=iUnit,TypeName="Switch",Used=0,DeviceID=unitname).Create()
#  Domoticz.Device(Name=unitname, Unit=iUnit, TypeName="Temp+Hum",Used=1,DeviceID=unitname).Create() # create Temp+Hum Type=82
#
#  Devices[iUnit].Update(nValue=1, sValue="On")
#  Devices[iUnit].Update(nValue=0, sValue=str(curval), BatteryLevel=int(mval))
#
#  curval = Devices[iUnit].sValue
#  Domoticz.Device(Name=unitname, Unit=iUnit,Type=241, Subtype=3, Switchtype=7, Used=1,DeviceID=unitname).Create() # create Color White device
#  Domoticz.Device(Name=unitname, Unit=iUnit,Type=241, Subtype=6, Switchtype=7, Used=1,DeviceID=unitname).Create() # create RGBZW device


# Create a domoticz device from infos extracted out of tasmota STATE tele messages
def createStateDevice(fullName, cmndName, deviceAttr):
    '''
    Create domoticz device for deviceName
    DeviceID is hash of fullName
    Description contains necessary info as json (previously used Options, but got overwritten for Custom devices)
    '''

    for idx in range(1, 512):
        if idx not in Devices:
            break

    if deviceAttr in ['POWER'] + ['POWER{}'.format(r) for r in range(1, 33)]:
        deviceHash = deviceId(fullName)
        deviceName = '{} {}'.format(fullName, deviceAttr)
        description = {'Topic': cmndName, 'Command': deviceAttr, 'Device': 'Schalter'}
        if deviceAttr == 'POWER':
            description["Type"] = ""
        else:
            description["Type"] = deviceAttr[5:]
        Domoticz.Device(Name=deviceName, Unit=idx, TypeName="Switch", Used=1,
                        Description=json.dumps(description, indent=2, ensure_ascii=False), DeviceID=deviceHash).Create()
        if idx in Devices:
            # Remove hardware/plugin name from domoticz device name
            Devices[idx].Update(
                nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, Name=deviceName, SuppressTriggers=True)
            Domoticz.Log("tasmota::createStateDevice: ID: {}, Name: {}, On: {}, Hash: {}".format(
                idx, deviceName, fullName, deviceHash))
            return idx
        Domoticz.Error("tasmota::createStateDevice: Failed creating Device ID: {}, Name: {}, On: {}".format(
            idx, deviceName, fullName))

    return None


# Create a domoticz device from infos extracted out of tasmota SENSOR tele messages
def createSensorDevice(fullName, cmndName, deviceAttr, desc):
    '''
    Create domoticz sensor device for deviceName
    DeviceID is hash of fullName
    Description contains necessary info as json (previously used Options, but got overwritten for Custom devices)
    '''

    for idx in range(1, 512):
        if idx not in Devices:
            break

    deviceHash = deviceId(fullName)
    deviceName = '{} {} {}'.format(fullName, desc['Sensor'], desc['Name'])
    description = {'Topic': cmndName, 'Command': deviceAttr,
                   'Device': desc['Sensor'], 'Type': desc['Name']}
    if desc['DomoType'] == 'Custom':
        options = {'Custom': '1;{}'.format(desc['Unit'])}
    else:
        options = None
    Domoticz.Device(Name=deviceName, Unit=idx, TypeName=desc['DomoType'], Used=1, Options=options,
                    Description=json.dumps(description, indent=2, ensure_ascii=False), DeviceID=deviceHash).Create()
    if idx in Devices:
        # Remove hardware/plugin name from domoticz device name
        Devices[idx].Update(
            nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, Name=deviceName, SuppressTriggers=True)
        Domoticz.Log("tasmota::createSensorDevice: ID: {}, Name: {}, On: {}, Hash: {}".format(
            idx, deviceName, fullName, deviceHash))
        return idx

    Domoticz.Error("tasmota::createSensorDevice: Failed creating Device ID: {}, Name: {}, On: {}".format(
        idx, deviceName, fullName))
    return None


# Translate device value received form domoticz to tasmota attribute/value
def d2t(attr, value):
    if attr in ['POWER'] + ['POWER{}'.format(r) for r in range(1, 33)]:
        if value == "On":
            return "on"
        elif value == "Off":
            return "off"
    return None


# Translate values of a tasmota attribute to matching domoticz device value
def t2d(attr, value, type, subtype):
    if attr in ['POWER'] + ['POWER{}'.format(r) for r in range(1, 33)]:
        if value == "ON":
            return 1, "On"
        elif value == "OFF":
            return 0, "Off"
    elif type == 81:
        # Domoticz humidity only accepted as integer
        return int(round(float(value))), ""
    elif type == 243:
        if subtype == 26:
            # Domoticz barometer needs nValue=0 and sValue="pressure;5"
            return 0, "{};5".format(value)
        if subtype == 27:
            # Domoticz distance needs cm but gets mm
            return 0, str(float(value)/10)
    return 0, str(value)


# Update a tasmota attributes value in its associated domoticz device idx
def updateValue(idx, attr, value):
    nValue, sValue = t2d(attr, value, Devices[idx].Type, Devices[idx].SubType)
    if nValue != None and sValue != None:
        if Devices[idx].nValue != nValue or Devices[idx].sValue != sValue:
            Debug("tasmota::updateValue: Idx:{}, Attr: {}, nValue: {}, sValue: {}".format(
                idx, attr, nValue, sValue))
            Devices[idx].Update(nValue=nValue, sValue=sValue)


# Update domoticz device values related to tasmota STATE message, create device if it does not exist yet
# Returns true if a new device was created
def updateStateDevices(fullName, cmndName, message):
    ret = False
    idxs = findDevices(fullName)
    for attr, value in getStateDevices(message):
        idx = deviceByAttr(idxs, attr)
        if idx == None:
            idx = createStateDevice(fullName, cmndName, attr)
            if idx != None:
                ret = True
        if idx != None:
            updateValue(idx, attr, value)
    return ret


# Update domoticz device related to tasmota RESULT message (e.g. on power on/off)
def updateResultDevice(fullName, message):
    idxs = findDevices(fullName)
    attr, value = next(iter(message.items()))
    for idx in idxs:
        description = json.loads(Devices[idx].Description)
        if description['Command'] == attr:
            updateValue(idx, attr, value)


# Update domoticz device values related to tasmota SENSOR message, create device if it does not exist yet
# Returns true if a new device was created
def updateSensorDevices(fullName, cmndName, message):
    ret = False
    idxs = findDevices(fullName)
    #   ENERGY, Voltage, 220 {Name: Spannung, Unit: V}
    for sensor, type, value, desc in getSensorDevices(message):
        attr = '{}-{}'.format(sensor, type)
        idx = deviceByAttr(idxs, attr)
        if idx == None:
            idx = createSensorDevice(fullName, cmndName, attr, desc)
            if idx != None:
                ret = True
        if idx != None:
            updateValue(idx, attr, value)
    return ret


# Update domoticz device values related to tasmota INFO1 message: Version and Module
def updateInfo1Devices(fullName, cmndName, message):
    try:
        module = message["Module"]
        version = message["Version"]
        for idx in findDevices(fullName):
            description = json.loads(Devices[idx].Description)
            dirty = False
            if "Module" not in description or module != description["Module"]:
                Domoticz.Log("tasmota::updateInfo1Devices: idx: {}, name: {}, module: {}".format(
                    idx, Devices[idx].Name, module))
                description["Module"] = module
                dirty = True
            if "Version" not in description or version != description["Version"]:
                Domoticz.Log("tasmota::updateInfo1Devices: idx: {}, name: {}, version: {}".format(
                    idx, Devices[idx].Name, version))
                description["Version"] = version
                dirty = True
            if dirty:
                Devices[idx].Update(nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, 
                    Description=json.dumps(description, indent=2, ensure_ascii=False), SuppressTriggers=True)
    except Exception as e:
        Domoticz.Error("tasmota::updateInfo1Devices: Set module and version failed: {}".format(str(e)))


# Update domoticz device names from friendly names of tasmota STATUS message
def updateStatusDevices(fullName, cmndName, message):
    try:
        names = message["Status"]["FriendlyName"]
        for idx in findDevices(fullName):
            description = json.loads(Devices[idx].Description)
            command = description["Command"]
            nonames = ['Sonoff', 'Tasmota', '', None] + ['Tasmota{}'.format(r) for r in range(2, 9)]
            name = None
            for i in range(1, 8):
                if command == "POWER{}".format(i+1) and len(names) > i and names[i] not in nonames:
                    name = names[i]
                    break
            if name == None and names[0] not in nonames:
                name = names[0]
            if name != None and command != 'POWER':
                name += ' ' + description["Type"]
            if name != None and Devices[idx].Name != name and ('Name' not in description or Devices[idx].Name == description["Name"]):
                Domoticz.Log("tasmota::updateStatusDevices: idx: {}, from: {}, to: {}".format(
                    idx, Devices[idx].Name, name))
                description["Name"] = name
                Devices[idx].Update(
                    nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, Name=name, 
                    Description=json.dumps(description, indent=2, ensure_ascii=False), SuppressTriggers=True)
            else:
                Debug("tasmota::updateStatusDevices: idx: {}, rename: {}, skipped: {}".format(
                    idx, Devices[idx].Name, repr(names)))
    except Exception as e:
        Domoticz.Error("tasmota::updateStatusDevices: Set friendly name failed: {}".format(str(e)))


# TODO
# Add or update tasmota network info in domoticz device description if it changed
def updateNetDevices(fullName, cmndName, message):
    pass


# TODO
# Handle tasmota ENERGY tele messages similar to SENSOR tele messages (still needed?)
def updateEnergyDevices(fullName, cmndName, message):
    pass

# TODO
# other types of switches (interlock, inching, shutters...)
# dimmers
# color control
# UI translations
# send RSSI on updates, RSSI as sensor value
# combined tasmota sensor values (temp/humi/baro, ...)
# respect units configured in tasmota (°C vs F, ...) 
