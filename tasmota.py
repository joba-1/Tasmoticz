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

        # So far only STATE, SENSOR and RESULT used. Others just for research...
        self.topics = ['LWT', 'STATE', 'SENSOR', 'ENERGY', 'RESULT',
                       'STATUS', 'STATUS2', 'STATUS5', 'STATUS8', 'STATUS11']

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
                        (pattern == '%topic%' and subtopic == 'sonoff')):
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
        Domoticz.Log("Handler::onMQTTPublish: device: {}, cmnd: {}, tail: {}, message: {}".format(
            fullName, cmndName, tail, str(message)))

        if tail == 'STATE':
            updateStateDevices(fullName, cmndName, message)
        elif tail == 'RESULT':
            updateResultDevice(fullName, message)
        elif tail == 'STATUS':
            updateStatusDevices(fullName, cmndName, message)
        elif tail == 'STATUS2':
            updateVersionDevices(fullName, cmndName, message)
        elif tail == 'STATUS5':
            updateNetDevices(fullName, cmndName, message)
        elif tail == 'SENSOR':
            updateSensorDevices(fullName, cmndName, message)
        elif tail == 'ENERGY':
            updateEnergyDevices(fullName, cmndName, message)

        return True


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
    baseattrs = ['POWER', 'POWER1', 'POWER2', 'POWER3', 'Heap', 'LoadAvg']
    for attr in baseattrs:
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
# * If a sensor name needs translation for display, this is done with its Name entry
def getSensorDevices(message):
    states = []

    sensors = {
        'DHT11': {
            'Temperature':   {'Name': 'Temperatur',      'Unit': '°C',   'DomoType': 'Temperature'},
            'Humidity':      {'Name': 'Feuchtigkeit',    'Unit': '%',    'DomoType': 'Humidity'}
        },
        'AM2301': {
            'Temperature':   {'Name': 'Temperatur',      'Unit': '°C',   'DomoType': 'Temperature'},
            'Humidity':      {'Name': 'Feuchtigkeit',    'Unit': '%',    'DomoType': 'Humidity'}
        },
        'ENERGY': {
            'Name':          'Energie',  # set, if different from key
            'Total':         {'Name': 'Gesamt',          'Unit': 'kWh',  'DomoType': 'Custom'},
            'Yesterday':     {'Name': 'Gestern',         'Unit': 'kWh',  'DomoType': 'Custom'},
            'Today':         {'Name': 'Heute',           'Unit': 'kWh',  'DomoType': 'Custom'},
            'Power':         {'Name': 'Leistung',        'Unit': 'kW',   'DomoType': 'Usage'},
            'ApparentPower': {'Name': 'Scheinleistung',  'Unit': 'kW',   'DomoType': 'Usage'},
            'ReactivePower': {'Name': 'Blindleistung',   'Unit': 'kW',   'DomoType': 'Usage'},
            'Factor':        {'Name': 'Leistungsfaktor', 'Unit': 'W/VA', 'DomoType': 'Custom'},
            'Voltage':       {'Name': 'Spannung',        'Unit': 'V',    'DomoType': 'Voltage'},
            'Current':       {'Name': 'Strom',           'Unit': 'A',    'DomoType': 'Current (Single)'}
        },
        'TSL2561': {
            'Illuminance':   {'Name': 'Helligkeit',      'Unit': 'lux',  'DomoType': 'Illumination'}
        },
        'BMP280': {
            'Temperature':   {'Name': 'Temperatur',      'Unit': '°C',   'DomoType': 'Temperature'},
            'Pressure':      {'Name': 'Druck',           'Unit': 'hPa',  'DomoType': 'Barometer'}
        },
        'BME280': {
            'Temperature':   {'Name': 'Temperatur',      'Unit': '°C',   'DomoType': 'Temperature'},
            'Pressure':      {'Name': 'Druck',           'Unit': 'hPa',  'DomoType': 'Barometer'},
            'Humidity':      {'Name': 'Feuchtigkeit',    'Unit': '%',    'DomoType': 'Humidity'}
        }
    }

    for sensor, values in sensors.items():
        for type, desc in values.items():
            try:
                value = message[sensor][type]
                try:
                    desc['Sensor'] = values['Name']
                except:
                    desc['Sensor'] = sensor
                states.append((sensor, type, value, desc))
            except:
                pass

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

    if deviceAttr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
        deviceHash = deviceId(fullName)
        deviceName = '{} {}'.format(fullName, deviceAttr)
        description = {'Topic': cmndName, 'Command': deviceAttr}
        Domoticz.Device(Name=deviceName, Unit=idx, TypeName="Switch", Used=1,
                        Description=json.dumps(description, indent=2), DeviceID=deviceHash).Create()
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
    description = {'Topic': cmndName, 'Command': deviceAttr}
    if desc['DomoType'] == 'Custom':
        options = {'Custom': '1;{}'.format(desc['Unit'])}
    else:
        options = None
    Domoticz.Device(Name=deviceName, Unit=idx, TypeName=desc['DomoType'], Used=1, Options=options,
                    Description=json.dumps(description, indent=2), DeviceID=deviceHash).Create()
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
    if attr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
        if value == "On":
            return "on"
        elif value == "Off":
            return "off"
    return None


