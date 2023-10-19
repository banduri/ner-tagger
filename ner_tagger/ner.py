import locale
import logging

import json
from collections import defaultdict

import uuid

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
    for sent in sentsplitter[args.sentsplitter](sentences,args):
        try:
            data = ner(sent,args)
            result.append(data)

        except Exception as exep:
            LOGGER.warning("could not process request: %s",str(exep))
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
    ## XXX better error checking... or any checking at all
    modelcontext = zmq.Context()
    modelsocket = modelcontext.socket(zmq.REQ)
    modelsocket.connect(args.zmqmodelsocket)
    modelsocket.send(json.dumps({
        "text": sent
    }).encode('utf-8'))
    modelmsg = modelsocket.recv()
    jmsg = json.loads(modelmsg.decode("utf-8"))
    return jmsg['result']
    
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
            result = middleware[args.middleware](result,arbs)

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


