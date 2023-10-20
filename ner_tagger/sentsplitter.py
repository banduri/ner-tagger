import re
import json
import logging

import nltk
import zmq

LOGGER = logging.getLogger(__name__)

def cleanup(text):
    text = text.replace("\n"," ")
    pattern = re.compile(r'\s{2,}',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)

    pattern = re.compile(r'­',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)
    
    return str(text)

def nltksentsplit(text, args):
    result = []
    text = cleanup(text)
    sent_text = nltk.sent_tokenize(text, language=args.splitlang) # this gives us a list of sentences
        
    # now loop over each sentence and clean it separately
    for sentence in sent_text:
        result.append(cleanup(sentence))

    return result



# we don't know how the split-server behaves so implementing a lazy-pirate-pattern
# check https://zguide.zeromq.org/docs/chapter4/#Client-Side-Reliability-Lazy-Pirate-Pattern

def zmqsentsplit(sent,args):

    REQUEST_TIMEOUT = args.zmqsplittimeout # milliseconds in array
    REQUEST_RETRIES = len(args.zmqsplittimeout)
    context = zmq.Context()
    client = context.socket(zmq.REQ)
    LOGGER.info("Connecting to broker… %s", args.zmqsplitsocket)
    client.connect(args.zmqsplitsocket)
    
    request = json.dumps({ "text": cleanup(sent) }).encode('utf-8')
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
        client.connect(args.zmqsplitsocket)
        logging.info("Retry: %d with timeout %d (ms) sending (%s)", retry, REQUEST_TIMEOUT[retry], request)
        client.send(request)

    # all retries died
    LOGGER.error("Server seems to be offline after %d retries and %s timeouts -> abandoning - using buildin nltk",
                 REQUEST_RETRIES, str(REQUEST_TIMEOUT))
    client.setsockopt(zmq.LINGER, 0)
    client.close()

    result = nltksentsplit(sent,args)
    
    # act as it would be a passthrough
    return result


sentsplitter = {
    'nltk': nltksentsplit,
    'zmq': zmqsentsplit
    }
