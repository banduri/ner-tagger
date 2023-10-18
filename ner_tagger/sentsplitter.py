import re
import nltk
import zmq
import json

def cleanup(text):
    text = text.replace("\n"," ")
    pattern = re.compile(r'\s{2,}',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)

    pattern = re.compile(r'­',flags=re.UNICODE)
    text = re.sub(pattern, ' ', text)
    
    return text

def nltksentsplit(text, args):
    result = []
    text = cleanup(text)
    sent_text = nltk.sent_tokenize(text, language=args.splitlang) # this gives us a list of sentences
        
    # now loop over each sentence and clean it separately
    for sentence in sent_text:
        result.append(cleanup(sentence))

    return result


def zmqsentsplit(sent,args):
    ## XXX better error checking... or any checking at all
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(args.zmqsplitsocket)
    socket.send(json.dumps({
        "text": sent
    }).encode('utf-8'))
    msg = socket.recv()
    jmsg = json.loads(msg.decode("utf-8"))
    return jmsg['result']

sentsplitter = {
    'nltk': nltksentsplit,
    'zmq': zmqsentsplit
    }
