#!/bin/bash
#

./modelServer.py &
./zmqBroker.py &
./cacheServer.py &
./nerapi.py 
