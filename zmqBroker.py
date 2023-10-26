#!/usr/bin/env python

import logging
import argparse

import zmq

from zmq.eventloop.zmqstream import ZMQStream

from tornado.ioloop import IOLoop

# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass


class LRUQueue(object):
    """LRUQueue class using ZMQStream/IOLoop for event dispatching"""

    def __init__(self, backend_socket, frontend_socket):
        self.available_workers = 0
        self.is_workers_ready = False
        self.workers = []

        self.backend = ZMQStream(backend_socket)
        self.frontend = ZMQStream(frontend_socket)
        self.backend.on_recv(self.handle_backend)

        self.loop = IOLoop.instance()

    def handle_backend(self, msg):
        # Queue worker address for LRU routing
        worker_addr, empty, client_addr = msg[:3]

        # add worker back to the list of workers
        self.available_workers += 1
        self.is_workers_ready = True
        self.workers.append(worker_addr)
        LOGGER.debug("available workers: %s",str(self.workers))
        #   Second frame is empty
        assert empty == b""

        # Third frame is READY or else a client reply address
        # If client reply, send rest back to frontend
        if client_addr != b"READY":
            empty, reply = msg[3:]

            # Following frame is empty
            assert empty == b""

            self.frontend.send_multipart([client_addr, b'', reply])


        if self.is_workers_ready:
            # when atleast 1 worker is ready, start accepting frontend messages
            self.frontend.on_recv(self.handle_frontend)

    def handle_frontend(self, msg):
        # Now get next client request, route to LRU worker
        # Client request is [address][empty][request]
        client_addr, empty, request = msg

        assert empty == b""

        #  Dequeue and drop the next worker address
        self.available_workers -= 1
        worker_id = self.workers.pop()
        LOGGER.debug("using worker: %s",str(worker_id))

        self.backend.send_multipart([worker_id, b'', client_addr, b'', request])
        if self.available_workers == 0:
            # stop receiving until workers become available again
            self.is_workers_ready = False
            self.frontend.stop_on_recv()

def main(args):
    """ main method """

    context = zmq.Context()

    # Socket facing clients
    frontend = context.socket(zmq.ROUTER)
    frontend.bind(args.frontendsocket)
    LOGGER.info("(Router) Frontend open on: %s",args.frontendsocket)

    # Socket facing services
    backend  = context.socket(zmq.ROUTER)
    backend.bind(args.backendsocket)
    LOGGER.info("(Dealer) Backend open on: %s",args.backendsocket)

    LOGGER.info("Connecting Frontend and Backend.")
    queue = LRUQueue(backend, frontend)

    # start reactor
    IOLoop.instance().start()
    

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

    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    
    main(args)

