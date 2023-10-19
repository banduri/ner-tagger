#!/usr/bin/env python
import locale
import argparse
import uuid
import json
import logging

import torch
from ner_tagger import LOGGER, StandaloneApplication, create_app, middleware, sentsplitter



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
    parser.add_argument('--zmqsplitsocket', type = str,
                        default = "tcp://127.0.0.1:5561",
                        help = "the socket to the frontend of the 'split-zmqbroker'.")
    parser.add_argument('--zmqmiddlewaresocket', type = str,
                        default = "tcp://127.0.0.1:5563",
                        help = "the socket to the frontend of the 'middleware-zmqbroker'.")
    parser.add_argument('--splitlang', type = str,
                        default = "german",
                        help = "language to assume for splitting text into sentences. needs the nltk-networks. currently only german and english. ")
    parser.add_argument('--maxnosplit', type = int,
                        default = 500,
                        help = "the maximum length of the text when using the nosplit endpoint. if the size is exceded the split (default) endpoint will be used. large text will lead high vRAM usage and workers may not like that.Also the model may not beeing trained on long context.")
    parser.add_argument('--disablecache', action='store_true',
                        help = "disable the usage of a cache")
    parser.add_argument('--middleware', type = str,
                        default = 'nertagger',
                        choices=list(middleware.keys()),
                        help = 'the kind of postprocessing of the modeldata. sentiment creates the avg-score of multiple sentences. nertagger removes information about position and groups by NER-Type')
    parser.add_argument('--sentimentpositiv', type = str, nargs='+',
                        default = ["OTHER","POSITIV"],
                        help = "if a sentiment-middleware and a sentiment model is used consider this as 'nice' labels")
    parser.add_argument('--sentimentnegativ', type = str, nargs='+',
                        default = ["NEGATIV","OFFENSE"],
                        help = "if a sentiment-middleware and a sentiment model is used consider this as 'bad' labels")
    parser.add_argument('--nerthreshold', type = float,
                        default = 0.95,
                        help = 'every NER-Tag produced by the model comes with a confidence. with the nertaggermiddleware enabled, labes with a confidence lower then this value are ignored and filted out.')
    parser.add_argument('--sentsplitter', type = str,
                        default = 'nltk',
                        choices=list(sentsplitter.keys()),
                        help = 'how to split paragraphs into sentences. nltk is rather fast an does not use much memory, while zmq tries to connect to a zmq-broker given parameter zmqsplitsocket.')
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
