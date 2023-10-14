# ner-tagger
a http-api to provide Named-entity recognition for text

# Setup

    git clone https://github.com/banduri/ner-tagger
    cd ner-tagger
    virtualenv .
    source bin/activate
    pip install -r requirements

# size

    (ner-tagger) ~/GITs/ner-tagger >>> du -h -d 1
    52K	./debian
    36K	./ner_tagger
    5.4G	./lib
    184K	./bin
    2.2M	./share
    2.2G	./models
    3.7M	./nltk_data
    2.1M	./.git
    4.0K	./data
    7.6G	.

# debian package

    dpkg-buildpackage -us -uc

# infrastructure

The software consists of four parts. A modelserver to access the model. A cacheserver to store already processed texts. A http-fronted server to provide the api. A ZeroMQ-Broker/Proxy. All four components run as individual processes.

ZeroMQ is used to decouple the components so they can be scaled individually.

    ┌──────────────┐       ┌──────────────┐
    │              │       │              │
    │  ModelServer │  ...  │  ModelServer │
    │              │       │              │
    └──────┬───────┘       └─────────┬────┘
           │                         │
           │                         │
           │                         │
           │     ┌─────────────┐     │
           │     │             │     │
           └─────┤  zmq-Broker ├─────┘
                 │             │
                 └─┬────────┬──┘
                   │        │
                   │        │
                   │        │
                   │        │
                   │        │
                   │        │
     ┌─────────────┴┐     ┌─┴────────────┐
     │              │     │              │
     │  http-Worker │ ... │  http-Worker │
     │              │     │              │
     └───────────┬──┘     └──────┬───────┘
                 │               │
                 │               │             ┌──────────────┐
                 │               └─────────────┤              │
                 │                             │  cacheServer │
                 └─────────────────────────────┤              │
                                               └──────────────┘

it is possible to run more then one ModelServer on the same host, while every instance uses a different GPU. It is also possible to setup multiple hosts each running a ModelServer. Since the 'slow'-Part is the use of the model there should be no need to setup more http-Workers then ModelServers. All http-Workers should connect to the same cacheServer.

# Running

    cd ner-tagger
    source bin/activate
    ./cacheServer.py &
    ./modelServer.py &
    ./zmqBroker.py &
    ./nerapi.py

# api endpoints

## http-fronted

the default API-Endpoint is
    curl http://localhost:8000/api/ner -d '{"text": "die Kinder von Anton Schwarz haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"                           
    {"PERSON": ["Anton Schwarz"], "GPE": ["Dresden"], "WORK_OF_ART": ["Traumwerkstadt"]}

the text provided is split into seperate sentences. For every sentence a request to the model is done

    (ner-tagger) ~/GITs/ner-tagger >>> cat data/cache_data.ndjson
    {"die Kinder von Anton Schwarz haben in Dresden eine Wohnung.": {"PERSON": ["Anton Schwarz"], "GPE": ["Dresden"]}}
    {"In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"WORK_OF_ART": ["Traumwerkstadt"]}}

Splitting up the text into sentences sometimes yields wrong results. 

    curl http://localhost:8000/api/ner -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"                           
    {"GPE": ["Dresden"], "WORK_OF_ART": ["Traumwerkstadt"]}

    cat data/cache_data.ndjson
    {"die Kinder von Elisabeth II.": {}}
    {"haben in Dresden eine Wohnung.": {"GPE": ["Dresden"]}}
    {"In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"WORK_OF_ART": ["Traumwerkstadt"]}}

the second endpoint does not split, but leads to a general problem with neural networks

    curl http://localhost:8000/api/nernosplit -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"
    {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"]}

    cat data/cache_data.ndjson
    {"die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"]}}

    curl http://localhost:8000/api/nernosplit -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch \"Traumwerkstadt\" wird die Wohnung beschrieben."}' -H "Content-Type: application/json"                
    {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"], "WORK_OF_ART": ["\"Traumwerkstadt\""]}

## cacheServer

