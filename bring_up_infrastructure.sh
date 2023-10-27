#!/bin/bash
#
rm data/cache_data.ndjson
# setting up modelserver an zmq-model-broker
./modelServer.py --log debug --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin  &
./zmqBroker.py --log debug --frontendsocket tcp://127.0.0.1:5559 --backendsocket tcp://127.0.0.1:5560 &

# start a second modelserver on cuda-device
#./modelServer.py --log debug --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin --device cuda  &

# start a modelserver that uses the CPU and connects to the same zmqBroker as a worker - but with lower cpu-prio - useless
#nice ./modelServer.py --log debug --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin --device cpu &

# setting up split-server and zmq-spit-broker
#./splitServer.py --log debug --zmqsocket tcp://127.0.0.1:5562 --device gpu &
#./zmqBroker.py --log debug --frontendsocket tcp://127.0.0.1:5561 --backendsocket tcp://127.0.0.1:5562 &

# setting up middleware-server and zmq-middleware-broker
#./middlewareServer.py --log debug --zmqsocket tcp://127.0.0.1:5564 --device gpu &
#./zmqBroker.py --log debug --frontendsocket tcp://127.0.0.1:5563 --backendsocket tcp://127.0.0.1:5564 &

# cacheserver for mdel
#./cacheServer.py --log debug &

# webfrontend
#./nerapi.py --sentsplitter zmq --zmqsplitsocket tcp://127.0.0.1:5561 --middleware zmq --zmqmiddlewaresocket tcp://127.0.0.1:5563

# only modelserver and no cache
./nerapi.py --log debug --workertimeout 180 --disablecache 