# Translate values of a tasmota attribute to matching domoticz device value
def t2d(attr, value, type, subtype):
    if attr in ['POWER', 'POWER1', 'POWER2', 'POWER3']:
        if value == "ON":
            return 1, "On"
        elif value == "OFF":
            return 0, "Off"
    elif type == 81:
        # Domoticz humidity only accepted as integer
        return int(round(float(value))), ""
    elif type == 243 and subtype == 26:
        # Domoticz barometer needs nValue=0 and sValue="pressure;5"
        return 0, "{};5".format(value)
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
def updateStateDevices(fullName, cmndName, message):
    idxs = findDevices(fullName)
    for attr, value in getStateDevices(message):
        idx = deviceByAttr(idxs, attr)
        if idx == None:
            idx = createStateDevice(fullName, cmndName, attr)
        if idx != None:
            updateValue(idx, attr, value)


# Update domoticz device related to tasmota RESULT message (e.g. on power on/off)
def updateResultDevice(fullName, message):
    idxs = findDevices(fullName)
    attr, value = next(iter(message.items()))
    for idx in idxs:
        description = json.loads(Devices[idx].Description)
        if description['Command'] == attr:
            updateValue(idx, attr, value)


# Update domoticz device values related to tasmota SENSOR message, create device if it does not exist yet
def updateSensorDevices(fullName, cmndName, message):
    idxs = findDevices(fullName)
    #   ENERGY, Voltage, 220 {Name: Spannung, Unit: V}
    for sensor, type, value, desc in getSensorDevices(message):
        attr = '{}-{}'.format(sensor, type)
        idx = deviceByAttr(idxs, attr)
        if idx == None:
            idx = createSensorDevice(fullName, cmndName, attr, desc)
        if idx != None:
            updateValue(idx, attr, value)


# TODO
# Extract friendly name of tasmota device from STATUS message and use as domoticz device name
# Change device name to use friendly name instead of topic if description did not contain friendly name yet
# Update description with new friendly name if changed
# STATUS message to be triggered on device creation in create???Device().
#  Or in addition on update???Devices(), if description does not contain friendly name yet?
def updateStatusDevices(fullName, cmndName, message):
    pass


# TODO
# Add or update tasmota version info in domoticz device description if it changed
def updateVersionDevices(fullName, cmndName, message):
    pass


# TODO
# Add or update tasmota network info in domoticz device description if it changed
def updateNetDevices(fullName, cmndName, message):
    pass


# TODO
# Handle tasmota ENERGY tele messages similar to SENSOR tele messages (still needed?)
def updateEnergyDevices(fullName, cmndName, message):
    pass