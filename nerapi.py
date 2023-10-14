#!/usr/bin/env python
import locale
import argparse
import uuid
import json
import logging

import torch
from ner_tagger import LOGGER, StandaloneApplication, create_app

# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
provides a REST-API, that accepts json-requests at '/api/ner' in the form '{"text": "<text>"}' and
returns the NamedEntitie-Tags. (it finds 'important' words). Longer texts are split on sentences.
a cache-file is created to keep CPU/GPU-Usage low. It is not designed to do parallel processing,
also multiple requests are accepted but they are processed in order of arrival.
the '/api/nernosplit' endpoint will try to process the text without splitting at the cost of high (V)RAM usage.
        """,
        epilog = """
        """)
    parser.add_argument('--log', type = str,
                        choices=['debug','info','warning','error','critical'], 
                        default='warning',
                        help = 'set the loglevel')
    parser.add_argument('--host', type = str,
                        default = "localhost",
                        help = "tcp-bind to this hostname - use '[::]' to bind to everything")
    parser.add_argument('--port', type = int,
                        default = 8000,
                        help = 'tcp-bind to this portnumber')
    parser.add_argument('--zmqcachesocket', type = str,
                        default = "ipc:///tmp/cache.ipc",
                        help = "the socket of the cacheserver")
    parser.add_argument('--zmqmodelsocket', type = str,
                        default = "tcp://127.0.0.1:5559",
                        help = "the socket of the model-server or broker")
    parser.add_argument('--maxnosplit', type = int,
                        default = 50000,
                        help = "the maximum length of the text when using the nosplit endpoint. if the size is exceded the split (default) endpoint will be used. large text will lead high vRAM usage and workers may not like that.")
    parser.add_argument('--disablecache', action='store_true',
                        help = "disable the usage of a cache")
    parser.add_argument('--workers', type = int,
                        default = 3,
                        help = "the amount of gunicorn workers")
    parser.add_argument('--workertimeout', type = int,
                        default = 30,
                        help = "how long to wait for a worker to finish the request. if on cpu you may set it to 0 to disable any timeouts")

    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    # configuration is done - lets load the app and create the server

    LOGGER.info("creating app")
    app = create_app(parser.description,args)

    # https://docs.gunicorn.org/en/stable/settings.html
    options = {
        'bind': '%s:%d' % (args.host, args.port),
        'workers': args.workers,
        'timeout': args.workertimeout,
        'access-logfile': '-', # stdout
        'disable-redirect-access-to-syslog': 'True', # stdout is fine, to forward to syslog
        'errorlog': '-', # also stdout
        'loglevel': args.log
        
    }
    LOGGER.info("starting Server")
    StandaloneApplication(app, options).run()
