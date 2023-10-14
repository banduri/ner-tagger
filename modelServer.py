#!/usr/bin/env python

import logging
import argparse
import uuid
import json
from collections import defaultdict

import zmq

import flair
from flair.data import Span
from flair.nn import Classifier
from flair.data import Sentence

import torch


# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass

def preparejson(data):
    result = {}
    if data:
        data = dict(data)
    else:
        data={}
    for i in data.keys():
        result[i] = list(data[i])
    return result

def main(args):
    model = None
    
    # limit number of threads
    if args.threads > 0:
        torch.set_num_threads(args.threads)
        torch.set_num_interop_threads(args.threads)

    LOGGER.debug("Setting device")
    device = torch.device('cpu')
    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device('cuda')
    else:
        device = torch.device(args.device)
    flair.device = device
    LOGGER.info("Device set to %s",str(device))

    LOGGER.info("Loading model")
    try:
        model = Classifier.load(args.model)
    except Exception as excep:
        LOGGER.critical("Failed to load model: %s",str(excep))
        return

    LOGGER.debug("connecting to zmq-broker")

    socket = None
    try:
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.connect(args.zmqsocket)
    except Exception as excep:
        LOGGER.critical("Could not connect to zmq-broker:%s",str(excep))
        return

    while True:
        sentence = None
        result = defaultdict(set)
        jmsg = None
        
        message = socket.recv()
        
        try:
            jmsg = json.loads(message.decode("utf-8"))
        except Exception as excep:
            LOGGER.warning("could not decode json message from socket: %s",str(excep))
            socket.send(json.dumps({
                "result": None,
                "error": "could not decode json message from socket"
            }).encode('utf-8'))
            continue

        if 'text' in jmsg:
            try:
                sentence = Sentence(jmsg['text'])
            except Exception as excep:
                LOGGER.warning("could not create datastructure for model: %s",str(excep))
                socket.send(json.dumps({
                    "result": None,
                    "error": "could not create (internal) datastructure for model"
                }).encode('utf-8'))
                continue
        else:
            LOGGER.warning("skipping: no text in message")
            socket.send(json.dumps({
                "result": None,
                "error": "no text in message"
            }).encode('utf-8'))
            
            continue

        LOGGER.info("starting prediction:")
        try:
            model.predict(sentence)
        except Exception as excep:
            LOGGER.warning("predition failed: %s",str(excep))
            socket.send(json.dumps({
                "result": None,
                "error": "prediction failed - check server"
            }).encode('utf-8'))
            
        LOGGER.info("done prediction")

        # flair-specific data-structure - reorder it a bit

        for span in sentence.get_spans():
            # filter out low confidence
            span = span.to_dict()
            if span['labels'][0]['confidence'] < 0.95:
                continue

            result[span['labels'][0]['value']].add(span['text'])
        result = preparejson(result)
        socket.send(json.dumps({
            "result": result,
            "error": None
        }).encode('utf-8'))
        # drop the cuda-cache
        if not args.keepcudacache and torch.cuda.is_available():
            torch.cuda.empty_cache()
            LOGGER.info("cleared cudacache")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
provides a model prediction via zmq. it accepts json in the form: { "text" "<text>" }
it returns a json-string with the result of the model-prediction: { "result": <data|null>, "error": <msg|null> }
the program connects to a zmq-'broker'/proxy on the specific socket. It does not provide
a socket on its own.

if "error" is not "null" something happend to the model and the "null"-result is provided. 
        
        
        """,
        epilog = """
        """)
    parser.add_argument('--log', type = str,
                        choices=['debug','info','warning','error','critical'], 
                        default='warning',
                        help = 'set the loglevel')

    parser.add_argument('--threads', type = int,
                        default = 0,
                        help = "limit the amount of CPU-threads that can be used; 0 is equivalent to the number of CPUs in the system")
    parser.add_argument('--device', type = str,
                        choices=['auto','cpu','cuda','cuda:0','cuda:1'], 
                        default = "auto",
                        help = "define where to run. Defaults to 'cuda' if available 'cpu' otherwise")

    parser.add_argument('--model', type = str,
                        default = "models/ner-english-ontonotes-large.bin",
                        help = "which model to use - to download other check downloadscript and flairdocumentation")

    parser.add_argument('--zmqsocket', type = str,
                        default = "tcp://localhost:5560",
                        help = "where to find the zmq-proxy/broker to register as worker")

    parser.add_argument('--keepcudacache', action="store_true",
                        help = "keep the cachedata on the cuda-device. default is to drop the cache after prediction to free no longer used memory on the device")
    
    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    
    main(args)
    