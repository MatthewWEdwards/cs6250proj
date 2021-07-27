#!/usr/bin/python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel, info, debug
from mininet.node import Host, OVSSwitch

import json
import os

QUAGGA_DIR = '/usr/lib/quagga'
# Must exist and be owned by quagga user (quagga:quagga by default on Ubuntu)
QUAGGA_RUN_DIR = '/var/run/quagga'
EXABGP_RUN_EXE = '/home/mininet/exabgp/sbin/exabgp'
CONFIG_DIR = 'configs/'
ZEBRA_CMD = "/usr/lib/quagga/zebra"
BGPD_CMD = "/usr/lib/quagga/bgpd"

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
        topopath = "./topos/small_topo.json"
        topo = json.loads(open(topopath, "r").read())
        
        for as_name, as_dict in topo["ASes"].items():
            routers, hosts, exabgps = {}, {}, {}

            # Add routers and BGP monitors
            for router_name, router_attrs in as_dict["routers"].items():
                zebraConf = f"%s{router_attrs['zebra']}" % CONFIG_DIR
                quaggaConf = f"%s{router_attrs['quagga']}" % CONFIG_DIR
                r = self.addHost(router_name, cls=QuaggaRouter, quaggaConfFile=quaggaConf,
                        zebraConfFile=zebraConf, intfDict=router_attrs["netifs"])
                routers[r] = router_attrs

                if "bgp" in as_dict.keys():
                    # Set up BGP monitors
                    name = f"{as_name}-exabgp"
                    exabgp = self.addHost(name, cls=ExaBGPRouter,
                                          exaBGPconf='%sexabgp.conf' % CONFIG_DIR,
                                          intfDict=as_dict["bgp"]["netifs"])
                    exabgps[name] = as_dict["bgp"]

            # Add hosts
            hosts = {}
            for host_name, host_attrs in as_dict["hosts"].items():
                h = self.addHost(host_name, 
                        ip=host_attrs["ip"], 
                        defaultRoute=f"via {host_attrs['defaultRoute']}")
                hosts[host_name] = host_attrs

            # Add switch
            linkcnt = 1
            l2switch = self.addSwitch(f"{as_name}-l2switch", failMode="standalone", dpid="0000000000000001", cls=L2Switch)
            for devtype in [routers, exabgps, hosts]:
                for name, attrs in devtype.items():
                    if "switch" in attrs.keys():
                        self.addLink(l2switch, name, port1=linkcnt, port2=attrs["switch"])
                        linkcnt += 1
        # Controller
        self.addHost("controller", cls=Controller, intfDict=topo["controller"]["netifs"])

        # Inter-AS connections
        for link in topo["links"]:
            self.addLink(link["dev1"], link["dev2"], link["port1"], link["port2"])



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
