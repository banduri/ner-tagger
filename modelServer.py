#!/usr/bin/env python

import logging
import argparse
import json
from collections import defaultdict
from random import randint
import time

import zmq

import flair

from flair.nn import Classifier
from flair.data import Sentence

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


def setupModel(args):
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
    finally:
        return model, device

def doModel(model, text, args):

    sentence = Sentence(text)
    
    model.predict(sentence)
    LOGGER.info("done prediction")
    
    result = sentence.to_dict()

    # drop the cuda-cache
    if not args.keepcudacache and torch.cuda.is_available():
        torch.cuda.empty_cache()
        LOGGER.info("cleared cudacache")

    return result



def setupSocket(args, poller, prefix=None):
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

def main(args):
    model, device = setupModel(args)

    poller = zmq.Poller()

    socket = setupSocket(args, poller, prefix=str(device))
    
    assert not isinstance(model, type(None)), "Model could not be loaded"
    assert not isinstance(socket, type(None)), "ZeroMQ Socket coult not be created"


    liveness = args.heartbeatliveness
    interval = INTERVAL_INIT
    
    heartbeat_at = time.time() + args.heartbeatinterval

    while True:
        result = None
        jmsg = None

        # waiting for a message
        socks = dict(poller.poll(args.heartbeatinterval * 1000))

        # Handle worker activity on backend
        if socks.get(socket) == zmq.POLLIN:
            #  Get message
            #  - 3-part envelope + content -> request
            #  - 1-part HEARTBEAT -> heartbeat
            frames = socket.recv_multipart()
            if not frames:
                break # Interrupted

            if len(frames) == 1 and frames[0] == PPP_HEARTBEAT:
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

                if 'text' not in jmsg:
                    LOGGER.warning("skipping: no text in message")
                    socket.send_multipart([address, b'',
                                           json.dumps({
                                               "result": None,
                                               "error": "no text in message"
                                           }).encode('utf-8')])
            
                    continue

                LOGGER.info("starting prediction on device: %s ", args.device)
                try:

                    result = doModel(model, jmsg['text'], args)
            
                except Exception as excep:
                    LOGGER.warning("predition failed: %s",str(excep))
                    socket.send_multipart([address, b'',
                                           json.dumps({
                                               "result": None,
                                               "error": "prediction failed: %s" %(str(execp))
                                           }).encode('utf-8')])
                    continue

                # all good - send the result
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
                socket = setupSocket(args,poller,device)
                liveness = args.heartbeatliveness
        if time.time() > heartbeat_at:
            heartbeat_at = time.time() + args.heartbeatinterval
            LOGGER.info("sending Worker heartbeat")
            socket.send(PPP_HEARTBEAT)

        

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

    parser.add_argument('--keepcudacache', action="store_true",
                        help = "keep the cachedata on the cuda-device. default is to drop the cache after prediction to free no longer used memory on the device")

    parser.add_argument('--zmqsocket', type = str,
                        default = "tcp://localhost:5560",
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
    
