#!/usr/bin/env python

import logging
import argparse
import json
from collections import defaultdict

import zmq

import spacy

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


def middleware(data, model, args):
    processdata = defaultdict(set)
    result = {}
    pipedata = []
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]

    for datapoint in data:
        if 'entities' in datapoint and len(datapoint['entities']) > 0 and isinstance(datapoint['entities'],list):
            for e in datapoint['entities']:
                confidence = e['labels'][0]['confidence']
                label = e['labels'][0]['value']
                if confidence >= args.threshold:
                    # the order is of no use
                    pipedata.append((e['text'],{'label': label}))


    # process via space-pipe
    #                     doc = model(e['text'])
    LOGGER.info("Got %d Entries to process",int(len(pipedata)))
    #docs = list(model.pipe(list(pipedata)))
    for doc, context in model.pipe(pipedata, as_tuples=True):
        text = []
        for token in doc:
            # filter out german artikels like 'der die das', adjektive 
            if token.tag_ not in ["ART"]:
                text.append(token.lemma_)
        text = " ".join(text)        
        processdata[context['label']].add(text)
                

    # make everything a list again
    for key,value in processdata.items():
        result[key] = list(value)

    return result

def main(args):
    model = None
    socket = None

    LOGGER.debug("Setting device")

    if args.device == "auto":
        spacy.prefer_gpu(args.deviceid)        
    elif args.device == "cpu":
        spacy.require_cpu()
    elif args.device == "gpu":
        spacy.require_gpu(args.deviceid)

    LOGGER.info("Device set to %s",str(args.device))

    LOGGER.info("Loading model")
    try:
        model = spacy.load(args.model, disable=["ner"])
    except Exception as excep:
        LOGGER.critical("Failed to load model: %s",str(excep))
        return

    LOGGER.debug("connecting to zmq-broker")


    try:
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.connect(args.zmqsocket)
    except Exception as excep:
        LOGGER.critical("Could not connect to zmq-broker:%s",str(excep))
        return

    while True:
        sentence = None
        result = []
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

        if 'data' not in jmsg:
            LOGGER.warning("skipping: no data in message")
            socket.send(json.dumps({
                "result": None,
                "error": "no data in message"
            }).encode('utf-8'))
            
            continue

        LOGGER.info("starting processing:")
        data = jmsg['data']
        try:
            result = middleware(jmsg['data'], model, args)
        except Exception as excep:
            LOGGER.warning("predition failed: %s",str(excep))
            socket.send(json.dumps({
                "result": None,
                "error": "prediction failed - check server"
            }).encode('utf-8'))
            
        LOGGER.info("done prediction")

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
provides a spacy-sentence-splitmodel prediction via zmq. it accepts json in the form: { "text" "<text>" }
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

    parser.add_argument('--device', type = str,
                        choices=['auto','cpu','gpu'], 
                        default = "auto",
                        help = "define where to run. Defaults to 'gpu' if available 'cpu' otherwise")
    parser.add_argument('--deviceid', type = int,
                        default = 0,
                        help = "define which deviceid to use - other frameworks use 'cuda:0' to force the device")

    parser.add_argument('--model', type = str,
                        default = "./models/de_dep_news_trf.bin", # de_core_news_lg
                        help = "which model to use - needs to be installed via pip - check https://spacy.io/usage to download models for your hardware/language")
    parser.add_argument('--threshold', type = float,
                        default = 0.95,
                        help = 'every NER-Tag produced by the model comes with a confidence. with the nertaggermiddleware enabled, labes with a confidence lower then this value are ignored and filted out.')

    parser.add_argument('--zmqsocket', type = str,
                        default = "tcp://localhost:5562",
                        help = "where to find the zmq-proxy/broker to register as worker")

    parser.add_argument('--keepcudacache', action="store_true",
                        help = "keep the cachedata on the cuda-device. default is to drop the cache after prediction to free no longer used memory on the device")
    
    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    
    main(args)
    
