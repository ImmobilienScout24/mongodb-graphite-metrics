import commands
import time
import sys
from socket import socket

import argparse
from pymongo import Connection


class MongoDBGraphiteMonitor(object):

    def __init__(self):
        self._thisHost = commands.getoutput('hostname')
        self._args = self._parseCommandLineArgs()

    def _parseCommandLineArgs(self):
        parser = argparse.ArgumentParser(description='Creates graphite metrics for a single mongodb instance from administation commands.')
        parser.add_argument('-host', default=self._thisHost,
            help='host name of mongodb to create metrics from.')
        parser.add_argument('-prefix', default='DEV',
            help='prefix for all metrics.')
        parser.add_argument('-service', default='unspecified', required=True,
            help='service name the metrics should appear under.')
        parser.add_argument('-graphiteHost', required=True,
            help='host name for graphite server.')
        parser.add_argument('-graphitePort', required=True,
            help='port garphite is listening on.')
        return parser.parse_args()

    def _uploadToCarbon(self, metrics):
        now = int(time.time())
        lines = []

        for name, value in metrics.iteritems():
            if name.find('mongo') == -1:
                name = self._mongoHost.split('.')[0] + '.' + name
            lines.append(self._metricName + name + ' %s %d' % (value, now))

        message = '\n'.join(lines) + '\n'

        sock = socket()
        try:
            sock.connect((self._carbonHost, self._carbonPort))
        except:
            print "Couldn't connect to %(server)s on port %(port)d, is carbon-agent.py running?" % {'server': self._carbonHost, 'port': self._carbonPort}
            sys.exit(1)
            #print message
        sock.sendall(message)

    def _calculateLagTimes(self, replStatus, primaryDate):
        lags = dict()
        for hostState in replStatus['members']:
            lag = primaryDate - hostState['optimeDate']
            hostName = hostState['name'].lower().split('.')[0]
            lags[hostName + ".lag_seconds"] = '%.0f' % ((lag.microseconds + (lag.seconds + lag.days * 24 * 3600) * 10 ** 6) / 10 ** 6)
        return lags

    def _gatherReplicationMetrics(self):
        replicaMetrics = dict()
        replStatus = self._connection.admin.command("replSetGetStatus")

        for hostState in replStatus['members']:
            if hostState['stateStr'] == 'PRIMARY' and hostState['name'].lower().startswith(self._mongoHost):
                lags = self._calculateLagTimes(replStatus, hostState['optimeDate'])
                replicaMetrics.update(lags)
            if hostState['name'].lower().startswith(self._mongoHost):
                thisHostsState = hostState

        replicaMetrics['state'] = thisHostsState['state']
        return replicaMetrics

    def _gatherServerStatusMetrics(self):
        serverMetrics = dict()
        serverStatus = self._connection.admin.command("serverStatus")

        serverMetrics['lock.ratio'] = '%.5f' % serverStatus['globalLock']['ratio']
        serverMetrics['lock.queue.total'] = serverStatus['globalLock']['currentQueue']['total']
        serverMetrics['lock.queue.readers'] = serverStatus['globalLock']['currentQueue']['readers']
        serverMetrics['lock.queue.writers'] = serverStatus['globalLock']['currentQueue']['writers']

        serverMetrics['connections.current'] = serverStatus['connections']['current']
        serverMetrics['connections.available'] = serverStatus['connections']['available']

        serverMetrics['indexes.missRatio'] = '%.5f' % serverStatus['indexCounters']['btree']['missRatio']
        serverMetrics['indexes.hits'] = serverStatus['indexCounters']['btree']['hits']
        serverMetrics['indexes.misses'] = serverStatus['indexCounters']['btree']['misses']

        serverMetrics['cursors.open'] = serverStatus['cursors']['totalOpen']
        serverMetrics['cursors.timedOut'] = serverStatus['cursors']['timedOut']

        serverMetrics['mem.residentMb'] = serverStatus['mem']['resident']
        serverMetrics['mem.virtualMb'] = serverStatus['mem']['virtual']
        serverMetrics['mem.mapped'] = serverStatus['mem']['mapped']
        serverMetrics['mem.pageFaults'] = serverStatus['extra_info']['page_faults']

        serverMetrics['asserts.warnings'] = serverStatus['asserts']['warning']
        serverMetrics['asserts.errors'] = serverStatus['asserts']['msg']

        return serverMetrics


    def execute(self):
        self._carbonHost = self._args.graphiteHost
        self._carbonPort = int(self._args.graphitePort)

        self._mongoHost = self._args.host.lower()
        self._mongoPort = 27017
        self._connection = Connection(self._mongoHost, self._mongoPort)

        self._metricName = self._args.prefix + '.' + self._args.service + '.mongodb.'

        metrics = dict()
        metrics.update(self._gatherReplicationMetrics())
        metrics.update(self._gatherServerStatusMetrics())

        self._uploadToCarbon(metrics)


def main():
    MongoDBGraphiteMonitor().execute()

if __name__ == "__main__":
    main()