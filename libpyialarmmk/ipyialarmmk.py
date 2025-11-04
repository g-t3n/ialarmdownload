# Copyright (C) 2022, ServiceA3
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from .pyialarmmk import iAlarmMkClient, iAlarmMkPushClient
import asyncio
import logging
from logging import Logger

class iAlarmMkInterface:
    """
    Interface with pyialarmmk library.
    """

    ARMED_AWAY = 0
    DISARMED = 1
    ARMED_STAY = 2
    CANCEL = 3
    TRIGGERED = 4
    ALARM_ARMING = 5
    UNAVAILABLE = 6

    ZONE_NOT_USED = 0
    ZONE_IN_USE = 1 << 0
    ZONE_ALARM = 1 << 1
    ZONE_BYPASS = 1 << 2
    ZONE_FAULT = 1 << 3
    ZONE_LOW_BATTERY = 1 << 4
    ZONE_LOSS = 1 << 5

    IALARMMK_P2P_DEFAULT_PORT = 18034
    IALARMMK_P2P_DEFAULT_HOST = "47.91.74.102"

    def __init__(
        self,
        uid: str,
        pwd: str,
        host: str,
        port: int,
        query_sensor: bool = False,
        hass=None,
        logger : Logger =None,
    ):
        self.threadID = "iAlarmMK-Thread"
        self.host = iAlarmMkInterface.IALARMMK_P2P_DEFAULT_HOST
        self.port = iAlarmMkInterface.IALARMMK_P2P_DEFAULT_PORT
        self.uid = uid
        self.pwd = pwd
        self.query_sensor = query_sensor

        self.ialarmmkClient = iAlarmMkClient(self.host, self.port, self.uid, self.pwd)

        self.callback = None
        self.polling_callback = None
        self.hass = hass
        self.logger = logger
        
        self.subscribed = False
        self.pollingActive = False
        
        self.logger.debug("iAlarm-MK Interface initialized")

        self.sensors = {}
        self.sensor_number = 0
        self.sensors_status = []

        self._get_status()
        
        if self.query_sensor:
            self._init_sensors()
        
        # self._get_sensors_status()

    def set_callback(self, callback):
        self.callback = callback

    def set_polling_callback(self, callback):
        self.polling_callback = callback

    async def subscribe(self):
        if self.subscribed:
            return
        
        self.subscribed = True
        disconnect_time = 60 * 5
        self.logger.debug("iAlarm-MK Subscribe started")
        
        while True:
            loop = asyncio.get_running_loop()
            on_con_lost = loop.create_future()
            transport, protocol = await loop.create_connection(
                lambda: iAlarmMkPushClient(
                    self.host,
                    self.port,
                    self.uid,
                    self.set_status,
                    loop,
                    on_con_lost,
                    self.logger,
                ),
                self.host,
                self.port,
            )

            try:
                await asyncio.sleep(disconnect_time)
            except Exception as e:
                self.logger.debug(e)
                pass
            finally:
                transport.close()
                transport = None
                self.subscribed = False
                self.logger.debug("iAlarm-MK Subscribe Timeout, reconnecting...")
                await asyncio.sleep(1)
                
        self.logger.debug("iAlarm-MK Subscribe stopped")

    async def polling(self):
        """Periodically poll the alarm sensors and invoke the polling callback if set.

        This method sleeps for 5 seconds between polls, updates sensor status,
        and calls the polling callback if it is defined.
        """
        self.logger.debug("iAlarm-MK Polling started")
        while True:
            try:
                if self.query_sensor is False:
                    self.logger.debug("iAlarm-MK Polling stopped")
                    return

                await asyncio.sleep(5)

                if self.sensor_number > 0:
                    self._get_sensors_status()
                    if self.polling_callback is not None:
                        self.polling_callback()
                else:
                    self.logger.debug("iAlarm-MK No sensors to poll")
            except:
                self.logger.debug("iAlarm-MK Polling exception")
                
    async def polling_once(self):
        """Poll the alarm sensors once to update their status."""
        try:
            if self.query_sensor is False or self.sensor_number == 0:
                self.logger.debug("iAlarm-MK Polling stopped")
                return
        
            client = iAlarmMkClient(self.host, self.port, self.uid, self.pwd)
            await asyncio.to_thread(client.login)
            #await asyncio.sleep(0.5)
            states = await asyncio.to_thread(client.GetByWay)
            #await asyncio.sleep(0.5)
            await asyncio.to_thread(client.logout)
            #await asyncio.sleep(0.5)
            for sensor_id, sensor in self.sensors.items():
                self.sensors[sensor_id]["state"] = states[sensor["index"]]
                
            del client
            del states
            await asyncio.sleep(0)
        except:
            self.logger.debug("iAlarm-MK Unable to poll once", exc_info=True)
        
        
        #self.logger.debug("iAlarm-MK polling once started")
        #
        #
        #if self.query_sensor is False:
        #    self.logger.debug("iAlarm-MK No query sensor set, skipping polling")
        #    return

        #if self.sensor_number > 0:
        #    self._get_sensors_status()
        #else:
        #    self.logger.debug("iAlarm-MK No sensors to poll")

    def _get_status(self):
        try:
            self.ialarmmkClient.login()
            self.status = self.ialarmmkClient.GetAlarmStatus().get("DevStatus")
            self.ialarmmkClient.logout()
        except:
            self.status = self.UNAVAILABLE
            pass

    def get_status(self):
        return self.status

    def get_sensors(self):
        return self.sensors

    def _init_sensors(self):
        try:
            self.ialarmmkClient.login()
            sensors = self.ialarmmkClient.GetSensor()
            zones = self.ialarmmkClient.GetZone()
            states = self.ialarmmkClient.GetByWay()
            self.ialarmmkClient.logout()
            for index, s in enumerate(sensors):
                if s and len(s) > 0:
                    self.sensors[s] = {
                        "id": s,
                        "zone": zones[index],
                        "state": states[index],  # or False if unknown
                        "index": index,
                    }
                    self.sensor_number += 1
                    
            self.query_sensor = self.sensor_number > 0
        except Exception as e:
            self.logger.debug("iAlarm-MK Unable to initialize sensors", exc_info=True)

    def _get_sensors_status(self):
        try:
            self.ialarmmkClient.login()
            states = self.ialarmmkClient.GetByWay()
            self.ialarmmkClient.logout()

            for sensor_id, sensor in self.sensors.items():
                self.sensors[sensor_id]["state"] = states[sensor["index"]]
        except:
            self.logger.debug("iAlarm-MK Unable to get sensors status", exc_info=True)
            return None

    def get_sensor_status(self, id):
        try:
            return self.sensors[id]["state"]
        except:
            return None

    def is_sensor_open(self, id):
        try:
            status = self.sensors[id]["state"]
            return status in (9, 11, 17, 27)
        except:
            return None

    def set_status(self, status):
        new_status = int(status.get("Cid"))

        if new_status == 1401:
            self.status = 1
        elif new_status == 1406:
            self.status = 1
        elif new_status == 3401:
            self.status = 0
        elif new_status == 3441:
            self.status = 2
        elif new_status == 1100 or new_status == 1101 or new_status == 1120:
            self.status = 4
        elif new_status == 1131 or new_status == 1132 or new_status == 1133:
            self.status = 4
        elif new_status == 1134 or new_status == 1137:
            self.status = 4

        if self.callback is not None:
            self.callback(self.status)

    def cancel_alarm(self) -> None:
        try:
            self.ialarmmkClient.login()
            self.ialarmmkClient.SetAlarmStatus(3)
            self._set_status(self.DISARMED)
            self.ialarmmkClient.logout()
        except:
            pass

    def arm_stay(self) -> None:
        try:
            self.ialarmmkClient.login()
            self.ialarmmkClient.SetAlarmStatus(2)
            self._set_status(self.ARMED_STAY)
            self.ialarmmkClient.logout()
        except:
            self.logger.debug("iAlarm-MK Unable to arm home", exc_info=True)


    def disarm(self) -> None:
        try:
            self.ialarmmkClient.login()
            self.ialarmmkClient.SetAlarmStatus(1)
            self._set_status(self.DISARMED)
            self.ialarmmkClient.logout()
        except:
            self.logger.debug("iAlarm-MK Unable to disarm", exc_info=True)


    def arm_away(self) -> None:
        try:
            self.ialarmmkClient.login()
            self.ialarmmkClient.SetAlarmStatus(0)
            self._set_status(self.ALARM_ARMING)
            self.ialarmmkClient.logout()
        except:
            self.logger.debug("iAlarm-MK Unable to arm away", exc_info=True)


    def _set_status(self, status):
        if self.hass is not None:
            asyncio.run_coroutine_threadsafe(
                self.async_set_status(status), self.hass.loop
            ).result()

    async def async_set_status(self, status):
        self.callback(status)
        pass

    def get_mac(self) -> str:
        self.ialarmmkClient.login()
        network_info = self.ialarmmkClient.GetNet()
        self.ialarmmkClient.logout()
        if network_info is not None:
            mac = network_info.get("Mac", "")

        if mac:
            return mac
        else:
            raise ConnectionError(
                "An error occurred trying to connect to the alarm "
                "system or received an unexpected reply"
            )
