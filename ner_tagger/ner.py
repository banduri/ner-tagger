import locale
import logging

import json
from collections import defaultdict

import re
import uuid

import nltk

from flask import request, Flask

# served via gunicorn custom app
import gunicorn.app.base

import zmq
# enforce german locale
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)

def cleanup(text):
    text = text.replace("\n"," ")
    pattern = re.compile(r'\s{2,}',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)

    pattern = re.compile(r'­',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)
    
    return text

def splitsent(text, language='german'):
    result = []
    text = cleanup(text)
    sent_text = nltk.sent_tokenize(text, language=language) # this gives us a list of sentences
        
    # now loop over each sentence and clean it separately
    for sentence in sent_text:
        result.append(cleanup(sentence))

    return result

def textsplitner(sentences,args):
    result = defaultdict(set)
    for sent in splitsent(sentences, language=args.splitlang):
        try:
            data = ner(sent,args)
            for key,value in data.items():
                result[key].update(value)
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
        data = defaultdict(set)
        for tag in jmsg['result']:
            data[tag].update(set(jmsg['result'][tag]))
            # the exception else-block is not executed if we continue, the finally-block is
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
        "value": preparejson(value)
    }).encode('utf-8'))
    cachemsg = cachesocket.recv()
    # at that point we are at fire and forget, either store it or not, i don't care
    jmsg = json.loads(cachemsg.decode("utf-8"))
    if jmsg['result'] != "ACK":
        LOGGER.info("CacheServer did not store: %s",str(jmsg))

def modelrequest(sent,args):
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
    # flair supports to predict multiple sentences at once, but
    # if an exceptions occurse on one sentence all fails
    # cacheuse would be useless

    if not args.disablecache:
        data = cacherequest(sent,args)
        if not isinstance(data,type(None)):
            return data
    # if we are still here, we ask the zmq-worker
    data = modelrequest(sent,args)

    # store in cache
    if not args.disablecache:
        cacheit(key=sent,value=data, args=args)
        
    return data

def preparejson(data):
    result = {}
    
    if data:
        data = dict(data)
    else:
        data={}
    for i in data.keys():
        result[i] = list(data[i])
    return result    

def create_app(description,args):

    nerapi = Flask(__name__)
    
    @nerapi.route('/')
    def index():
        return description

    @nerapi.route('/api/ner',methods=['POST'])
    def api_ner():

        text = request.get_json().get('text')
                
        return json.dumps(preparejson(textsplitner(text,args)))

    @nerapi.route('/api/nernosplit',methods=['POST'])
    def api_nernosplit():

        text = request.get_json().get('text')
        # sometimes text is just to big to process it as one
        if len(text) > args.maxnosplit:
            LOGGER.warning("Maxnosplit reached, using split instead")
            return json.dumps(preparejson(textsplitner(text,args)))
        else:
            return json.dumps(preparejson(ner(text,args)))

    @nerapi.route('/api/split',methods=['POST'])
    def api_split():

        text = request.get_json().get('text')
        result = {'splits': splitsent(text,language=args.splitlang)}
        return json.dumps(preparejson(result))


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


