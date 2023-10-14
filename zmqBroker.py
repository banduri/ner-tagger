#!/usr/bin/env python
"""

   Simple message queuing broker
   Same as request-reply broker but using ``zmq.proxy``

   Author: Guillaume Aubert (gaubert) <guillaume(dot)aubert(at)gmail(dot)com>
           Alexander Kasper (asklepios) <asklepios(at)riseup(dot)net>
            (logging and argparse)
"""


import zmq
import logging
import argparse

# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass


def main(args):
    """ main method """

    context = zmq.Context()

    # Socket facing clients
    frontend = context.socket(zmq.ROUTER)
    frontend.bind(args.frontendsocket)
    LOGGER.info("(Router) Frontend open on: %s",args.frontendsocket)

    # Socket facing services
    backend  = context.socket(zmq.DEALER)
    backend.bind(args.backendsocket)
    LOGGER.info("(Dealer) Backend open on: %s",args.backendsocket)

    LOGGER.info("Connecting Frontend and Backend.")
    zmq.proxy(frontend, backend)

    # We never get here...
    frontend.close()
    backend.close()
    context.term()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
zmq-broker/proxy. accepts zmq-requests on the fronted side and forwards them to the zmq-response-servers that connected on the backendside. Does a roundrobin if more then one backend is connected. 
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

