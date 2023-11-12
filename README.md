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
    52K    ./debian
    80K    ./ner_tagger
    6.8G   ./lib
    192K   ./bin
    2.2M   ./share
    4.0G   ./models
    3.7M   ./nltk_data
    3.0M   ./.git
    4.0K   ./data
    64K    ./doc
    11G    .

# debian package

    dpkg-buildpackage -us -uc

# infrastructure

To software consists of
* a http-Frontend-API (NerAPI)
* a modelServer
* a zmqBroker
* an optional cacheServer
* an optional SplitServer
* an optional Middleware Server

The very basic setup is to start the zmqBroker and connect ModelServer and NerAPI to it. 'That will work' but is not that nice since splitting the text into sentences is done by the buildin nltk-package. The postprocessing also happens in the NerAPI-Frontend. Since the cacheserver is missing, all requests will stress the the modelserver. The best results are provided if a cacheserver is used, a splitserver to have better sentencesplits with the spacy package and a middleware-Server to cleanup some of the mess the model produced (also use spacy-package with some NLP-Tasks). The general setup should look like in the following image
![general setup](./doc/drawing-1.svg)

1. first the (text-)request is send to the SplitBroker which forwards (with loadbalancing) to all connected SplitServers. The splitup text is then send back to the NerAPI-Frontend. If the SplitBroker is not reachable, or the SplitServers don't reply the text is splitup via nltk on the Frontendserver. 
2. every sentence - one by one - is send to the ModelBroker which forwards (with loadbalancing) to all connected ModelServers. There is no Fallback here if it breaks, it fails hard. The response of the model goes back to the NerAPI-Frontend.
3. before contacting the ModelBroker the cacheServer is queried. If there is already result for that sentence it is returned to the NerAPI-Frontend instead of connecting the ModelBroker. If the ModelBroker was contacted, the result is stored in the cacheServer.
4. after all sentences have been analysed by the Model the data is send to the MiddlewareBroker to process it further and return the desired data to the NerAPI-Frontend, which returns it to the client.

There are other ways to setup the infrastructure. It is also possible to have different Models (including Middleware) connected to different NerAPIs but they are both using the same SplitBroker.
![same splitserver](./doc/drawing-2.svg)

An other possibility is to connect the same ModelBroker and SplitBroker to different NerAPIs and only use different MiddlewareBroker. The cacheServer is designed to be used by one NerAPI only. Also it is possible to connect the cacheServer via tcp.
![same splitserver](./doc/drawing-3.svg)

it is possible to run more then one ModelServer on the same host, while every instance uses a different GPU. It is also possible to run two modelserver on the same GPU which may gives a small speedup. It is still nesecssary to preprocess the data before it is send to the GPU which sill needs CPU processing. It is also possible to setup multiple hosts each running a ModelServer and connecting them to the same ModelBroker. Since the 'slow'-Part is the use of the model there should be no need to setup more http-Workers at the NerAPI-Frontend then ModelServers. 

# Running

    cd ner-tagger
    source bin/activate
    python ./download_and_convert_model_for_local_use.py # only once to download the model and store it for local use
    ./cacheServer.py &
    ./modelServer.py &
    ./zmqBroker.py &
    ./nerapi.py

See [full example](./bring_up_infrastructure.sh) for more

# api endpoints

## http-frontend

the default API-Endpoint is
    curl http://localhost:8000/api/v1/ner -d '{"text": "die Kinder von Anton Schwarz haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"                           
    {"PERSON": ["Anton Schwarz"], "GPE": ["Dresden"], "WORK_OF_ART": ["Traumwerkstadt"]}

