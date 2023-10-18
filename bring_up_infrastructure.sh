#!/bin/bash
#
rm data/cache_data.ndjson
# setting up modelserver an zmq-model-broker
./modelServer.py --log debug --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin &
./zmqBroker.py --log debug --frontendsocket tcp://127.0.0.1:5559 --backendsocket tcp://127.0.0.1:5560 &

# setting up split-server and zmq-spit-broker
./splitServer.py --log debug --zmqsocket tcp://127.0.0.1:5562 --device gpu &
./zmqBroker.py --log debug --frontendsocket tcp://127.0.0.1:5561 --backendsocket tcp://127.0.0.1:5562 &

# cacheserver for mdel
./cacheServer.py --log debug &

# webfrontend
./nerapi.py --log debug --workertimeout 180 --sentsplitter zmq --zmqsplitsocket tcp://127.0.0.1:5561
