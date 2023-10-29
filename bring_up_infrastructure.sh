#!/bin/bash
#
rm data/cache_data.ndjson
# setting up modelserver an zmq-model-broker
./zmqBroker.py --frontendsocket tcp://127.0.0.1:5559 --backendsocket tcp://127.0.0.1:5560 &
./modelServer.py --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin  &

# start a second modelserver on cuda-device if you've got the vRAM
#./modelServer.py --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin --device cuda  &

# start a modelserver that uses the CPU and connects to the same zmqBroker as a worker - but with lower cpu-prio - useless
#nice ./modelServer.py --log debug --zmqsocket tcp://127.0.0.1:5560 --model models/ner-english-ontonotes-large.bin --device cpu &

# setting up split-server and zmq-spit-broker
./zmqBroker.py --frontendsocket tcp://127.0.0.1:5561 --backendsocket tcp://127.0.0.1:5562 &
./splitServer.py --zmqsocket tcp://127.0.0.1:5562 --device gpu &

# setting up middleware-server and zmq-middleware-broker
./zmqBroker.py --frontendsocket tcp://127.0.0.1:5563 --backendsocket tcp://127.0.0.1:5564 &
./middlewareServer.py --zmqsocket tcp://127.0.0.1:5564 --device gpu &

# cacheserver for mdel
./cacheServer.py --zmqsocket ipc:///tmp/cache.ipc &

# webfrontend
#./nerapi.py --sentsplitter zmq --zmqsplitsocket tcp://127.0.0.1:5561 --middleware zmq --zmqmiddlewaresocket tcp://127.0.0.1:5563

# only modelserver and no cache
./nerapi.py --workertimeout 180 \
	--zmqmodelsocket tcp://127.0.0.1:5559 \
	--sentsplitter zmq --zmqsplitsocket tcp://127.0.0.1:5561 \
	--middleware zmq --zmqmiddlewaresocket tcp://127.0.0.1:5563 \
	--zmqcachesocket ipc:///tmp/cache.ipc
