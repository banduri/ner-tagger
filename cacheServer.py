#!/usr/bin/env python

import logging
import argparse
import uuid
import json


import zmq



# configure logging and LOGGER
logging.basicConfig(format='%(asctime)s %(name)s' +
        '\t(module: %(module)s; function: %(funcName)s; line:\t%(lineno)d)' +
        '\t%(levelname)s:\t%(message)s',level=logging.WARN)
LOGGER = logging.getLogger(__name__)


# argparse magic
class RawTextDefaultsHelpFormatter(argparse.RawDescriptionHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    pass

def rereadcache(args):
    """
    prefill the cache with local data
    """
    result = {}
    try:
        with open(args.cache) as fp:
            for line in fp.readlines():
                tmp = json.loads(line)
                cache_key = str(uuid.uuid5(uuid.NAMESPACE_X500,tmp['key']))
                result[cache_key] = tmp['value']
    except Exception as exep:
        LOGGER.warning("Could not read cachefile at %s: %s",args.cache, str(exep))

    return result

def main(args):
    cache=rereadcache(args)

    context = zmq.Context()
    socket = context.socket(zmq.REP)

    socket.bind(args.zmqsocket)
    LOGGER.info("Starting mainloop")

    while True:
        message = socket.recv()
        LOGGER.debug(f"Received request: {message}")
        jmsg = None
        try:
            jmsg = json.loads(message.decode("utf-8"))
        except Exception as excep:
            LOGGER.warning("skipping - could not decode json: %s",str(excep))
            socket.send(json.dumps({"result": None, "error": str(excep)}).encode('utf-8'))
            continue

        if 'cmd' in jmsg:
            if jmsg['cmd'] == 'store':
                if 'key' in jmsg and 'value' in jmsg:
                    cache_key = None
                    try:
                        cache_key = str(uuid.uuid5(uuid.NAMESPACE_X500,jmsg['key']))
                    except Exception as excep:
                        LOGGER.warning("skipping - could not create cache_key: %s", str(excep))
                        socket.send(json.dumps({
                            "result": None,
                            "error": "could not create (internal) cache_key"
                        }).encode('utf-8'))
                        continue
                    # all good store it
                    cache[cache_key] = jmsg['value']
                    try:
                        with open(args.cache,'a') as cache_file:
                            cache_file.write(json.dumps({jmsg['key']: jmsg['value']}))
                            cache_file.write("\n")
                    except Exception as excep:
                        LOGGER.warning("Could not store on disc: %s",str(excep))

                    socket.send(json.dumps({ "result": "ACK", "error": None }).encode('utf-8'))
                else:
                    LOGGER.warning("skipping - key or value is missing: %s", json.dumps(jmsg))
                    socket.send(json.dumps({
                        "result": None,
                        "error": "key or value missing in message"
                    }).encode('utf-8'))
                    continue
                    
            elif jmsg['cmd'] == 'retrieve':
                if 'key' in jmsg :
                    cache_key = None
                    try:
                        cache_key = str(uuid.uuid5(uuid.NAMESPACE_X500,jmsg['key']))
                    except Exception as excep:
                        LOGGER.warning("skipping - could not create cache_key: %s", str(excep))
                        socket.send(json.dumps({
                            "result": None,
                            "error": "could not create (internal) cache_key"
                        }).encode('utf-8'))
                        continue
                    # all good - pull it
                    if cache_key in cache:
                        data = cache[cache_key]
                        LOGGER.debug("cachehit for: %s->%s",cache_key,jmsg['key'])
                        socket.send(json.dumps({ "result": data, "error": None }).encode('utf-8'))
                    else:
                        LOGGER.debug("not in cache: %s->%s",cache_key,jmsg['key'])
                        socket.send(json.dumps({ "result": None, "error": None }).encode('utf-8'))
                        
                else:
                    LOGGER.warning("skipping - key is missing: %s", json.dumps(jmsg))
                    socket.send(json.dumps({
                        "result": None,
                        "error": "key missing in message"
                    }).encode('utf-8'))
                    continue
            else:
                LOGGER.warning("skipping - unknown cmd found in message: %s", json.dumps(jmsg))
                socket.send(json.dumps({
                    "result": None,
                    "error": f"unknow cmd {jmsg['cmd']} found in message"
                }).encode('utf-8'))
                continue
                
        else:
            LOGGER.warning("skipping - no cmd found in message: %s", json.dumps(jmsg))
            socket.send(json.dumps({
                "result": None,
                "error": str(excep)
            }).encode('utf-8'))
            continue
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class = RawTextDefaultsHelpFormatter,
        description="""
provides a key-value cache via zmq. it accepts json in the form:
        { "cmd" "<store|retrieve>", "key": data, "value": data }
        if cmd is 'store' the "key" is used to store "value" data.
        if cmd is 'retrieve' the "key" is used to get data.

        on cmd='store' '{"result": "<ACK|null>", "error": <null|problem>}' is send to conform or deny cachestoreage
        on cmd='retrieve' '{"result": <data|null>}, "error": <null|problem>}' is send. null is a cachemiss

        'key' needs to be a string. From that string a uuid5-string is generated and used as the
        internal cachekey

        if anything fails a error not null is returned
        
        """,
        epilog = """
        """)
    parser.add_argument('--log', type = str,
                        choices=['debug','info','warning','error','critical'], 
                        default='warning',
                        help = 'set the loglevel')

    parser.add_argument('--cache', type = str,
                        default = "data/cache_data.ndjson",
                        help = "where to find and maintain a (precomputed) cache. everything that is found in the cache is served no matter the used model - if the model is changed a new cachefile should be used")

    parser.add_argument('--zmqsocket', type = str,
                        default = "ipc:///tmp/cache.ipc",
                        help = "the socket to bind to and wait for requests. for tcp use 'tcp://localhost:5559'. Remember to configure the clients appropriate")

    args = parser.parse_args()

    # set loglevel
    numeric_level = getattr(logging, args.log.upper(), logging.DEBUG)
    LOGGER.setLevel(numeric_level)

    main(args)
    
