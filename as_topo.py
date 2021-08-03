#!/usr/bin/python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel, info, debug
from mininet.node import Host, OVSSwitch

import contextlib
import json
import os
import io
import tempfile

QUAGGA_DIR = '/usr/lib/quagga'
# Must exist and be owned by quagga user (quagga:quagga by default on Ubuntu)
QUAGGA_RUN_DIR = '/var/run/quagga'
EXABGP_RUN_EXE = '/home/mininet/exabgp/sbin/exabgp'
CONFIG_DIR = 'configs/'
ZEBRA_CMD = "/usr/lib/quagga/zebra"
BGPD_CMD = "/usr/lib/quagga/bgpd"

def quaggaFile(as_num, id_num, prefix, neighbors):
    ip = ".".join([*prefix.split("/")[0].split(".")[:3], "3"])
    id_num += 1
    text = (
f"""
!
hostname bgp
password sdnip
!
!
router bgp {as_num}
    bgp router-id {id_num}.{id_num}.{id_num}.{id_num}
    network {prefix}
""" + \
f"    neighbor {ip} remote-as {as_num}\n" + \
"".join([f"    neighbor {n['ip']} remote-as {n['as']}\n" for n in neighbors])
+"""!

log stdout
"""
)
    filename = f"/tmp/{as_num}.quagga"
    f = open(filename, "w")
    f.write(text)
    f.close()
    return filename

def zebraFile(as_num):
    text = (
f"""
! Configuration for zebra (NB: it is the same for all routers)
!
hostname zebra 
password sdnip
log stdout
"""
)
    filename = f"/tmp/{as_num}.zebra"
    f = open(filename, "w")
    f.write(text)
    f.close()
    return filename

class Controller(Host):

    def __init__(self, name, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))

class L2Switch(OVSSwitch):

    def start(self, controllers):
        return OVSSwitch.start(self, [])

class QuaggaRouter(Host):

    def __init__(self, name, quaggaConfFile, zebraConfFile, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.quaggaConfFile = quaggaConfFile
        self.zebraConfFile = zebraConfFile
        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))
                self.cmd(f'iptables -t nat -A POSTROUTING -o {intf} -j MASQUERADE')
                self.cmd(f'iptables -A FORWARD -i {intf} -j ACCEPT')

        self.cmd(f'{ZEBRA_CMD} -d -f %s -z %s/zebra%s.api -i %s/zebra%s.pid' %
                 (self.zebraConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))
        self.cmd(f'{BGPD_CMD} -d -f %s -z %s/zebra%s.api -i %s/bgpd%s.pid' %
                 (self.quaggaConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))

    def terminate(self):
        self.cmd("ps ax | egrep 'bgpd%s.pid|zebra%s.pid' | awk '{print $1}' | xargs kill" % (
            self.name, self.name))

        Host.terminate(self)

