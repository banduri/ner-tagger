#!/usr/bin/env python

import logging
import argparse

from dataclasses import dataclass
from collections import OrderedDict

import time

import zmq

from zmq.eventloop.zmqstream import ZMQStream

from tornado.ioloop import IOLoop

# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


#  Paranoid Pirate Protocol constants
PPP_READY = b"\x01"      # Signals worker is ready
PPP_HEARTBEAT = b"\x02"  # Signals worker heartbeat


# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass


@dataclass
class Worker:
    """Class for keeping track of a Worker."""
    address: str
    heartbeatinterval: float = 2.0  # every two seconds as default
    heartbeatsliveness: int = 3 # try three times
    
    def __post_init__(self):
        self.expiry = time.time() + self.heartbeatinterval * self.heartbeatsliveness
        

        
        


class LRUQueue(object):
    """LRUQueue class for event dispatching an loadbalancing"""

    def __init__(self):
        self.queue =  OrderedDict()

    def ready(self, worker):
        self.queue.pop(worker.address, None)
        self.queue[worker.address] = worker

        
    def purge(self):
        """Look for & kill expired workers."""
        t = time.time()
        expired = []
        for address, worker in self.queue.items():
            if t > worker.expiry:  # Worker expired
                expired.append(address)
        for address in expired:
            self.queue.pop(address, None)        
        if len(expired) > 0:
            LOGGER.info("Idle worker(s) expired: %s",str(expired))
            LOGGER.info("%d Remaining aktiv Workers: %s",len(self.queue), str(list(self.queue)))

    def next(self):
        address, worker = self.queue.popitem(False)
        return address


    

def main(args):
    """ main method """

    context = zmq.Context()

    # Socket facing clients
    frontend = context.socket(zmq.ROUTER)
    frontend.bind(args.frontendsocket)
    LOGGER.info("Frontend open on: %s",args.frontendsocket)

    # Socket facing services
    backend  = context.socket(zmq.ROUTER)
    backend.bind(args.backendsocket)
    LOGGER.info("Backend open on: %s",args.backendsocket)

    LOGGER.info("Connecting Frontend and Backend.")

    poll_workers = zmq.Poller()
    poll_workers.register(backend, zmq.POLLIN)

    poll_both = zmq.Poller()
    poll_both.register(frontend, zmq.POLLIN)
    poll_both.register(backend, zmq.POLLIN)

    workers = LRUQueue()

    heartbeat_at = time.time() + args.heartbeatinterval

    while True:
        if len(workers.queue) > 0:
            poller = poll_both
        else:
            poller = poll_workers
        socks = dict(poller.poll(args.heartbeatinterval * 1000))

        # Send heartbeats to idle workers if it's time
        if time.time() >= heartbeat_at:
            LOGGER.debug("Heartbeat-Queue: %s",list(workers.queue))
            for worker in workers.queue:
                LOGGER.debug("sending heartbeat to worker: %s",str(worker))
                msg = [worker, PPP_HEARTBEAT]
                backend.send_multipart(msg)

            heartbeat_at = time.time() + args.heartbeatinterval

        # Handle worker activity on backend
        if socks.get(backend) == zmq.POLLIN:
            # Use worker address for LRU routing
            frames = backend.recv_multipart()
            if not frames:
                break

            address = frames[0]

            # Validate control message, or return reply to client
            msg = frames[1:]
            if len(msg) == 1:
                if msg[0] == PPP_READY:
                    workers.ready(Worker(address))
                    LOGGER.info("new Worker connected: %s - %d total", str(address),len(workers.queue))
                elif msg[0] == PPP_HEARTBEAT:
                    LOGGER.debug("Heartbeat from Worker: %s - refreshing", str(address))
                    workers.ready(Worker(address))
                else:
                    LOGGER.error("Invalid message from worker: %s", str(msg))
            else:
                # if a worker replies put it back into the queue
                workers.ready(Worker(address))
                frontend.send_multipart(msg)
                
                
        # forward frontend requests to worker
        if socks.get(frontend) == zmq.POLLIN:
            frames = frontend.recv_multipart()
            if not frames:
                break
            
            frames.insert(0, workers.next())
            backend.send_multipart(frames)


        # cycle complete - check for exipred workers
        workers.purge()
                
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
zmq-broker/proxy. accepts zmq-requests on the fronted side and forwards them to the zmq-response-servers that connected on the backendside. Does a LRU-Loadbalancing if more then one backend is connected. 
        """,
        epilog = """
        """)
    parser.add_argument('--log', type = str,
                        choices=['debug','info','warning','error','critical'], 
                        default='warning',
                        help = 'set the loglevel')

    parser.add_argument('--frontendsocket', type = str,
                        default = "tcp://127.0.0.1:5559",
                        help = "bind to this socket and wait for clients to connect. Use tcp://*:5559 to bind to every ip")

    parser.add_argument('--backendsocket', type = str,
                        default = "tcp://127.0.0.1:5560",
                        help = "bind to this socket and wait for servers to connect. Use tcp://*:5560 to bind to every ip")
    parser.add_argument('--heartbeatinterval', type = float,
                        default=2.0,
                        help = "interval of heartbeats for worker and clients in seconds")
    parser.add_argument('--heartbeatliveness', type = int,
                        default=3,
                        help="consider peer as dead after this amount of heartbeats")

    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    
    main(args)

