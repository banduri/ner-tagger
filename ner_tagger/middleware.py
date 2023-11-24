from collections import defaultdict
import json
import zmq
import logging

LOGGER = logging.getLogger(__name__)

def passthroughmiddleware(data,args):
    """
    does nothing 
    """
    return data
    
def sentimentmiddleware(data,args):
    """
    takes multiple entries from data['labels'] with value "POSITIV","NEGATIV","OTHER" and "OFFENSE"
    sums them up to one score. POSITIV and OTHER are interpretated as positiv values
    while "OFFENSE" and "NEGATIV" are interprete as negativ values. 

    the expected format is an array like "[{'value': 'OTHER', 'confidence': 1.0},..."
    
    """
    score = 0
    wrongDataCounter = 0
    totalDataCounter = 0
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]
    for datapoint in data:
        if 'labels' in datapoint and len(datapoint['labels']) > 0 and isinstance(datapoint['labels'],list):
            for l in datapoint['labels']:
                totalDataCounter = totalDataCounter + 1
                if l['value'] in args.sentimentpositiv:
                    score = score + l['confidence']
                elif l['value'] in args.sentimentnegativ:
                    score = score - l['confidence']
                else:
                    wrongDataCounter = wrongDataCounter + 1
    
    score = score / ( totalDataCounter - wrongDataCounter)

    return {'score': score}

def nertaggermiddleware(data,args):
    """
    takes multiple from data['entities'] discards any 'span' information like start and stop and only
    provides the NERs found in the text. also labels with a confidence smaller then threshold are filtered out
    """
    processdata = defaultdict(set)
    result = {}
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]
    for datapoint in data:
        if 'entities' in datapoint and len(datapoint['entities']) > 0 and isinstance(datapoint['entities'],list):
            for e in datapoint['entities']:
                confidence = e['labels'][0]['confidence']
                label = e['labels'][0]['value']
                text = e['text']
                if confidence >= args.nerthreshold:
                    processdata[label].add(text)

    # make everything a list again
    for key,value in processdata.items():
        result[key] = list(value)

    return result

# we don't know how the middleware behaves so implementing a lazy-pirate-pattern
# check https://zguide.zeromq.org/docs/chapter4/#Client-Side-Reliability-Lazy-Pirate-Pattern

def zmqmiddleware(data,args):
    REQUEST_TIMEOUT = args.zmqmiddlewaretimeout # milliseconds in array
    REQUEST_RETRIES = len(args.zmqmiddlewaretimeout)
    context = zmq.Context()
    client = context.socket(zmq.REQ)
    LOGGER.info("Connecting to broker… %s",args.zmqmiddlewaresocket)
    client.connect(args.zmqmiddlewaresocket)
    
    request = json.dumps({ "data": data }).encode('utf-8')
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
        client.connect(args.zmqmiddlewaresocket)
        logging.info("Retry: %d with timeout %d (ms) sending (%s)", retry, REQUEST_TIMEOUT[retry], request)
        client.send(request)

    # all retries died
    LOGGER.error("Server seems to be offline after %d retries and %s timeouts -> abandoning",
                 REQUEST_RETRIES, str(REQUEST_TIMEOUT))
    client.setsockopt(zmq.LINGER, 0)
    client.close()

    # act as it would be a passthrough
    return data

middleware = {
    'passthrough': passthroughmiddleware,
    'sentiment': sentimentmiddleware,
    'nertagger': nertaggermiddleware,
    'zmq': zmqmiddleware
    }