the text provided is split into seperate sentences. For every sentence a request to the model is done

    (ner-tagger) ~/GITs/ner-tagger >>> cat data/cache_data.ndjson
    {"die Kinder von Anton Schwarz haben in Dresden eine Wohnung.": {"PERSON": ["Anton Schwarz"], "GPE": ["Dresden"]}}
    {"In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"WORK_OF_ART": ["Traumwerkstadt"]}}

Splitting up the text into sentences sometimes yields wrong results. 

    curl http://localhost:8000/api/v1/ner -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"
    {"GPE": ["Dresden"], "WORK_OF_ART": ["Traumwerkstadt"]}

    cat data/cache_data.ndjson
    {"die Kinder von Elisabeth II.": {}}
    {"haben in Dresden eine Wohnung.": {"GPE": ["Dresden"]}}
    {"In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"WORK_OF_ART": ["Traumwerkstadt"]}}

the 'nernosplit' endpoint does not split the paragraph into two sentences. this leads to a general problem with neural networks

    curl http://localhost:8000/api/v1/nernosplit -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben."}' -H "Content-Type: application/json"
    {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"]}

    cat data/cache_data.ndjson
    {"die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch Traumwerkstadt wird die Wohnung beschrieben.": {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"]}}

    curl http://localhost:8000/api/v1/nernosplit -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch \"Traumwerkstadt\" wird die Wohnung beschrieben."}' -H "Content-Type: application/json"
    {"PERSON": ["Elisabeth II"], "GPE": ["Dresden"], "WORK_OF_ART": ["\"Traumwerkstadt\""]}

to only get the sentences without any models involved:
    curl http://localhost:8000/api/v1/split -d '{"text": "die Kinder von Elisabeth II. haben in Dresden eine Wohnung. In dem Buch \"Traumwerkstadt\" wird die Wohnung beschrieben."}' -H "Content-Type: application/json"
    {"splits": ["die Kinder von Elisabeth II.", "haben in Dresden eine Wohnung.", "In dem Buch \"Traumwerkstadt\" wird die Wohnung beschrieben."]}

if the 'maxnosplit' value is reached on the nosplit-endpoint, the text will be splitup at sentence bounderies into parts a little bit smaller then the maxnosplit value. Each part will be send to the model.

## Zeromq

All 'internal' components are connected via zeromq. The API-Server connects to every Broker. The different Broker are waiting for their servers to connect. If a Broker does not get a heartbeat from one of their servers, this server is removed from the queue. The servers expecting to get heartbeats from the broker and try to reconnect. The API-Frontend does not send any heartbeats to the brokers. If a broker does not reply to a request within a timeout, the request is send again.

### zmq-internal-protocol

All messages between the zmq-instances are exchanging their data via json-serialization.

For the Cache it looks like this:
API->Cache - storerequest
    { "cmd": "store", "key": "sentence", "value": "content of key" }
Cache->API - storeresponse
    { "result": "ACK", "error": null }
API->Cache - lookuprequest
    { "cmd": "retrieve", "key": "sentence" }
Cache->API - lookupresponse
    { "result": "content of key", "error": null }
If anything goes wrong "result" is null and "error" contains the short description of the problem

### cacheserver

    { "cmd" "<store|retrieve>", "key": data, "value": data }

if cmd is 'store' the "key" is used to store "value" data.
if cmd is 'retrieve' the "key" is used to get data.

on cmd='store' '

    {"result": "<ACK|null>", "error": <null|problem>}'

is send to conform or deny cachestoreage. on cmd='retrieve'

    '{"result": <data|null>}, "error": <null|problem>}'

is send. null as a result is a cachemiss. 'key' needs to be a string. From that string a uuid5-string is generated and used as the internal cachekey if anything fails an error not null is returned.

### modelserver

it accepts json in the form:

    { "text" "<text>" }

it returns a json-string with the result of the model-prediction:

    { "result": <data|null>, "error": <msg|null> }

The '<data>' is modeldependent and defined by the flair-framework. It is the direct result of
    sentence = Sentence(text)
    model.predict(sentence)
    return sentence.to_dict()

example 'to_dict()' is defined like this

    def to_dict(self, tag_type: Optional[str] = None):
        return {
            "text": self.to_original_text(),
            "labels": [label.to_dict() for label in self.get_labels(tag_type) if label.data_point is self],
            "entities": [span.to_dict(tag_type) for span in self.get_spans(tag_type)],
            "relations": [relation.to_dict(tag_type) for relation in self.get_relations(tag_type)],
            "tokens": [token.to_dict(tag_type) for token in self.tokens],
        }

### splitserver

it accepts json in the form:

    { "text" "<text>" }

it returns a json-string with the result of the model-prediction:

    { "result": <data|null>, "error": <msg|null> }

The '<data>' is an array of strings, where each element of the array is a seperate sentence. The array is in order of the sentences in the paragraph. E.g. no reordering of the sentences takes place.

### middlewareserver

the json-format is a little different since it is no longer unstrucktured text

request:
    { "data" <data> }
response:
    { "result": <data|null>, "error": <msg|null> }

the Frontend-API sends the result of the model unchanged to the middlewareserver.

### zmq-Reliable Request-Reply and loadbalancing

the API-Frontend ensures reliability to the brokers by following the zeromq-book for the 'lazy pirat pattern': https://zguide.zeromq.org/docs/chapter4/#Client-Side-Reliability-Lazy-Pirate-Pattern

the Brokers, with their server, follow the 'paranoid pirate pattern' at https://zguide.zeromq.org/docs/chapter4/#Robust-Reliable-Queuing-Paranoid-Pirate-Pattern and https://zguide.zeromq.org/docs/chapter4/#Heartbeating-for-Paranoid-Pirate for their heartbeat. The loadbalancing is realized via https://zguide.zeromq.org/docs/chapter3/#The-Load-Balancing-Pattern


# custom models

Since it is flair the general howto for finetuneing and task-specific training applies. A good starting-point is https://flairnlp.github.io/docs/tutorial-training/how-model-training-works . For the final model can be directly passed to the modelserver via commandlineswitch.

## example - taz.de articles

An example of the trainingprozess can be found inside the CustomModelTrainingExample.ipynb . The content of about 250k newspaper articles of 'taz. Die Tageszeitung' was used to train a text-classifiere. The used XML-Files can be fetched by appending 'c.xml' at the end of an article. like: https://taz.de/Linkes-Engagement-in-den-US-Suedstaaten/!5969356/c.xml

since it is a TextClassifier, and not a ner-tagging/SequenceTagger the middleware-server should be disabled and the 'nernosplit'-Endpoind should be used, since the model is trained on a larger text.

     ./nerapi.py --middleware passthrough
     ./modelServer.py --model models/taz-resort-class.final.pt