class ExaBGPRouter(Host):

    def __init__(self, name, exaBGPconf, intfDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.exaBGPconf = exaBGPconf
        self.intfDict = intfDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            for addr in attrs['ipAddrs']:
                self.cmd('ip addr add %s dev %s' % (addr, intf))

        self.cmd('%s %s > /dev/null 2> exabgp.log &' % (EXABGP_RUN_EXE, self.exaBGPconf))

    def terminate(self):
        self.cmd(
            "ps ax | egrep 'lib/exabgp/application/bgp.py' | awk '{print $1}' | xargs kill")
        self.cmd(
            "ps ax | egrep 'server.py' | awk '{print $1}' | xargs kill")
        Host.terminate(self)


class L2Switch(OVSSwitch):

    def start(self, controllers):
        return OVSSwitch.start(self, [])


class Topo(Topo):

    def build(self):
        topopath = "./topos/as_topo.json"
        topo = json.loads(open(topopath, "r").read())
        interfaces, quaggas, routers, exabgps = {}, {}, {}, {}
        links = []

        # Create interfaces as quagga info for links
        for n_links, link in enumerate(topo["links"]):
            interfaces[link["peer1"]] = interfaces.get(link["peer1"], {})
            interfaces[link["peer2"]] = interfaces.get(link["peer2"], {})
            
            new_link = {
                "peer1": link["peer1"], 
                "peer2": link["peer2"],
                "port1": len(interfaces[link["peer1"]]),
                "port2": len(interfaces[link["peer2"]]),
            }
            links += [new_link]

            ip1 = f"{150}.{n_links%256}.1.1/16"
            ip2 = f"{150}.{n_links%256}.1.2/16"

            interfaces[link["peer1"]] = {
                **interfaces[link["peer1"]], 
                f"R{link['peer1']}-eth{new_link['port1']}": {
                    "ipAddrs": [
                        ip1,
                    ]
                },
            }
            interfaces[link["peer2"]] = {
                **interfaces[link["peer2"]], 
                f"R{link['peer2']}-eth{new_link['port2']}": { 
                    "ipAddrs": [
                        ip2,
                    ]
                },
            }

            quaggas[link["peer1"]] = quaggas.get(link["peer1"], [])
            quaggas[link["peer2"]] = quaggas.get(link["peer2"], [])

            quaggas[link["peer1"]] = [
                *quaggas[link["peer1"]], 
                {
                    "ip": ip2.split("/")[0],
                    "as": topo["ASes"][link["peer2"]]["as"],
                }
            ]

            quaggas[link["peer2"]] = [
                *quaggas[link["peer2"]], 
                {
                    "ip": ip1.split("/")[0],
                    "as": topo["ASes"][link["peer1"]]["as"],
                }
            ]
           
        # Create ASes
        bgpcount = 0
        for as_cnt, (as_name, as_dict) in enumerate(topo["ASes"].items()):
            router_ip = f"{'.'.join([*as_dict['prefix'].split('/')[0].split('.')[:3], '1']) + '/8'}"

            # Add router
            zebraConf = zebraFile(as_dict["as"])
            quaggaConf = quaggaFile(as_dict["as"], as_cnt, as_dict["prefix"], quaggas[as_name])
            ifaces = {
                **interfaces[as_name],
                f"R{as_name}-eth{len(interfaces[as_name])}": {
                    "ipAddrs": [
                        router_ip,
                    ]
                },
            }
            r = self.addHost(f"R{as_name}", cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                    zebraConfFile=zebraConf, intfDict=ifaces)
            routers[r] = ifaces

            # Set up ExaBGP
            if as_dict["type"] == "m" or as_dict["type"] == "x":
                bgpcount += 1
                local_ip = ".".join([*as_dict["prefix"].split("/")[0].split(".")[:-1], "3"])
                exabgp_interfaces = {
                    f"{as_name}-exabgp-eth0": { 
                        "ipAddrs": [
                            f"192.168.{bgpcount}.2/24",
                        ]
                    },
                    f"{as_name}-exabgp-eth1": { 
                        "ipAddrs": [
                            f"{local_ip}/8"
                        ]
                    },
                }
            
                name = f"{as_name}-exabgp"
                exabgp = self.addHost(name, cls=ExaBGPRouter,
                                      exaBGPconf=f'%s{as_dict["exabgp"]}' % CONFIG_DIR,
                                      intfDict=exabgp_interfaces)
                exabgps[name] = exabgp_interfaces

        # Add switch
        linkcnt = 1
        l2switch = self.addSwitch(f"{as_name}-l2switch", failMode="standalone", dpid="0000000000000001", cls=L2Switch)
        for devtype in [routers, exabgps]:
            for name, ifs in devtype.items():
                self.addLink(l2switch, name, port1=linkcnt, port2=len(ifs) - 1)
                linkcnt += 1

        # Inter-AS connections
        for link in links:
            self.addLink(f"R{link['peer1']}", f"R{link['peer2']}", link["port1"], link["port2"])

        # Controller
        controller_dict = {
            f"controller-eth{n}": { 
                "ipAddrs": [
                    f"192.168.{n+1}.1/24",
                ]
            } for n in range(len(exabgps))
        }
        self.addHost("controller", cls=Controller, intfDict=controller_dict)

        # Controller connections
        for n, (exabgp_name, _) in enumerate(exabgps.items()): 
            self.addLink("controller", exabgp_name, n, 0)


topos = {'smalltopo': Topo}

if __name__ == '__main__':
    setLogLevel('debug')
    topo = Topo()

    net = Mininet(topo=topo, build=False)
    net.build()
    net.start()

    CLI(net)

    net.stop()

    info("done\n")
