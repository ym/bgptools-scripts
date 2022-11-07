#!/usr/bin/env python3
from typing import TypedDict

from os import environ
from sys import exit
from argparse import ArgumentParser
from netaddr import IPNetwork, IPAddress
from requests import Session
from urllib.parse import urljoin


class MACAddressEntry(TypedDict):
    mac: str
    ip: str


class ARPEntry(TypedDict):
    port_id: int
    mac_address: str
    ipv4_address: str


def format_mac_address(s: str):
    return ':'.join([s[i: i + 2] for i in range(0, len(s), 2)])


def dedup_mac_addresses(macs: list[ARPEntry]) -> list[MACAddressEntry]:
    ret: dict = {}
    for e in macs:
        ret[e['ipv4_address']] = e['mac_address']

    return [
        {'mac': format_mac_address(mac), 'ip': ip}
        for ip, mac in ret.items()
    ]


class IXPMACTool(object):
    port_cache: dict = None
    port_ip_cache: dict = {}

    peeringdb_url: str = 'https://peeringdb.com/api/'
    librenms_url: str
    librenms_token: str

    def __init__(self, librenms_url: str, librenms_token: str):
        self.librenms_url = librenms_url
        self.librenms_token = librenms_token

        self.r = Session()

    def __get_librenms(self, path: str, params: dict = None):
        return self.r.get(
            urljoin(self.librenms_url, f'/api/v0/{path}'),
            headers={'X-Auth-Token': self.librenms_token},
            params=params,
        )

    def __get_peeringdb(self, path: str, params: dict = None):
        r = self.r.get(
            urljoin(self.peeringdb_url, path),
            params=params,
        )
        r.raise_for_status()
        return r

    def get_mac_addresses_by_prefix(self, prefix: IPNetwork):
        ret = []
        result = self.__get_librenms(
            f'resources/ip/arp/{prefix}'
        ).json()
        for entry in result['arp']:
            address = IPAddress(entry['ipv4_address'])
            if address not in prefix:
                print("WARN: Skipping {} as it is not in {}".format(address, prefix))
                continue
            ret.append(entry)
        return ret

    def get_ports(self):
        if not self.port_cache:
            result = self.__get_librenms(
                'ports',
                params={'columns': 'ifName,port_id,ifPhysAddress'},
            ).json()['ports']
            self.port_cache = {port['port_id']: port for port in result}
        return self.port_cache

    def get_port(self, port_id: int):
        ports = self.get_ports()
        if port_id not in ports:
            raise Exception(f'Port {port_id} not found')
        return ports[port_id]

    """
    Get all IP addresses for a given port
    """

    def get_port_addresses(self, port_id: int):
        if port_id not in self.port_ip_cache:
            self.port_ip_cache[port_id] = self.__get_librenms(
                f'ports/{port_id}/ip',
            ).json()['addresses']
        return self.port_ip_cache[port_id]

    """
    This is to get the MAC addresses of own Peering IPs
    (FDB / ARP table won't include them)
    """

    def fetch_device_ports_mac_addresses(self, results: list[ARPEntry]) -> list[ARPEntry]:
        ret: list[ARPEntry] = []

        # remove duplicates
        ports = set([
            result['port_id'] for result in results
        ])

        for port_id in ports:
            port = self.get_port(port_id)
            addresses = self.get_port_addresses(port_id)
            for address in addresses:
                if 'ipv4_address' not in address:
                    continue
                ret.append({
                    'mac_address': port['ifPhysAddress'],
                    'ipv4_address': address['ipv4_address'],
                    'port_id': port_id,
                })

        return ret

    """
    Get all peering prefixes for given ASNs
    """

    def get_peering_prefixes(self, asns: set[int]) -> list[IPNetwork]:
        ixlan_ids = set()
        prefixes = set()

        for net in self.__get_peeringdb('net', params={
            'asn__in': ','.join([str(asn) for asn in asns]),
            # to include IXLAN IDs
            'depth': 2,
        }).json()['data']:
            for ixlan in net['netixlan_set']:
                ixlan_ids.add(ixlan['ixlan_id'])

        print("Found {} IXLAN IDs.".format(len(ixlan_ids)))

        for ixpfx in self.__get_peeringdb('ixpfx', params={
            'ixlan_id__in': ','.join([str(ixlan_id) for ixlan_id in ixlan_ids]),
        }).json()['data']:
            # exclude IPv6 prefixes
            if ixpfx['protocol'] != 'IPv4':
                continue
            # exclude prefixes that are not in DFZ (e.g. RFC1918 space)
            if not ixpfx['in_dfz']:
                continue
            prefixes.add(ixpfx['prefix'])

        print("Found {} IX prefixes.".format(len(prefixes)))

        return [
            IPNetwork(prefix) for prefix in prefixes
        ]

    def send_to_bgptools(self, endpoint: str, macs: list[MACAddressEntry]):
        r = self.r.post(endpoint, json=macs)
        r.raise_for_status()
        return r.text


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('asn', nargs='+')
    args = parser.parse_args()
    for e in ['LIBRENMS_TOKEN', 'LIBRENMS_URL', 'BGPTOOLS_ENDPOINT']:
        if e not in environ:
            print(f'ERROR: {e} is not set')
            exit(1)

    asns = set([int(asn) for asn in args.asn])

    t = IXPMACTool(
        librenms_token=environ['LIBRENMS_TOKEN'],
        librenms_url=environ['LIBRENMS_URL']
    )

    prefixes = t.get_peering_prefixes(asns)

    print("Fetching MAC addresses from LibreNMS for peering prefixes...")
    mac_addresses: list[ARPEntry] = list()
    for prefix in prefixes:
        m = t.get_mac_addresses_by_prefix(prefix)
        for a in m:
            mac_addresses.append(a)
        print(f'Found {len(m)} MAC addresses in prefix {prefix}.')

    print("Fetching MAC addresses from LibreNMS for own IPs...")
    port_mac_addresses = t.fetch_device_ports_mac_addresses(mac_addresses)
    print(f'Found {len(port_mac_addresses)} MAC addresses.')
    mac_addresses.extend(port_mac_addresses)

    mac_addresses = dedup_mac_addresses(mac_addresses)
    print(f"Found {len(mac_addresses)} MAC addresses in total.")

    print("Sending to bgp.tools ...")
    t.send_to_bgptools(environ['BGPTOOLS_ENDPOINT'], mac_addresses)
