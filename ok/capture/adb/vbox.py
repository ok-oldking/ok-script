# https://github.com/ArknightsAutoHelper/ArknightsAutoHelper/blob/5a9284773b68e12012c338cce50cb732f6a3542c/automator/control/adb/targets/vbox.py

import winreg
from dataclasses import dataclass

import adbutils
import win32com.client

from ok.capture.adb.targets import ADBControllerTarget
from ok.logging.Logger import get_logger
from ok.util import win32_process

logger = get_logger(__name__)


@dataclass
class VBoxClass:
    clsid: str
    vendor: str
    tag: str


@dataclass
class VBoxSerever(VBoxClass):
    path: str
    pid: int = 0


import ctypes

vbox_clsids = [
    VBoxClass('{20190809-47b9-4a1e-82b2-07ccd5323c3f}', 'LDPlayer', 'ld'),
    VBoxClass('{20191216-47b9-4a1e-82b2-07ccd5323c3f}', 'LDPlayer9', 'ld9'),
    VBoxClass('{88888888-47b9-4a1e-82b2-07ccd5323c3f}', 'Nox', 'nox'),
    VBoxClass('{baf3f651-58d8-429d-97ad-2b5699b43567}', 'BlueStacks', 'bstk'),
    VBoxClass('{b1a7a4f2-47b9-4a1e-82b2-07ccd5323c3a}', 'Memu', 'memu'),
    VBoxClass('{81919390-a492-11e5-a837-0800200c9a66}', 'MuMu', 'mumu'),
    VBoxClass('{23cd1535-edaa-4f21-a4ab-45d97fd1d58b}', 'MuMu 12',
              'mumu 12'),
    # ('{B1A7A4F2-47B9-4A1E-82B2-07CCD5323C3F}', 'Oracle', 'oracle'),  # nobody uses this
]

OpenProcess = ctypes.windll.kernel32.OpenProcess
OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
OpenProcess.restype = ctypes.c_void_p
PROCESS_QUERY_INFORMATION = 0x0400
CloseHandle = ctypes.windll.kernel32.CloseHandle
CloseHandle.argtypes = [ctypes.c_void_p]


def get_server(clsid):
    try:
        with winreg.OpenKeyEx(winreg.HKEY_CLASSES_ROOT, 'CLSID\\%s\\LocalServer32' % clsid, 0,
                              winreg.KEY_READ) as hkey:
            value = winreg.QueryValue(hkey, None)
            filename = value.strip('"')
            return win32_process.get_final_path(filename)
    except OSError:
        return None


# current process's privilege must equal to the target process's privilege, can raise a error if not
def installed_emulator():
    logger.debug('enumerating vbox targets')
    vbox_servers: list[VBoxSerever] = []
    for vboxcls in vbox_clsids:
        server = get_server(vboxcls.clsid)
        if server:
            logger.debug(f"enumerating vbox {server}")
            vbox_servers.append(VBoxSerever(vboxcls.clsid, vboxcls.vendor, vboxcls.tag, server))

    logger.debug(f'installed VirtualBox servers: {vbox_servers}')

    running_processes = {pid: win32_process.resolve_image_name(pid) for pid in win32_process.all_pids()}
    # logger.debug(f'running processes: {running_processes}')
    for pid, path in running_processes.items():
        # logger.debug(f'running_processes: {pid, path}')
        for vbox_server in vbox_servers:
            if vbox_server.path == path:
                vbox_server.pid = pid
                logger.debug(f'found vbox server: {vbox_server} {pid, path}')
                break
    running_servers = [x for x in vbox_servers if x.pid]
    # running_servers = [x for x in vbox_servers if x[3] in running_processes]

    logger.debug(f'running VirtualBox servers: {running_servers}')
    results = []
    try:
        for server in running_servers:
            logger.debug(f'checking {server}')
            hproc = OpenProcess(PROCESS_QUERY_INFORMATION, False, server.pid)
            if not hproc:
                logger.debug(f'try OpenProcess failed for PID {server.pid}')
                continue
            CloseHandle(hproc)
            logger.debug(f'checking hproc end {server}')

            client = win32com.client.Dispatch(server.clsid)
            for machine in client.Machines:
                machine_name = machine.Name
                logger.debug(f'checking machine {machine_name}')
                if not machine.State == 5:
                    # machine is not running
                    continue
                for adapter_id in range(4):
                    adapter = machine.GetNetworkAdapter(adapter_id)
                    if adapter.Enabled and adapter.AttachmentType == 1:
                        # adapter is enabled and attached to per-machine NAT
                        forwards = adapter.NatEngine.Redirects
                        for forward in forwards:
                            rule_name, proto, host, port, guest_host, guest_port = forward.split(',', 5)
                            if proto == '1' and guest_port == '5555':
                                address = f'127.0.0.1:{port}'
                                identifier = f'vbox:{server.tag}:{machine_name}'
                                logger.debug(
                                    f'adb_server, None, {server.vendor}: {machine_name}, {address}, 2, 1, override_identifier={identifier}')
                                results.append(
                                    ADBControllerTarget(None, f'{server.vendor}',
                                                        address, 2, 1, override_identifier=identifier,
                                                        preload_device_info={'emulator_hypervisor': 'vbox'}))
            logger.debug(f'try checking {server}')
    except Exception as e:
        logger.error(f'failed to check server :{server} {e}', e)
    return results


def _main():
    logger.config({'debug': True})
    adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
    for x in installed_emulator():
        logger.debug(f'installed emulators {x}')
        adb.connect(x.adb_address)

    logger.debug(adb.device_list())
    for device in adb.device_list():
        logger.debug(device.shell('settings get secure android_id'))
        logger.debug(f'{device.info}')


if __name__ == '__main__':
    _main()
