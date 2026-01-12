import ctypes
from comtypes import CLSCTX_ALL, GUID, IUnknown, COMMETHOD, HRESULT
from comtypes import client as com_client
from pycaw.pycaw import AudioUtilities
import comtypes

class AudioSwitcher:
    def __init__(self):
        try:
            comtypes.CoInitialize()
        except: pass
        self.policy_config = self._get_policy_config()

    def _get_policy_config(self):
        try:
            class IPolicyConfig(IUnknown):
                _iid_ = GUID('{f8679f50-850a-41cf-9c72-430f290290c8}')
                _methods_ = [
                    COMMETHOD([], HRESULT, 'GetMixFormat'),
                    COMMETHOD([], HRESULT, 'GetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'ResetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'SetDeviceFormat'),
                    COMMETHOD([], HRESULT, 'GetProcessingPeriod'),
                    COMMETHOD([], HRESULT, 'SetProcessingPeriod'),
                    COMMETHOD([], HRESULT, 'GetShareMode'),
                    COMMETHOD([], HRESULT, 'SetShareMode'),
                    COMMETHOD([], HRESULT, 'GetPropertyValue'),
                    COMMETHOD([], HRESULT, 'SetPropertyValue'),
                    COMMETHOD([], HRESULT, 'SetDefaultEndpoint', (['in'], ctypes.c_wchar_p, 'wszDeviceId'), (['in'], ctypes.c_int, 'role')),
                ]
            CLSID_PolicyConfig = GUID('{870af99c-171d-4f9e-af0d-e63df40c2bc9}')
            return com_client.CreateObject(CLSID_PolicyConfig, interface=IPolicyConfig)
        except Exception as e:
            return None

    def get_devices(self):
        devs = []
        try:
            device_enumerator = AudioUtilities.GetDeviceEnumerator()
            collection = device_enumerator.EnumAudioEndpoints(0, 1) # 0=Render, 1=Active
            count = collection.GetCount()
            for i in range(count):
                raw_dev = collection.Item(i)
                device = AudioUtilities.CreateDevice(raw_dev)
                devs.append({'name': device.FriendlyName, 'id': device.id})
        except: pass
        return devs

    def get_current_device_id(self):
        try:
            device_enumerator = AudioUtilities.GetDeviceEnumerator()
            current = device_enumerator.GetDefaultAudioEndpoint(0, 1) # 0=Render, 1=Console
            return current.GetId()
        except: return None

    def set_default_device(self, device_id):
        if not self.policy_config: return
        try:
            self.policy_config.SetDefaultEndpoint(device_id, 0)
            self.policy_config.SetDefaultEndpoint(device_id, 2)
        except: pass