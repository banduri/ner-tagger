import locale
import logging

import json
from collections import defaultdict

import uuid

from concurrent.futures import ThreadPoolExecutor

from flask import request, Flask

# served via gunicorn custom app
import gunicorn.app.base

import zmq

# used for data postprocessing
from .middleware import middleware

# used to split into sentence
from .sentsplitter import sentsplitter

# enforce german locale
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)

def textsplitner(sentences,args):
    result = []
    splitsentences = sentsplitter[args.sentsplitter](sentences,args)
    # do parallel processing on all sentences
    argsarray = [args]*len(splitsentences)
    try:
        with ThreadPoolExecutor(args.maxparallelmodelrequests) as tpool:
            result = list(tpool.map(ner,splitsentences,argsarray))
    except Exception as exep:
        LOGGER.warning("could not process request: %s",str(exep))
            
    LOGGER.debug("threadpoolresult: %s",result)
    return result

def cacherequest(sent,args):
    """
    ask zmq-cache for data
    """
    cachecontext = zmq.Context()
    cachesocket = cachecontext.socket(zmq.REQ)
    cachesocket.connect(args.zmqcachesocket)
    LOGGER.debug("requesting from cache")
    cachesocket.send(json.dumps({
        "cmd": "retrieve",
        "key": sent
    }).encode('utf-8'))
    cachemsg = cachesocket.recv()
    jmsg = json.loads(cachemsg.decode("utf-8"))
    if not isinstance(jmsg['result'],type(None)):
        LOGGER.info("cachehit for: %s",sent)
        data = jmsg['result']

        return data
    else:
        LOGGER.info("not a cachehit")
        return None

def cacheit(key,value,args):
    """
    ask zmq-cache for data
    """
    cachecontext = zmq.Context()
    cachesocket = cachecontext.socket(zmq.REQ)
    cachesocket.connect(args.zmqcachesocket)
    LOGGER.debug("requesting from cache")
    cachesocket.send(json.dumps({
        "cmd": "store",
        "key": key,
        "value": value
    }).encode('utf-8'))
    cachemsg = cachesocket.recv()
    # at that point we are at fire and forget, either store it or not, i don't care
    jmsg = json.loads(cachemsg.decode("utf-8"))
    if jmsg['result'] != "ACK":
        LOGGER.info("CacheServer did not store: %s",str(jmsg))

def modelrequest(sent,args):
    REQUEST_TIMEOUT = args.zmqmodeltimeout # milliseconds in array
    REQUEST_RETRIES = len(args.zmqmodeltimeout)
    context = zmq.Context()
    client = context.socket(zmq.REQ)
    LOGGER.info("Connecting to broker… %s",args.zmqmodelsocket)
    client.connect(args.zmqmodelsocket)
    
    request = json.dumps({ "text": sent }).encode('utf-8')
    LOGGER.debug("Sending request: %s", request.decode('utf-8'))
                 
    client.send(request)

    for retry in range(REQUEST_RETRIES):
        if (client.poll(REQUEST_TIMEOUT[retry]) & zmq.POLLIN) != 0:
            # all good - server replied within timeout
            # fetch message, decode it, check for error and return it if fine
            msg = client.recv()
            jmsg = json.loads(msg.decode("utf-8"))
            # there was an error somehow
            if isinstance(jmsg['error'], type(None)):
                LOGGER.info("got data")
                return jmsg['result']
            else:
                LOGGER.warning("try %d/%d server returned with error: %s",retry+1,REQUEST_RETRIES,jmsg['error'])
                # retry
                continue
                
        LOGGER.warning("No response from server within Timeout: %d (ms)", REQUEST_TIMEOUT[retry])
        # do not keep the send message any further in RAM since the socket is closed an reopend
        # http://api.zeromq.org/master:zmq-setsockopt#toc28
        # 
        client.setsockopt(zmq.LINGER, 0)
        client.close()

        logging.info("Reconnecting to server…")
        # Create new connection
        client = context.socket(zmq.REQ)
        client.connect(args.zmqmodelsocket)
        logging.info("Retry: %d with timeout %d (ms) sending (%s)", retry, REQUEST_TIMEOUT[retry], request)
        client.send(request)

    # all retries died
    LOGGER.error("Server seems to be offline after %d retries and %s timeouts -> abandoning",
                 REQUEST_RETRIES, str(REQUEST_TIMEOUT))
    client.setsockopt(zmq.LINGER, 0)
    client.close()

    # act as it would be a passthrough
    return {}

    
def ner(sent,args):

    data = defaultdict(set)

    if not args.disablecache:
        data = cacherequest(sent,args)
        if not isinstance(data,type(None)):
            return data
    # if we are still here, we ask the zmq-worker
    data = modelrequest(sent,args)
    # store in cache
    if not args.disablecache:
        cacheit(key=sent,value=data, args=args)

    LOGGER.debug("modeldata: %s",str(data))
            
    return data

def create_app(description, args):

    nerapi = Flask(__name__)
    
    @nerapi.route('/')
    def index():
        return description

    @nerapi.route('/api/v1/ner',methods=['POST'])
    def api_ner():

        text = request.get_json().get('text')
        data = textsplitner(text,args)
    
        # do postprocessing 
        data = middleware[args.middleware](data,args)

        return json.dumps(data)

    @nerapi.route('/api/v1/nernosplit',methods=['POST'])
    def api_nernosplit():
        text = request.get_json().get('text')
        # sometimes text is just to big to process it as one
        if len(text) > args.maxnosplit:
            LOGGER.warning("Maxnosplit reached, using split instead")
            # split on sentences
            sentences = sentsplitter[args.sentsplitter](text,args)
            parts = [""]
            for sentence in sentences:
                partidx = len(parts) - 1
                # as long as the part is smaller then maxnosplit minus 10%, add the sentence to the part 
                if len(parts[partidx]) < ( args.maxnosplit - int(args.maxnosplit * 0.1) ):
                    parts[partidx] = parts[partidx] + " " + str(sentence)
                else:
                    parts.append(str(sentence))

            # run model on every part
            result = []
            for part in parts:
                data = ner(part,args)
                # merge the results
                result.append(data)

            # do postprocessing 
            result = middleware[args.middleware](result,args)

            return json.dumps(result)
        else:
            result = ner(text,args)
            # do postprocessing 
            result = middleware[args.middleware](result,args)
            
            return json.dumps(result)

    @nerapi.route('/api/v1/split',methods=['POST'])
    def api_split():
        text = request.get_json().get('text')
        result = {'splits': sentsplitter[args.sentsplitter](text,args)}
        return json.dumps(result)


    return nerapi


# https://docs.gunicorn.org/en/stable/custom.html
class StandaloneApplication(gunicorn.app.base.BaseApplication):

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app

        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


