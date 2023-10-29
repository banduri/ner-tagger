#!/usr/bin/env python

import logging
import argparse
import json
from collections import defaultdict
from random import randint
import time

import zmq

import spacy

import torch


# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


#  Paranoid Pirate Protocol constants
PPP_READY = b"\x01"      # Signals worker is ready
PPP_HEARTBEAT = b"\x02"  # Signals worker heartbeat

# 
INTERVAL_INIT = 1
INTERVAL_MAX = 32

# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass

def setupMiddleware(args):
    model = None

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
    finally:
        return model

def setupSocket(args,poller, prefix=None):
    socket = None

    try:
        context = zmq.Context()
        if args.identityprefix:
            prefix = args.identityprefix
            
        LOGGER.debug("Getting zmq-context")
        socket = context.socket(zmq.DEALER)
        LOGGER.debug("Got zmq-context")
        identity = "%s-%04X-%04X" % (str(prefix), randint(0, 0x10000), randint(0, 0x10000))
        identity = identity.encode("utf-8")
        LOGGER.info("Setting identity: %s", identity.decode())
        socket.setsockopt(zmq.IDENTITY, identity)
        LOGGER.debug("register socket at poller")
        poller.register(socket, zmq.POLLIN)
        LOGGER.debug("connecting to zmq-broker at: %s", args.zmqsocket)

        socket.connect(args.zmqsocket)
        LOGGER.info("announcing myself to Broker as: %s" %(identity.decode()))
        socket.send(PPP_READY)

    except Exception as excep:
        LOGGER.critical("Could not connect to zmq-broker:%s",str(excep))
        raise excep

    finally:
        return socket


def doMiddleware(model, data, args):
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
                
    # drop the cuda-cache
    if not args.keepcudacache and torch.cuda.is_available():
        torch.cuda.empty_cache()
        LOGGER.debug("cleared cudacache")

    # make everything a list again
    for key,value in processdata.items():
        result[key] = list(value)

    return result

def main(args):

    poller = zmq.Poller()
    
    model = setupMiddleware(args)
    assert not isinstance(model, type(None)), "could not setup model for middleware"

    socket = setupSocket(args, poller, prefix="%s-%s" %(args.device, str(args.deviceid)))
    assert not isinstance(socket, type(None)), "ZeroMQ Socket coult not be created"

    liveness = args.heartbeatliveness
    interval = INTERVAL_INIT
    
    heartbeat_at = time.time() + args.heartbeatinterval
       
    while True:
        result = []
        jmsg = None

        # waiting for a message
        socks = dict(poller.poll(args.heartbeatinterval * 1000))

        # Handle worker activity on backend
        if socks.get(socket) == zmq.POLLIN:
            LOGGER.debug("Got POLLIN")
            #  Get message
            #  - 3-part envelope + content -> request
            #  - 1-part HEARTBEAT -> heartbeat
            frames = socket.recv_multipart()
            if not frames:
                break # Interrupted

            if len(frames) == 1 and frames[0] == PPP_HEARTBEAT:
                LOGGER.debug("Heartbeat from broker")

                liveness = args.heartbeatliveness

            # regular work request from a client
            elif len(frames) == 3:
                address, empty, request = frames
                liveness = args.heartbeatliveness
        
                try:
                    jmsg = json.loads(request.decode("utf-8"))
                except Exception as excep:
                    LOGGER.warning("could not decode json message from socket: %s",str(excep))
                    socket.send_multipart([address, b'',
                                           json.dumps({
                                               "result": None,
                                               "error": "could not decode json message from socket"
                                           }).encode('utf-8')])
                    continue

                if 'data' not in jmsg:
                    LOGGER.warning("skipping: no data in message")
                    socket.send_multipart([address, b'',
                                           json.dumps({
                                               "result": None,
                                               "error": "no data in message"
                                           }).encode('utf-8')])
            
                    continue

                LOGGER.debug("starting processing:")
                data = jmsg['data']
                try:
                    result = doMiddleware(model, jmsg['data'], args)
                except Exception as excep:
                    LOGGER.warning("predition failed: %s",str(excep))
                    socket.send_multipart([address, b'',
                                           json.dumps({
                                               "result": None,
                                               "error": "prediction failed - check server"
                                           }).encode('utf-8')])
                    continue
            
                LOGGER.debug("done prediction")
                socket.send_multipart([address, b'',
                               json.dumps({
                                   "result": result,
                                   "error": None
                               }).encode('utf-8')])
            else:
                LOGGER.error("Invalid message: %s",str(frames))
                
            interval = INTERVAL_INIT
        else:
            liveness -= 1
            if liveness == 0:
                LOGGER.warning("Heartbeat failure, can't reach queue")
                LOGGER.warning("Reconnecting in %0.2fs...", interval)
                time.sleep(interval)

                if interval < INTERVAL_MAX:
                    interval *= 2
                poller.unregister(socket)
                socket.setsockopt(zmq.LINGER, 0)
                socket.close()
                socket = setupSocket(args, poller, prefix="%s-%s" %(args.device, str(args.deviceid)))
                liveness = args.heartbeatliveness
        if time.time() > heartbeat_at:
            heartbeat_at = time.time() + args.heartbeatinterval
            LOGGER.info("sending Worker heartbeat")
            socket.send(PPP_HEARTBEAT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
provides a middleware-worktervia zmq. it accepts json in the form: { "text" "<text>" }
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

    parser.add_argument('--keepcudacache', action="store_true",
                        help = "keep the cachedata on the cuda-device. default is to drop the cache after prediction to free no longer used memory on the device")
    
    parser.add_argument('--threshold', type = float,
                        default = 0.95,
                        help = 'every NER-Tag produced by the model comes with a confidence. with the nertaggermiddleware enabled, labes with a confidence lower then this value are ignored and filted out.')

    parser.add_argument('--zmqsocket', type = str,
                        default = "tcp://localhost:5562",
                        help = "where to find the zmq-proxy/broker to register as worker")

    parser.add_argument('--identityprefix', type = str,
                        default = None,
                        help = "set an identityprefix for zmq-worker-identityname. If None is given used device is choosen")
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
    
