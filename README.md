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

