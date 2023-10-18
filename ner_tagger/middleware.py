from collections import defaultdict


def passthroughmiddleware(data):
    """
    does nothing 
    """
    return data
    
def sentimentmiddleware(data):
    """
    takes multiple entries from data['labels'] with value "POSITIV","NEGATIV","OTHER" and "OFFENSE"
    sums them up to one score. POSITIV and OTHER are interpretated as positiv values
    while "OFFENSE" and "NEGATIV" are interprete as negativ values. 

    the expected format is an array like "[{'value': 'OTHER', 'confidence': 1.0},..."
    
    """
    score = 0
    wrongDataCounter = 0
    totalDataCounter = 0
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]
    for datapoint in data:
        if 'labels' in datapoint and len(datapoint['labels']) > 0 and isinstance(datapoint['labels'],list):
            for l in datapoint['labels']:
                totalDataCounter = totalDataCounter + 1
                if l['value'] in ("OTHER","POSITIV"):
                    score = score + l['confidence']
                elif l['value'] in ("NEGATIV","OFFENSE"):
                    score = score - l['confidence']
                else:
                    wrongDataCounter = wrongDataCounter + 1
    
    score = score / ( totalDataCounter - wrongDataCounter)

    return {'score': score}

def nertaggermiddleware(data,threshold=0.95):
    """
    takes multiple from data['entities'] discards any 'span' information like start and stop and only
    provides the NERs found in the text. also labels with a confidence smaller then threshold are filtered out
    """
    processdata = defaultdict(set)
    result = {}
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]
    for datapoint in data:
        if 'entities' in datapoint and len(datapoint['entities']) > 0 and isinstance(datapoint['entities'],list):
            for e in datapoint['entities']:
                confidence = e['labels'][0]['confidence']
                label = e['labels'][0]['value']
                text = e['text']
                if confidence >= threshold:
                    processdata[label].add(text)

    # make everything a list again
    for key,value in processdata.items():
        result[key] = list(value)

    return result

def nerlemmarmiddleware(data,threshold=0.95):
    """
    takes multiple from data['entities'] discards any 'span' information like start and stop and only
    provides the NERs found in the text. also labels with a confidence smaller then threshold are filtered out
    does lematarization using spacy
    """
    import spacy
    nlp = spacy.load("de_core_news_lg", disable=["ner"])

    processdata = defaultdict(set)
    result = {}
    # in the case of splitting the text, data is an array of dict. otherwise it is a dict
    # let's make everything an array an process it the same way
    if not isinstance(data,list):
        data = [data]
    for datapoint in data:
        if 'entities' in datapoint and len(datapoint['entities']) > 0 and isinstance(datapoint['entities'],list):
            for e in datapoint['entities']:
                confidence = e['labels'][0]['confidence']
                label = e['labels'][0]['value']
                text = []
                if confidence >= threshold:
                    doc = nlp(e['text'])

                    for token in doc:
                        # filter out german artikels like 'der die das'
                        if token.tag_ != "ART":
                            text.append(token.lemma_)
                    text = " ".join(text)        
                    processdata[label].add(text)
                

    # make everything a list again
    for key,value in processdata.items():
        result[key] = list(value)

    del nlp
    return result

middleware = {
    'passthrough': passthroughmiddleware,
    'sentiment': sentimentmiddleware,
    'nertagger': nertaggermiddleware,
    'nerlemmar': nerlemmarmiddleware
    }
